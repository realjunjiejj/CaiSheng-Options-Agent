"""Independent accounting oracle and fill model for trade evaluation across all baselines."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from volagent.domain.strategies import StrategyCandidate


@dataclass(frozen=True)
class RealizedTradeResult:
    entry_cash_flow: float
    exit_cash_flow: float
    total_friction: float
    net_pnl: float | None
    max_loss: float
    is_valid: bool
    validity_note: str
    entry_description: str
    exit_description: str


def compute_realized_trade_pnl(
    candidate: StrategyCandidate,
    exit_quotes: dict[str, dict[str, Any]],
    fee_per_contract: float = 0.65,
    slippage_per_contract: float = 0.02,
    multiplier: int = 100,
    expected_exit_time: datetime | None = None,
) -> RealizedTradeResult:
    """Compute exact executable P&L using shared fill model:
    - Long legs enter at ask (+slippage) and exit at bid (-slippage).
    - Short legs enter at bid (-slippage) and exit at ask (+slippage).
    - Deducts per-contract exchange fees and slippage on both entry and exit.
    """
    if not candidate.legs or candidate.quantity <= 0:
        return RealizedTradeResult(
            entry_cash_flow=0.0,
            exit_cash_flow=0.0,
            total_friction=0.0,
            net_pnl=0.0,
            max_loss=0.0,
            is_valid=True,
            validity_note="VALID (Flat)",
            entry_description="—",
            exit_description="—",
        )

    assumptions_valid = (
        math.isfinite(fee_per_contract)
        and fee_per_contract >= 0.0
        and math.isfinite(slippage_per_contract)
        and slippage_per_contract >= 0.0
        and isinstance(multiplier, int)
        and multiplier > 0
    )
    if not assumptions_valid:
        return RealizedTradeResult(
            entry_cash_flow=0.0,
            exit_cash_flow=0.0,
            total_friction=0.0,
            net_pnl=None,
            max_loss=round(candidate.max_loss, 2),
            is_valid=False,
            validity_note="INVALID (Non-finite or negative execution assumptions)",
            entry_description="N/A",
            exit_description="N/A",
        )

    total_entry_cost = 0.0
    total_exit_value = 0.0
    total_contracts = 0
    invalid_reasons: list[str] = []

    for leg in candidate.legs:
        ratio = getattr(leg, "ratio_qty", getattr(leg, "ratio", 1))
        qty = ratio * candidate.quantity
        total_contracts += qty
        sym = leg.contract_symbol

        # Entry pricing: long pays ask, short receives bid
        leg_entry_px = float(getattr(leg, "entry_price_assumption", getattr(leg, "entry_price", 0.0)))
        is_buy = (leg.side.value.lower() == "buy") if hasattr(leg.side, "value") else (str(leg.side).lower() == "buy")

        if not math.isfinite(leg_entry_px) or leg_entry_px < 0.0:
            invalid_reasons.append(f"invalid entry price for {sym}")
            continue
        if is_buy:
            total_entry_cost += (leg_entry_px + slippage_per_contract) * qty * multiplier
        else:
            total_entry_cost -= max(0.0, leg_entry_px - slippage_per_contract) * qty * multiplier

        # Exit pricing from sealed quotes
        if sym not in exit_quotes:
            invalid_reasons.append(f"missing exit quote for {sym}")
            continue

        q_exit = exit_quotes[sym]
        bid_exit = float(q_exit.get("bid", 0.0))
        ask_exit = float(q_exit.get("ask", 0.0))

        if not (math.isfinite(bid_exit) and math.isfinite(ask_exit)):
            invalid_reasons.append(f"non-finite exit quote for {sym}")
            continue
        if bid_exit < 0.0 or ask_exit < 0.0 or bid_exit > ask_exit:
            invalid_reasons.append(f"crossed or negative exit quote for {sym}")
            continue

        if expected_exit_time is not None:
            raw_quote_time = q_exit.get("quote_time")
            if raw_quote_time is None:
                invalid_reasons.append(f"missing exit timestamp for {sym}")
                continue
            quote_time = (
                datetime.fromisoformat(raw_quote_time).astimezone(timezone.utc)
                if isinstance(raw_quote_time, str)
                else raw_quote_time.astimezone(timezone.utc)
            )
            if quote_time != expected_exit_time.astimezone(timezone.utc):
                invalid_reasons.append(f"exit timestamp mismatch for {sym}")
                continue

        if is_buy:
            # Long leg sells to close at bid
            total_exit_value += max(0.0, bid_exit - slippage_per_contract) * qty * multiplier
        else:
            # Short leg buys to close at ask
            total_exit_value -= (ask_exit + slippage_per_contract) * qty * multiplier

    # Total friction: 2 rounds of fees and slippage
    entry_exit_fees = total_contracts * fee_per_contract * 2.0
    total_friction = entry_exit_fees + (total_contracts * slippage_per_contract * 2.0 * multiplier)

    if invalid_reasons:
        return RealizedTradeResult(
            entry_cash_flow=round(total_entry_cost, 2),
            exit_cash_flow=0.0,
            total_friction=round(total_friction, 2),
            net_pnl=None,
            max_loss=round(candidate.max_loss, 2),
            is_valid=False,
            validity_note=f"INVALID ({'; '.join(invalid_reasons)})",
            entry_description=f"Entry Cash Flow: ${total_entry_cost:.2f}",
            exit_description="N/A",
        )

    # Net P&L = Exit Cash Flow - Entry Cash Flow - Entry/Exit Fees
    net_pnl = round(total_exit_value - total_entry_cost - entry_exit_fees, 2)

    entry_desc = f"Debit (${total_entry_cost:.2f})" if total_entry_cost > 0 else f"Credit (${abs(total_entry_cost):.2f})"
    exit_desc = f"Exit (${total_exit_value:.2f})" if total_exit_value > 0 else f"Cost (${abs(total_exit_value):.2f})"

    return RealizedTradeResult(
        entry_cash_flow=round(total_entry_cost, 2),
        exit_cash_flow=round(total_exit_value, 2),
        total_friction=round(total_friction, 2),
        net_pnl=net_pnl,
        max_loss=round(candidate.max_loss, 2),
        is_valid=True,
        validity_note="VALID",
        entry_description=entry_desc,
        exit_description=exit_desc,
    )
