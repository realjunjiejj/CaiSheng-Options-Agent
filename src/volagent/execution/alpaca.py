"""Alpaca paper trading options adapter, explicit local simulator, and broker reconciliation."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any, Mapping
import uuid


from volagent.domain.enums import BrokerTarget, Decision, ExecutionStatus, NetPriceConvention, OptionType, OrderSide, PositionIntent
from volagent.domain.execution import ApprovedLegSnapshot, ExecutionReceipt, OrderPlan, VerifiedStrategyPositionSnapshot
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import BrokerExecutionError, ExecutionError
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.mapper import extract_fill_metrics, map_broker_status


def parse_occ_underlying(contract_symbol: str) -> str:
    """Extract clean underlying ticker from OCC option symbol (e.g. NVDA240823C00125000 -> NVDA)."""
    if len(contract_symbol) >= 16:
        root = contract_symbol[:-15]
        if root:
            return root.strip()
    return contract_symbol.split("-")[0][:6].strip()


def normalize_broker_position_side(raw_side: Any) -> str:
    """Normalize Alpaca SDK enums and serialized enum strings to long/short."""
    value = getattr(raw_side, "value", raw_side)
    side = str(value or "").strip().lower().split(".")[-1]
    if side not in {"long", "short"}:
        raise ExecutionError(f"Unrecognized broker position side: {raw_side!r}")
    return side


def compute_order_fingerprint(payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 fingerprint over complete decision and order parameters."""
    canonical_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_logical_exposure_key(
    event_id: str,
    symbol: str,
    decision: str,
    legs: list[Any],
    purpose: str = "entry",
    strategy_id: str | None = None,
    mandate_version: str = "caisheng-mandate-v1",
) -> str:
    """Compute canonical SHA-256 logical exposure key.

    Does NOT include limit price, quote timestamp, or random client order ID.
    Blocks duplicate exposure across repricing while an intent is active or open.
    """
    sorted_legs = sorted(
        [
            {
                "contract_symbol": l.contract_symbol if hasattr(l, "contract_symbol") else l["contract_symbol"],
                "side": l.side.value if hasattr(l.side, "value") else str(l.side if hasattr(l, "side") else l["side"]),
                "ratio_qty": l.ratio_qty if hasattr(l, "ratio_qty") else l["ratio_qty"],
                "position_intent": l.position_intent.value if hasattr(l.position_intent, "value") else str(l.position_intent if hasattr(l, "position_intent") else l["position_intent"]),
            }
            for l in legs
        ],
        key=lambda x: x["contract_symbol"],
    )
    payload = {
        "event_id": event_id,
        "symbol": symbol,
        "decision": decision,
        "purpose": purpose,
        "strategy_id": strategy_id or "default_strategy",
        "mandate_version": mandate_version,
        "legs": sorted_legs,
    }
    canonical_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_economic_fingerprint(payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 economic fingerprint over strategy intent."""
    canonical_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def build_order_plan(
    candidate: StrategyCandidate,
    broker_target: BrokerTarget = BrokerTarget.SIMULATED_LOCAL,
    limit_improvement_fraction: float = 0.25,
    ledger: ExecutionLedger | None = None,
    contract_snapshots: Mapping[str, OptionContractSnapshot] | None = None,
    decision_id: str = "dec-default",
    event_id: str = "evt-default",
    model_version: str = "caisheng-1.0.0",
    mandate_version: str = "caisheng-mandate-v1",
    decision_time_bucket: str = "",
    risk_reservation_ref: str | None = None,
    quote_provenance_id: str | None = None,
    original_entry_intent_id: str | None = None,
) -> OrderPlan:
    """Construct an immutable fingerprinted OrderPlan and register it in the transactional ledger."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)
    client_order_id = f"volagent-{uuid.uuid4().hex[:12]}"
    approval_token = f"tok-{uuid.uuid4().hex[:16]}"
    dt_bucket = decision_time_bucket or now.strftime("%Y-%m-%dT%H:%M:00Z")

    symbol = parse_occ_underlying(candidate.legs[0].contract_symbol) if candidate.legs else "UNKNOWN"
    convention = NetPriceConvention.DEBIT if candidate.decision == Decision.LONG_STRADDLE else NetPriceConvention.CREDIT

    approved_legs = []
    for leg in candidate.legs:
        snapshot = (contract_snapshots or {}).get(leg.contract_symbol)
        if broker_target == BrokerTarget.ALPACA_PAPER and snapshot is None:
            raise ExecutionError(f"Live paper order requires an immutable quote snapshot for {leg.contract_symbol}.")
        if snapshot is not None:
            quote_time = snapshot.quote_time
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=timezone.utc)
            quote_age = (now - quote_time.astimezone(timezone.utc)).total_seconds()
            if (
                snapshot.symbol != leg.contract_symbol
                or snapshot.underlying_symbol != symbol
                or snapshot.strike != leg.strike
                or snapshot.expiration != leg.expiration
                or snapshot.expiration < now.date()
                or snapshot.bid <= 0
                or snapshot.ask < snapshot.bid
                or not math.isfinite(snapshot.bid)
                or not math.isfinite(snapshot.ask)
                or quote_age < -2.0
                or quote_age > 1800.0
            ):
                raise ExecutionError(f"Invalid immutable quote snapshot for {leg.contract_symbol}.")
        opt_type = OptionType.CALL if leg.option_type == "call" else OptionType.PUT
        side = OrderSide.BUY if leg.side == "buy" else OrderSide.SELL
        intent = PositionIntent(leg.position_intent)
        approved_legs.append(
            ApprovedLegSnapshot(
                contract_symbol=leg.contract_symbol,
                underlying_symbol=symbol,
                option_type=opt_type,
                strike=leg.strike,
                expiration=leg.expiration,
                side=side,
                ratio_qty=leg.ratio_qty,
                position_intent=intent,
                bid=snapshot.bid if snapshot else max(0.01, leg.entry_price_assumption - 0.10),
                ask=snapshot.ask if snapshot else leg.entry_price_assumption + 0.10,
                multiplier=snapshot.multiplier if snapshot else 100,
                vendor_implied_vol=snapshot.vendor_implied_vol if (snapshot and snapshot.vendor_implied_vol is not None) else 0.60,
                vendor_delta=snapshot.vendor_delta if (snapshot and snapshot.vendor_delta is not None) else (getattr(leg, "delta", None) or 0.50),
                quote_time=snapshot.quote_time if snapshot else now,
                entry_price_assumption=leg.entry_price_assumption,
            )
        )


    limit_px = abs(candidate.entry_debit_credit) / (candidate.quantity * 100.0) if candidate.quantity > 0 else 1.0
    dec_str = candidate.decision.value if hasattr(candidate.decision, "value") else str(candidate.decision)

    # 1. Logical exposure key (blocks duplicate exposure across repricing)
    logical_key = compute_logical_exposure_key(
        event_id=event_id,
        symbol=symbol,
        decision=dec_str,
        legs=approved_legs,
        purpose="entry",
        strategy_id=candidate.strategy_id,
        mandate_version=mandate_version,
    )

    # 2. Economic payload
    economic_payload = {
        "symbol": symbol,
        "decision": dec_str,
        "quantity": candidate.quantity,
        "net_price_convention": convention.value,
        "limit_price": round(limit_px, 2),
        "strategy_id": candidate.strategy_id,
        "legs": [
            {
                "contract_symbol": l.contract_symbol,
                "side": l.side.value if hasattr(l.side, "value") else str(l.side),
                "ratio_qty": l.ratio_qty,
                "position_intent": l.position_intent.value if hasattr(l.position_intent, "value") else str(l.position_intent),
            }
            for l in approved_legs
        ],
    }
    economic_fp = compute_economic_fingerprint(economic_payload)

    # 3. Exact execution fingerprint
    fingerprint_payload = {
        "client_order_id": client_order_id,
        "symbol": symbol,
        "decision": dec_str,
        "quantity": candidate.quantity,
        "net_price_convention": convention.value,
        "limit_price": round(limit_px, 2),
        "legs": [l.model_dump(mode="json") for l in approved_legs],
        "broker_target": broker_target.value,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "max_loss": candidate.max_loss,
        "logical_exposure_key": logical_key,
        "decision_id": decision_id,
        "event_id": event_id,
        "model_version": model_version,
        "mandate_version": mandate_version,
    }
    fp = compute_order_fingerprint(fingerprint_payload)

    plan = OrderPlan(
        client_order_id=client_order_id,
        approval_token=approval_token,
        symbol=symbol,
        decision=dec_str,
        quantity=candidate.quantity,
        net_price_convention=convention,
        limit_price=round(limit_px, 2),
        legs=approved_legs,
        fingerprint=fp,
        economic_fingerprint=economic_fp,
        logical_exposure_key=logical_key,
        execution_fingerprint=fp,
        strategy_id=candidate.strategy_id,
        decision_id=decision_id,
        event_id=event_id,
        model_version=model_version,
        mandate_version=mandate_version,
        decision_time_bucket=dt_bucket,
        risk_reservation_ref=risk_reservation_ref,
        quote_provenance_id=quote_provenance_id,
        original_entry_intent_id=original_entry_intent_id,
        broker_target=broker_target,
        created_at=now,
        expires_at=expires_at,
        max_loss_dollars=candidate.max_loss,
        estimated_cost_dollars=abs(candidate.entry_debit_credit),
    )

    # Register in ledger with atomic duplicate prevention and full order plan persistence
    ledger_inst = ledger or ExecutionLedger()
    ledger_inst.register_preview(
        fingerprint=fp,
        logical_exposure_key=logical_key,
        economic_fingerprint=economic_fp,
        client_order_id=client_order_id,
        approval_token=approval_token,
        broker_target=broker_target.value,
        symbol=symbol,
        quantity=candidate.quantity,
        limit_price=round(limit_px, 2),
        expires_at=expires_at,
        strategy_id=candidate.strategy_id,
        decision_id=decision_id,
        event_id=event_id,
        model_version=model_version,
        mandate_version=mandate_version,
        decision_time_bucket=dt_bucket,
        full_order_plan=plan.model_dump(mode="json"),
    )

    return plan


