"""Broker-authoritative account risk summary for entry gating and judge evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable


_OCC_SYMBOL = re.compile(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$")


@dataclass(frozen=True)
class BrokerRiskEnvelope:
    """Small, display-ready account truth derived from current broker positions."""

    mode: str
    starting_nav: float
    current_equity: float | None
    full_account_net_pnl: float | None
    full_account_return_pct: float | None
    broker_position_legs: int
    governed_position_legs: int
    orphan_position_legs: int
    underlying_symbols: list[str]
    gross_marked_exposure: float
    unrealized_pnl: float
    max_abs_contract_quantity: int
    orphan_contract_symbols: list[str]
    violations: list[str]


def _field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _underlying(symbol: str) -> str:
    match = _OCC_SYMBOL.fullmatch(symbol.upper().strip())
    return match.group(1) if match else symbol.upper().strip()


def build_broker_risk_envelope(
    *,
    positions: Iterable[Any],
    governed_contract_symbols: set[str],
    snapshot_verified: bool,
    starting_nav: float,
    current_equity: float | None,
    system_halted: bool,
    drawdown_halt_pct: float,
    max_contracts: int,
) -> BrokerRiskEnvelope:
    """Build one concise view of account P&L, exposure provenance, and entry mode."""
    position_rows = list(positions)
    symbols = [str(_field(position, "symbol", "")).upper().strip() for position in position_rows]
    orphan_symbols = sorted(symbol for symbol in symbols if symbol and symbol not in governed_contract_symbols)
    governed_count = sum(1 for symbol in symbols if symbol in governed_contract_symbols)
    gross_exposure = sum(abs(_finite_float(_field(position, "market_value"))) for position in position_rows)
    unrealized_pnl = sum(_finite_float(_field(position, "unrealized_pl")) for position in position_rows)
    max_quantity = max(
        (int(abs(_finite_float(_field(position, "qty")))) for position in position_rows),
        default=0,
    )

    verified_equity = (
        float(current_equity)
        if snapshot_verified
        and current_equity is not None
        and math.isfinite(float(current_equity))
        and float(current_equity) >= 0.0
        else None
    )
    account_pnl = round(verified_equity - starting_nav, 2) if verified_equity is not None else None
    account_return = (
        round(account_pnl / starting_nav * 100.0, 4)
        if account_pnl is not None and starting_nav > 0.0
        else None
    )
    drawdown = (
        max(0.0, (starting_nav - verified_equity) / starting_nav)
        if verified_equity is not None and starting_nav > 0.0
        else 0.0
    )

    violations: list[str] = []
    if not snapshot_verified or verified_equity is None:
        violations.append("UNVERIFIED_BROKER_SNAPSHOT")
    if system_halted:
        violations.append("SYSTEM_HALT_ACTIVE")
    if orphan_symbols:
        violations.append("UNTRACKED_BROKER_EXPOSURE")
    if drawdown > drawdown_halt_pct:
        violations.append("ACCOUNT_DRAWDOWN_LIMIT")
    if max_quantity > max_contracts:
        violations.append("CONTRACT_QUANTITY_LIMIT")

    if "UNVERIFIED_BROKER_SNAPSHOT" in violations:
        mode = "UNVERIFIED"
    elif violations:
        mode = "LIQUIDATE_ONLY"
    else:
        mode = "NORMAL"

    return BrokerRiskEnvelope(
        mode=mode,
        starting_nav=float(starting_nav),
        current_equity=verified_equity,
        full_account_net_pnl=account_pnl,
        full_account_return_pct=account_return,
        broker_position_legs=len(position_rows),
        governed_position_legs=governed_count,
        orphan_position_legs=len(orphan_symbols),
        underlying_symbols=sorted({_underlying(symbol) for symbol in symbols if symbol}),
        gross_marked_exposure=round(gross_exposure, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        max_abs_contract_quantity=max_quantity,
        orphan_contract_symbols=orphan_symbols,
        violations=violations,
    )