def build_closing_order_plan(
    candidate: StrategyCandidate | None = None,
    entry_plan: OrderPlan | None = None,
    contract_snapshots: Mapping[str, OptionContractSnapshot] | None = None,
    verified_positions: VerifiedStrategyPositionSnapshot | list[dict[str, Any]] | None = None,
    net_closing_limit_price: float | None = None,
    broker_target: BrokerTarget = BrokerTarget.SIMULATED_LOCAL,
    limit_improvement_fraction: float = 0.25,
    ledger: ExecutionLedger | None = None,
    decision_id: str = "dec-close-default",
    event_id: str = "evt-close-default",
    model_version: str = "caisheng-1.0.0",
    mandate_version: str = "caisheng-mandate-v1",
    original_entry_intent_id: str | None = None,
) -> OrderPlan:
    """Construct an atomic multi-leg closing OrderPlan verified against broker positions."""
    if entry_plan is not None:
        original_entry_intent_id = original_entry_intent_id or entry_plan.client_order_id
        if event_id == "evt-close-default":
            event_id = entry_plan.event_id
        if model_version == "caisheng-1.0.0":
            model_version = entry_plan.model_version
        if mandate_version == "caisheng-mandate-v1":
            mandate_version = entry_plan.mandate_version
    if candidate is None:
        from volagent.domain.strategies import OptionLeg, StrategyCandidate
        legs = []
        for l in entry_plan.legs:
            side_str = "buy" if l.side == OrderSide.BUY else "sell"
            opt_str = "call" if l.option_type == OptionType.CALL else "put"
            legs.append(
                OptionLeg(
                    contract_symbol=l.contract_symbol,
                    strike=l.strike,
                    expiration=l.expiration,
                    option_type=opt_str,
                    side=side_str,
                    position_intent="buy_to_open" if side_str == "buy" else "sell_to_open",
                    ratio_qty=l.ratio_qty,
                    entry_price_assumption=l.entry_price_assumption or (l.bid + l.ask) / 2.0,
                )
            )
        candidate = StrategyCandidate(
            strategy_id=entry_plan.strategy_id or entry_plan.approval_token or "strategy-default",
            decision=Decision.LONG_STRADDLE if entry_plan.net_price_convention == NetPriceConvention.DEBIT else Decision.SHORT_IRON_BUTTERFLY,
            legs=legs,
            quantity=entry_plan.quantity,
            entry_debit_credit=entry_plan.limit_price if entry_plan.net_price_convention == NetPriceConvention.DEBIT else -entry_plan.limit_price,
            max_loss=entry_plan.max_loss_dollars,
            expected_pnl=0.0,
            risk_adjusted_score=1.0,
        )


    # Mandatory broker verification for live paper closes
    if broker_target == BrokerTarget.ALPACA_PAPER and verified_positions is None:
        raise ExecutionError("Live paper close order requires verified broker position snapshot.")


    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)
    client_order_id = f"volagent-close-{uuid.uuid4().hex[:10]}"
    approval_token = f"tok-close-{uuid.uuid4().hex[:14]}"

    symbol = parse_occ_underlying(candidate.legs[0].contract_symbol) if candidate.legs else "UNKNOWN"

    # Normalize verified positions
    pos_map: dict[str, dict[str, Any]] = {}
    if verified_positions is not None:
        if isinstance(verified_positions, VerifiedStrategyPositionSnapshot):
            pos_map = {p.contract_symbol: {"symbol": p.contract_symbol, "qty": p.qty, "side": normalize_broker_position_side(p.side)} for p in verified_positions.positions}
        elif isinstance(verified_positions, list):
            for p in verified_positions:
                sym = p.get("symbol") or p.get("contract_symbol")
                pos_map[sym] = {"symbol": sym, "qty": abs(int(p.get("qty", 0))), "side": normalize_broker_position_side(p.get("side"))}

    # Validate verified positions against strategy candidate
    effective_closing_qty = candidate.quantity
    if verified_positions is not None:
        unit_counts = []
        for leg in candidate.legs:
            if leg.contract_symbol not in pos_map:
                raise ExecutionError(f"Cannot build closing plan: broker does not hold verified position for {leg.contract_symbol}.")
            v_pos = pos_map[leg.contract_symbol]
            v_side = v_pos["side"]
            v_qty = v_pos["qty"]

            # Validate broker side against strategy leg side
            if leg.side == "buy":
                if v_side != "long":
                    raise ExecutionError(f"Broker position side '{v_side}' for {leg.contract_symbol} does not match expected long strategy leg.")
            else:
                if v_side != "short":
                    raise ExecutionError(f"Broker position side '{v_side}' for {leg.contract_symbol} does not match expected short strategy leg.")

            avail_units = v_qty // leg.ratio_qty
            if avail_units <= 0:
                raise ExecutionError(f"Cannot build closing plan: verified position quantity for {leg.contract_symbol} is 0.")
            unit_counts.append(avail_units)

        # Check ratio consistency across legs (fail closed if ratios mismatch)
        if len(set(unit_counts)) > 1:
            raise ExecutionError(
                f"Mismatched leg ratios in verified broker positions: {unit_counts}. Partial fills must be symmetric across legs to close."
            )
        effective_closing_qty = min(effective_closing_qty, unit_counts[0])

    if effective_closing_qty <= 0:
        raise ExecutionError("Cannot build closing plan with quantity <= 0 after position verification.")

    closing_legs: list[ApprovedLegSnapshot] = []
    total_exit_cashflow_per_unit = 0.0

    for leg in candidate.legs:
        snapshot = (contract_snapshots or {}).get(leg.contract_symbol)
        if broker_target == BrokerTarget.ALPACA_PAPER and snapshot is None:
            raise ExecutionError(f"Live paper close order requires an immutable quote snapshot for {leg.contract_symbol}.")
        if snapshot is not None:
            quote_time = snapshot.quote_time
            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=timezone.utc)
            quote_age = (now - quote_time.astimezone(timezone.utc)).total_seconds()
            if (
                snapshot.symbol != leg.contract_symbol
                or snapshot.underlying_symbol != symbol
                or snapshot.strike != leg.strike
                or snapshot.expiration != leg.expiration
                or snapshot.expiration < now.date()
                or snapshot.bid <= 0
                or snapshot.ask < snapshot.bid
                or not math.isfinite(snapshot.bid)
                or not math.isfinite(snapshot.ask)
                or quote_age < -2.0
                or quote_age > 1800.0
            ):
                raise ExecutionError(f"Invalid immutable quote snapshot for closing leg {leg.contract_symbol}.")

        bid_px = snapshot.bid if snapshot else max(0.01, leg.entry_price_assumption - 0.10)
        ask_px = snapshot.ask if snapshot else leg.entry_price_assumption + 0.10
        opt_type = OptionType.CALL if leg.option_type == "call" else OptionType.PUT

        if leg.side == "buy":
            close_side = OrderSide.SELL
            close_intent = PositionIntent.SELL_TO_CLOSE
            leg_exit_price = bid_px
            total_exit_cashflow_per_unit += leg_exit_price * leg.ratio_qty
        else:
            close_side = OrderSide.BUY
            close_intent = PositionIntent.BUY_TO_CLOSE
            leg_exit_price = ask_px
            total_exit_cashflow_per_unit -= leg_exit_price * leg.ratio_qty

        closing_legs.append(
            ApprovedLegSnapshot(
                contract_symbol=leg.contract_symbol,
                underlying_symbol=symbol,
                option_type=opt_type,
                strike=leg.strike,
                expiration=leg.expiration,
                side=close_side,
                ratio_qty=leg.ratio_qty,
                position_intent=close_intent,
                bid=bid_px,
                ask=ask_px,
                multiplier=snapshot.multiplier if snapshot else 100,
                vendor_implied_vol=snapshot.vendor_implied_vol if (snapshot and snapshot.vendor_implied_vol is not None) else 0.60,
                vendor_delta=snapshot.vendor_delta if (snapshot and snapshot.vendor_delta is not None) else (getattr(leg, "delta", None) or 0.50),
                quote_time=snapshot.quote_time if snapshot else now,
                entry_price_assumption=leg_exit_price,
            )
        )


    if net_closing_limit_price is not None and broker_target == BrokerTarget.SIMULATED_LOCAL:
        if not math.isfinite(net_closing_limit_price) or net_closing_limit_price <= 0:
            raise ExecutionError("Simulated close mark must be finite and positive.")
        convention = (
            NetPriceConvention.CREDIT
            if candidate.decision == Decision.LONG_STRADDLE
            else NetPriceConvention.DEBIT
        )
        limit_px = net_closing_limit_price
    elif total_exit_cashflow_per_unit >= 0:
        convention = NetPriceConvention.CREDIT
        limit_px = max(0.01, total_exit_cashflow_per_unit)
    else:
        convention = NetPriceConvention.DEBIT
        limit_px = max(0.01, abs(total_exit_cashflow_per_unit))

    decision_name = f"close_{candidate.decision.value if hasattr(candidate.decision, 'value') else str(candidate.decision)}"

    # Logical exposure key for close
    logical_key = compute_logical_exposure_key(
        event_id=event_id,
        symbol=symbol,
        decision=decision_name,
        legs=closing_legs,
        purpose="close",
        strategy_id=candidate.strategy_id,
        mandate_version=mandate_version,
    )

    economic_payload = {
        "symbol": symbol,
        "decision": decision_name,
        "quantity": effective_closing_qty,
        "net_price_convention": convention.value,
        "limit_price": round(limit_px, 2),
        "strategy_id": candidate.strategy_id,
        "legs": [
            {
                "contract_symbol": l.contract_symbol,
                "side": l.side.value if hasattr(l.side, "value") else str(l.side),
                "ratio_qty": l.ratio_qty,
                "position_intent": l.position_intent.value if hasattr(l.position_intent, "value") else str(l.position_intent),
            }
            for l in closing_legs
        ],
    }
    economic_fp = compute_economic_fingerprint(economic_payload)

    fingerprint_payload = {
        "client_order_id": client_order_id,
        "symbol": symbol,
        "decision": decision_name,
        "quantity": effective_closing_qty,
        "net_price_convention": convention.value,
        "limit_price": round(limit_px, 2),
        "legs": [l.model_dump(mode="json") for l in closing_legs],
        "broker_target": broker_target.value,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "max_loss": candidate.max_loss,
        "logical_exposure_key": logical_key,
        "decision_id": decision_id,
        "event_id": event_id,
        "model_version": model_version,
        "mandate_version": mandate_version,
    }
    fp = compute_order_fingerprint(fingerprint_payload)

    plan = OrderPlan(
        client_order_id=client_order_id,
        approval_token=approval_token,
        symbol=symbol,
        decision=decision_name,
        quantity=effective_closing_qty,
        net_price_convention=convention,
        limit_price=round(limit_px, 2),
        legs=closing_legs,
        fingerprint=fp,
        economic_fingerprint=economic_fp,
        logical_exposure_key=logical_key,
        execution_fingerprint=fp,
        strategy_id=candidate.strategy_id,
        decision_id=decision_id,
        event_id=event_id,
        model_version=model_version,
        mandate_version=mandate_version,
        original_entry_intent_id=original_entry_intent_id,
        broker_target=broker_target,
        created_at=now,
        expires_at=expires_at,
        max_loss_dollars=candidate.max_loss,
        estimated_cost_dollars=round(limit_px * effective_closing_qty * 100.0, 2),
    )

    ledger_inst = ledger or ExecutionLedger()
    ledger_inst.register_preview(
        fingerprint=fp,
        logical_exposure_key=logical_key,
        economic_fingerprint=economic_fp,
        client_order_id=client_order_id,
        approval_token=approval_token,
        broker_target=broker_target.value,
        symbol=symbol,
        quantity=effective_closing_qty,
        limit_price=round(limit_px, 2),
        expires_at=expires_at,
        strategy_id=candidate.strategy_id,
        decision_id=decision_id,
        event_id=event_id,
        model_version=model_version,
        mandate_version=mandate_version,
        full_order_plan=plan.model_dump(mode="json"),
    )
    return plan


def recompute_and_verify_plan_fingerprint(plan: OrderPlan) -> str:
    """Recompute fingerprint directly from submitted OrderPlan and verify against declared fingerprint."""
    payload = {
        "client_order_id": plan.client_order_id,
        "symbol": plan.symbol,
        "decision": plan.decision,
        "quantity": plan.quantity,
        "net_price_convention": plan.net_price_convention.value if hasattr(plan.net_price_convention, "value") else str(plan.net_price_convention),
        "limit_price": plan.limit_price,
        "legs": [l.model_dump(mode="json") for l in plan.legs],
        "broker_target": plan.broker_target.value if hasattr(plan.broker_target, "value") else str(plan.broker_target),
        "created_at": plan.created_at.isoformat() if hasattr(plan.created_at, "isoformat") else str(plan.created_at),
        "expires_at": plan.expires_at.isoformat() if hasattr(plan.expires_at, "isoformat") else str(plan.expires_at),
        "max_loss": plan.max_loss_dollars,
        "logical_exposure_key": plan.logical_exposure_key,
        "decision_id": plan.decision_id,
        "event_id": plan.event_id,
        "model_version": plan.model_version,
        "mandate_version": plan.mandate_version,
    }
    recomputed_fp = compute_order_fingerprint(payload)
    if recomputed_fp != plan.fingerprint:
        raise ExecutionError(
            f"Tampered order plan detected! Recomputed fingerprint '{recomputed_fp}' does not match plan fingerprint '{plan.fingerprint}'"
        )
    return recomputed_fp


class SimulatedPaperBroker:
    """Explicit simulated paper broker executing with identical safety invariants."""

    def __init__(self, ledger: ExecutionLedger | None = None):
        self.ledger = ledger or ExecutionLedger()

    def submit_simulated_order(self, plan: OrderPlan) -> ExecutionReceipt:
        """Execute simulated paper trade after consuming approval token and verifying fingerprint integrity."""
        if plan.broker_target != BrokerTarget.SIMULATED_LOCAL:
            raise ExecutionError(f"Cannot dispatch order to simulated broker: plan broker target is '{plan.broker_target}', expected 'SIMULATED_LOCAL'.")

        now = datetime.now(timezone.utc)

        if now > plan.expires_at:
            raise ExecutionError(f"Order plan {plan.client_order_id} expired at {plan.expires_at}")

        if plan.quantity <= 0:
            raise ExecutionError("Cannot execute order with quantity <= 0")

        recompute_and_verify_plan_fingerprint(plan)
        # Enforce legal transition PREVIEWED -> APPROVED -> INTENT_PERSISTED before lock
        self.ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
        self.ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

        sim_broker_order_id = f"sim-{uuid.uuid4().hex[:12]}"
        receipt = ExecutionReceipt(
            receipt_id=f"rec-{uuid.uuid4().hex[:12]}",
            client_order_id=plan.client_order_id,
            broker_order_id=sim_broker_order_id,
            broker_target=BrokerTarget.SIMULATED_LOCAL,
            status=ExecutionStatus.SIMULATED,
            submitted_at=now,
            filled_at=now,
            filled_quantity=plan.quantity,
            average_price=plan.limit_price,
            fingerprint=plan.fingerprint,
            logical_exposure_key=plan.logical_exposure_key,
            raw_broker_response={"simulation_mode": "local_replay_sandbox", "fill_model": "conservative_ask_bid"},
        )

        self.ledger.record_broker_result(
            plan.approval_token,
            ExecutionStatus.SIMULATED,
            broker_order_id=sim_broker_order_id,
            raw_response=receipt.raw_broker_response,
            filled_quantity=plan.quantity,
            average_price=plan.limit_price,
        )
        return receipt


class AlpacaPaperBroker:
    """Official Alpaca Level-3 Multi-Leg Options Paper Trading broker adapter with unknown reconciliation."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        ledger: ExecutionLedger | None = None,
        allow_order_submission: bool | None = None,
        paper: bool = True,
        settings: Any | None = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.ledger = ledger or ExecutionLedger()
        self.allow_order_submission = allow_order_submission
        self.paper = paper
        self.settings = settings
        self._trading_client = None

    def _get_trading_client(self):
        if self._trading_client is None:
            if not self.api_key or not self.secret_key:
                raise BrokerExecutionError("Alpaca credentials missing. Provide ALPACA_API_KEY and ALPACA_SECRET_KEY.")
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(self.api_key, self.secret_key, paper=self.paper)
        return self._trading_client

    def submit_paper_order(self, plan: OrderPlan) -> ExecutionReceipt:
        """Submit atomic multi-leg Level-3 options order to Alpaca Paper Trading through non-bypassable gateway."""
        # 1. Strict broker target validation
        if plan.broker_target != BrokerTarget.ALPACA_PAPER:
            raise ExecutionError(f"Cannot dispatch order to Alpaca paper broker: plan broker target is '{plan.broker_target}', expected 'ALPACA_PAPER'.")

        # 2. Config & Global Submission Switch Validation
        from volagent.config import load_config, MandateConfig
        from volagent.domain.enums import GateStatus, Decision
        from volagent.quant.portfolio_gate import evaluate_portfolio_gate
        from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter

        config = self.settings or load_config()
        # The process/.env kill switch is the authority.  A constructor flag
        # may further disable a broker instance, but must never turn a globally
        # disabled write path on (including from MCP or lifecycle code).
        instance_allows = self.allow_order_submission is not False
        is_submission_allowed = config.execution.allow_order_submission and instance_allows
        if not is_submission_allowed:
            self.ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message="Order submission blocked by allow_order_submission kill-switch sentinel")
            raise BrokerExecutionError("Order submission blocked: allow_order_submission kill switch is disabled (False).")

        is_paper = self.paper if self.paper is not None else config.alpaca_paper_trade
        if not is_paper:
            self.ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message="Live real-money trading is forbidden; alpaca_paper_trade must be True")
            raise BrokerExecutionError("Live money trading is disabled. alpaca_paper_trade must be True.")


        # 3. Detect risk-reducing close order
        is_close_order = all(
            leg.position_intent in (PositionIntent.BUY_TO_CLOSE, PositionIntent.SELL_TO_CLOSE)
            for leg in plan.legs
        ) if plan.legs else False

        # 4. System Halt check (permitted for risk-reducing closes, blocked for new entries)
        halted, halt_reason = self.ledger.is_system_halted()
        if halted and not is_close_order:
            raise BrokerExecutionError(f"Cannot submit paper order: System is currently HALTED for new entries. Reason: {halt_reason}")

        # 5. Broker/ledger reconciliation is a mandatory entry boundary.  It
        # catches exposure created outside this process before CaiSheng can add
        # another position. Risk-reducing closes remain available during a halt.
        if not is_close_order:
            from volagent.execution.reconciliation import (
                ReconciliationStatus,
                reconcile_broker_and_ledger,
            )

            reconciliation = reconcile_broker_and_ledger(self, self.ledger)
            if reconciliation.status != ReconciliationStatus.CLEAN:
                message = (
                    "Entry blocked by broker/ledger reconciliation: "
                    f"{reconciliation.status.value} "
                    f"({len(reconciliation.mismatches)} mismatch(es), "
                    f"report {reconciliation.reconciliation_id})."
                )
                self.ledger.record_broker_result(
                    plan.approval_token,
                    ExecutionStatus.REJECTED,
                    error_message=message,
                )
                raise BrokerExecutionError(message)

        # 6. Portfolio Mandate Gate validation (for new entry orders)
        if not is_close_order:
            portfolio_adapter = AlpacaPortfolioAdapter(api_key=self.api_key, secret_key=self.secret_key, paper=self.paper)
            try:
                portfolio_adapter._trading_client = self._get_trading_client()
            except Exception:
                pass
            snap = portfolio_adapter.fetch_portfolio_snapshot(ledger=self.ledger)
            if snap.is_stale or snap.equity <= 0:
                self.ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message="Stale or unauthenticated portfolio snapshot")
                raise BrokerExecutionError("Cannot submit entry order: Alpaca portfolio snapshot is stale or unauthenticated.")

            gate_report = evaluate_portfolio_gate(
                candidate=plan,
                decision=Decision.LONG_STRADDLE if plan.net_price_convention == NetPriceConvention.DEBIT else Decision.SHORT_IRON_BUTTERFLY,
                portfolio=snap,
                mandate_config=config.mandate if self.settings is not None else MandateConfig(),
                underlying_symbol=plan.symbol,
                is_paper_endpoint=True,
                ledger=self.ledger,
                is_close_order=False,
                candidate_risk_already_reserved=True,
            )

            if gate_report.overall_status != GateStatus.PASS:
                reasons = "; ".join(gate_report.rejection_reasons)
                self.ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message=f"Portfolio gate rejected: {reasons}")
                raise BrokerExecutionError(f"Rejected by Portfolio Mandate Gate: {reasons}")

        now = datetime.now(timezone.utc)

        if now > plan.expires_at:
            raise ExecutionError(f"Order plan {plan.client_order_id} has expired.")

        if plan.quantity <= 0:
            raise ExecutionError("Cannot execute order with quantity <= 0")

        if not plan.legs:
            raise ExecutionError("Cannot execute order with zero legs.")

        for leg in plan.legs:
            quote_age = (now - leg.quote_time).total_seconds()
            if quote_age < 0 or quote_age > 30:
                raise ExecutionError(f"Live paper order quote for {leg.contract_symbol} is stale or temporally invalid.")
            if leg.bid <= 0 or leg.ask < leg.bid or not math.isfinite(leg.bid) or not math.isfinite(leg.ask):
                raise ExecutionError(f"Live paper order quote for {leg.contract_symbol} is invalid or crossed.")

        if not math.isfinite(plan.limit_price) or plan.limit_price <= 0:
            raise ExecutionError(f"Invalid non-finite or non-positive limit price: {plan.limit_price}")

        recompute_and_verify_plan_fingerprint(plan)

        # Enforce legal transition APPROVED -> INTENT_PERSISTED -> SUBMITTING
        self.ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
        self.ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

        if not self.api_key or not self.secret_key:
            self.ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message="Missing Alpaca credentials")
            raise BrokerExecutionError("Alpaca credentials missing. Provide ALPACA_API_KEY and ALPACA_SECRET_KEY.")


        try:
            from alpaca.trading.enums import OrderSide as AlpacaOrderSide, PositionIntent as AlpacaPositionIntent, TimeInForce
            from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

            client = self._get_trading_client()

            intent_map = {
                PositionIntent.BUY_TO_OPEN: AlpacaPositionIntent.BUY_TO_OPEN,
                PositionIntent.SELL_TO_OPEN: AlpacaPositionIntent.SELL_TO_OPEN,
                PositionIntent.BUY_TO_CLOSE: AlpacaPositionIntent.BUY_TO_CLOSE,
                PositionIntent.SELL_TO_CLOSE: AlpacaPositionIntent.SELL_TO_CLOSE,
            }

            alpaca_legs = []
            for leg in plan.legs:
                side = AlpacaOrderSide.BUY if leg.side == OrderSide.BUY else AlpacaOrderSide.SELL
                intent = intent_map.get(leg.position_intent, AlpacaPositionIntent.BUY_TO_OPEN if side == AlpacaOrderSide.BUY else AlpacaPositionIntent.SELL_TO_OPEN)
                alpaca_legs.append(
                    OptionLegRequest(
                        symbol=leg.contract_symbol,
                        ratio_qty=leg.ratio_qty,
                        side=side,
                        position_intent=intent,
                    )
                )

            parent_side = AlpacaOrderSide.BUY if plan.net_price_convention == NetPriceConvention.DEBIT else AlpacaOrderSide.SELL
            req = LimitOrderRequest(
                # Alpaca identifies an mleg order exclusively through its option
                # legs and rejects an underlying parent symbol with HTTP 422.
                symbol=None,
                qty=plan.quantity,
                side=parent_side,
                time_in_force=TimeInForce.DAY,
                limit_price=plan.limit_price,
                order_class="mleg",
                legs=alpaca_legs,
                client_order_id=plan.client_order_id,
            )

            res = client.submit_order(req)
            broker_order_id = str(res.id)
            raw_resp = {"alpaca_status": str(res.status), "created_at": str(res.created_at), "order_id": broker_order_id}

            # Map status & fill metrics with centralized mapper
            status = map_broker_status(res.status)
            filled_qty, avg_px = extract_fill_metrics(res)

            receipt = ExecutionReceipt(
                receipt_id=f"rec-{uuid.uuid4().hex[:12]}",
                client_order_id=plan.client_order_id,
                broker_order_id=broker_order_id,
                broker_target=BrokerTarget.ALPACA_PAPER,
                status=status,
                submitted_at=now,
                filled_quantity=filled_qty,
                average_price=avg_px,
                fingerprint=plan.fingerprint,
                logical_exposure_key=plan.logical_exposure_key,
                raw_broker_response=raw_resp,
            )
            self.ledger.record_broker_result(plan.approval_token, status, broker_order_id=broker_order_id, raw_response=raw_resp, filled_quantity=filled_qty, average_price=avg_px)
            return receipt

        except Exception as e:
            # Mark state as UNKNOWN and immediately attempt reconciliation by client_order_id
            self.ledger.mark_unknown(plan.approval_token, error_message=str(e))
            try:
                reconciled = self.reconcile_order_by_client_order_id(plan.client_order_id)
                if reconciled is not None and reconciled.status in (ExecutionStatus.ACCEPTED, ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED):
                    return reconciled
            except Exception:
                pass
            raise BrokerExecutionError(
                f"Alpaca submission returned ambiguous result for client_order_id '{plan.client_order_id}'. "
                f"State marked UNKNOWN in ledger for reconciliation. Error: {str(e)}"
            ) from e

    def reconcile_order_by_client_order_id(self, client_order_id: str) -> ExecutionReceipt | None:
        """Reconcile broker state for a given client_order_id preserving original fingerprint."""
        order_rec = self.ledger.get_order_by_client_order_id(client_order_id)
        original_fp = order_rec["fingerprint"] if order_rec else ""
        orig_log_key = order_rec.get("logical_exposure_key", "") if order_rec else ""

        client = self._get_trading_client()
        try:
            order = client.get_order_by_client_id(client_order_id)
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "404" in err_str:
                self.ledger.record_recovery_attempt(client_order_id, error_message="Order not found on broker (404)")
                return ExecutionReceipt(
                    receipt_id=f"rec-{uuid.uuid4().hex[:12]}",
                    client_order_id=client_order_id,
                    broker_order_id="",
                    broker_target=BrokerTarget.ALPACA_PAPER,
                    status=ExecutionStatus.UNKNOWN,
                    submitted_at=datetime.now(timezone.utc),
                    filled_quantity=0,
                    average_price=None,
                    fingerprint=original_fp,
                    logical_exposure_key=orig_log_key,
                    rejection_reason="Order not yet found on broker (404). Kept UNKNOWN for subsequent reconciliation.",
                )
            raise

        mapped_status = map_broker_status(order.status)
        broker_order_id = str(order.id)
        filled_qty, avg_px = extract_fill_metrics(order)
        raw_resp = {"alpaca_status": str(order.status), "created_at": str(order.created_at), "order_id": broker_order_id}

        self.ledger.update_status_by_client_order_id(
            client_order_id=client_order_id,
            status=mapped_status,
            broker_order_id=broker_order_id,
            raw_response=raw_resp,
            filled_quantity=filled_qty,
            average_price=avg_px,
            evidence_id=broker_order_id,
        )

        return ExecutionReceipt(
            receipt_id=f"rec-{uuid.uuid4().hex[:12]}",
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            broker_target=BrokerTarget.ALPACA_PAPER,
            status=mapped_status,
            submitted_at=datetime.now(timezone.utc),
            filled_quantity=filled_qty,
            average_price=avg_px,
            fingerprint=original_fp,
            logical_exposure_key=orig_log_key,
            raw_broker_response=raw_resp,
        )

    def get_broker_account(self) -> dict[str, Any]:
        """Fetch real Alpaca paper account equity, cash, and buying power."""
        client = self._get_trading_client()
        acc = client.get_account()
        return {
            "account_number": str(acc.account_number),
            "status": str(acc.status),
            "currency": str(acc.currency),
            "equity": float(acc.equity or 0.0),
            "cash": float(acc.cash or 0.0),
            "buying_power": float(acc.buying_power or 0.0),
            "portfolio_value": float(acc.portfolio_value or 0.0),
            "last_equity": float(acc.last_equity or 0.0),
        }

    def get_broker_positions(self) -> list[dict[str, Any]]:
        """Fetch all open option and stock positions from Alpaca paper account."""
        client = self._get_trading_client()
        positions = client.get_all_positions()
        res = []
        for pos in positions:
            res.append({
                "symbol": str(pos.symbol),
                "qty": float(pos.qty or 0.0),
                "side": str(pos.side),
                "avg_entry_price": float(pos.avg_entry_price or 0.0),
                "current_price": float(pos.current_price or 0.0),
                "market_value": float(pos.market_value or 0.0),
                "unrealized_pl": float(pos.unrealized_pl or 0.0),
                "unrealized_plpc": float(pos.unrealized_plpc or 0.0),
            })
        return res

    def get_broker_orders(self, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent orders from Alpaca paper account."""
        from alpaca.trading.requests import GetOrdersRequest
        client = self._get_trading_client()
        req = GetOrdersRequest(status=status, limit=limit, nested=True)
        orders = client.get_orders(req)
        res = []
        for ord_obj in orders:
            res.append({
                "id": str(ord_obj.id),
                "client_order_id": str(ord_obj.client_order_id),
                "symbol": str(ord_obj.symbol),
                "qty": float(ord_obj.qty or 0.0),
                "filled_qty": float(ord_obj.filled_qty or 0.0),
                "side": str(ord_obj.side),
                "type": str(ord_obj.type),
                "status": str(ord_obj.status),
                "limit_price": float(ord_obj.limit_price) if ord_obj.limit_price is not None else None,
                "filled_avg_price": float(ord_obj.filled_avg_price) if getattr(ord_obj, "filled_avg_price", None) is not None else None,
                "legs": [str(l.id) for l in ord_obj.legs] if hasattr(ord_obj, "legs") and ord_obj.legs else [],
            })
        return res


def create_closing_order_service(

    candidate: StrategyCandidate | None = None,
    entry_plan: OrderPlan | None = None,
    broker: AlpacaPaperBroker | None = None,
    ledger: ExecutionLedger | None = None,
    contract_snapshots: Mapping[str, OptionContractSnapshot] | None = None,
    verified_positions: VerifiedStrategyPositionSnapshot | list[dict[str, Any]] | None = None,
    net_closing_limit_price: float | None = None,
    broker_target: BrokerTarget = BrokerTarget.ALPACA_PAPER,
) -> OrderPlan:
    """Non-UI service to query live broker positions, construct a verified snapshot, and build a closing OrderPlan."""
    ledger = ledger or ExecutionLedger()
    if verified_positions is None:
        if broker is None:
            raise ExecutionError("Cannot create closing order without a broker or verified positions.")
        raw_positions = broker.get_broker_positions()
        now = datetime.now(timezone.utc)
        from volagent.domain.execution import VerifiedPositionLeg

        pos_legs = []
        for p in raw_positions:
            pos_legs.append(
                VerifiedPositionLeg(
                    contract_symbol=p["symbol"],
                    symbol=parse_occ_underlying(p["symbol"]),
                    qty=abs(int(p["qty"])),
                    side=normalize_broker_position_side(p["side"]),
                    avg_entry_price=p.get("avg_entry_price", 0.0),
                )
            )

        strat_sym = "UNKNOWN"
        if candidate and candidate.legs:
            strat_sym = parse_occ_underlying(candidate.legs[0].contract_symbol)
        elif entry_plan and entry_plan.legs:
            strat_sym = entry_plan.symbol

        strat_id = (candidate.strategy_id if candidate else None) or (entry_plan.approval_token if entry_plan else "strategy-default")

        verified_positions = VerifiedStrategyPositionSnapshot(
            strategy_id=strat_id,
            symbol=strat_sym,
            timestamp=now,
            positions=pos_legs,
            evidence_source="alpaca_paper_account",
        )

    return build_closing_order_plan(
        candidate=candidate,
        entry_plan=entry_plan,
        contract_snapshots=contract_snapshots,
        verified_positions=verified_positions,
        net_closing_limit_price=net_closing_limit_price,
        broker_target=broker_target,
        ledger=ledger,
    )



def reconcile_due_unknown_orders(broker: AlpacaPaperBroker, ledger: ExecutionLedger, max_lookups: int = 10) -> list[ExecutionReceipt]:
    """Autonomous reconciliation loop for due UNKNOWN orders with deadline enforcement."""
    due_orders = ledger.get_due_unknown_orders(max_count=max_lookups)
    receipts: list[ExecutionReceipt] = []
    now = datetime.now(timezone.utc)

    for order_row in due_orders:
        client_order_id = order_row["client_order_id"]
        deadline_str = order_row.get("recovery_deadline")
        if deadline_str:
            deadline_dt = datetime.fromisoformat(deadline_str)
            if now > deadline_dt:
                # Deadline expired! Trip persistent system halt
                ledger.trip_system_halt(
                    reason=f"Reconciliation deadline expired for UNKNOWN order '{client_order_id}'",
                    evidence_id=client_order_id,
                )

        receipt = broker.reconcile_order_by_client_order_id(client_order_id)
        if receipt:
            receipts.append(receipt)

    return receipts
