"""Daily and real-time broker order and position reconciliation engine for CaiSheng."""

from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from volagent.domain.enums import ExecutionStatus
from volagent.execution.alpaca import AlpacaPaperBroker
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.mapper import extract_fill_metrics, map_broker_status


class ReconciliationStatus(str, Enum):
    CLEAN = "CLEAN"
    WARNING = "WARNING"
    HALTED = "HALTED"


class ReconciliationMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mismatch_type: str
    symbol: str
    contract_symbol: str | None = None
    broker_value: Any = None
    ledger_value: Any = None
    description: str


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reconciliation_id: str
    status: ReconciliationStatus
    timestamp: datetime
    matched_orders_count: int = 0
    matched_positions_count: int = 0
    orphan_broker_orders: list[dict[str, Any]] = Field(default_factory=list)
    orphan_broker_positions: list[dict[str, Any]] = Field(default_factory=list)
    orphan_ledger_positions: list[dict[str, Any]] = Field(default_factory=list)
    mismatches: list[ReconciliationMismatch] = Field(default_factory=list)
    resolved_unknown_orders: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_unknown_orders: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None


_TERMINAL_BROKER_ORDER_STATUSES = {
    "canceled",
    "expired",
    "filled",
    "rejected",
    "replaced",
    "stopped",
}


def _normalized_enum_text(value: Any) -> str:
    """Normalize SDK enums and plain strings such as PositionSide.SHORT."""
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower().split(".")[-1]


def _is_active_broker_order(order: dict[str, Any]) -> bool:
    """Treat unknown/nonterminal statuses as active so reconciliation fails closed."""
    return _normalized_enum_text(order.get("status")) not in _TERMINAL_BROKER_ORDER_STATUSES


def _signed_position_quantity(position: dict[str, Any]) -> float:
    """Return broker quantity with one canonical sign, never double-negating SDK qty."""
    quantity = float(position.get("qty", 0.0))
    if not math.isfinite(quantity):
        raise ValueError("Broker position quantity must be finite")
    side = _normalized_enum_text(position.get("side"))
    if side == "long":
        return abs(quantity)
    if side == "short":
        return -abs(quantity)
    raise ValueError(f"Unrecognized broker position side: {position.get('side')!r}")


def reconcile_broker_and_ledger(
    alpaca_broker: AlpacaPaperBroker,
    ledger: ExecutionLedger,
) -> ReconciliationReport:
    """Perform exhaustive, two-way reconciliation between Alpaca paper broker state and SQLite ledger."""
    now = datetime.now(timezone.utc)
    rec_id = f"rec-{uuid.uuid4().hex[:10]}"
    mismatches: list[ReconciliationMismatch] = []
    resolved_unknowns: list[dict[str, Any]] = []
    unresolved_unknowns: list[dict[str, Any]] = []
    orphan_broker_orders: list[dict[str, Any]] = []

    try:
        broker_orders = alpaca_broker.get_broker_orders(status="all", limit=100)
        broker_positions = alpaca_broker.get_broker_positions()
    except Exception as e:
        report = ReconciliationReport(
            reconciliation_id=rec_id,
            status=ReconciliationStatus.HALTED,
            timestamp=now,
            error_message=f"Failed to query broker state: {str(e)}",
        )
        ledger.trip_system_halt(reason=f"Broker query failure during reconciliation: {str(e)}", evidence_id=rec_id)
        ledger.persist_reconciliation_report(rec_id, report.status.value, 0, 0, report.model_dump(mode="json"))
        return report

    broker_orders_by_client_id = {o["client_order_id"]: o for o in broker_orders if o.get("client_order_id")}
    broker_positions_by_symbol = {p["symbol"]: p for p in broker_positions if p.get("symbol")}

    active_orders = ledger.list_active_orders()
    matched_orders = 0

    # 1. Check for Orphan Broker Orders (Broker orders not tracked in CaiSheng ledger)
    for bo in broker_orders:
        # Historical terminal orders remain useful audit evidence, but cannot
        # create live exposure. Positions below are the authority for filled
        # exposure, so closed orders must not permanently halt the system.
        if not _is_active_broker_order(bo):
            continue
        c_id = bo.get("client_order_id")
        if not c_id:
            orphan_broker_orders.append(bo)
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="ORPHAN_BROKER_ORDER",
                    symbol=bo.get("symbol", "UNKNOWN"),
                    description=f"Broker order {bo.get('id')} has no client_order_id and is not tracked in ledger.",
                )
            )
        else:
            ledger_rec = ledger.get_order_by_client_order_id(c_id)
            if not ledger_rec:
                orphan_broker_orders.append(bo)
                mismatches.append(
                    ReconciliationMismatch(
                        mismatch_type="ORPHAN_BROKER_ORDER",
                        symbol=bo.get("symbol", "UNKNOWN"),
                        description=f"Broker order {bo.get('id')} (client_order_id: {c_id}) not found in ledger.",
                    )
                )

    # 2. Reconcile UNKNOWN and in-flight orders
    for act_order in active_orders:
        c_id = act_order["client_order_id"]
        status = act_order["status"]

        if status == ExecutionStatus.UNKNOWN.value:
            try:
                rec_receipt = alpaca_broker.reconcile_order_by_client_order_id(c_id)
                if rec_receipt and rec_receipt.status != ExecutionStatus.UNKNOWN:
                    resolved_unknowns.append({"client_order_id": c_id, "resolved_status": rec_receipt.status.value})
                else:
                    unresolved_unknowns.append({"client_order_id": c_id, "status": "still_unknown"})
            except Exception as e:
                unresolved_unknowns.append({"client_order_id": c_id, "error": str(e)})

        elif c_id in broker_orders_by_client_id:
            matched_orders += 1
            bo = broker_orders_by_client_id[c_id]
            mapped_status = map_broker_status(bo.get("status"))
            filled_qty, avg_px = extract_fill_metrics(bo)

            if mapped_status != ExecutionStatus(status):
                ledger.update_status_by_client_order_id(
                    client_order_id=c_id,
                    status=mapped_status,
                    broker_order_id=bo.get("id"),
                    filled_quantity=filled_qty,
                    average_price=avg_px,
                    evidence_id=rec_id,
                )

    # 3. Reconcile Open Positions vs Ledger Open Strategies (Handling partial fills & shared contracts)
    open_ledger_orders = ledger.list_open_positions()
    expected_contracts: dict[str, dict[str, Any]] = {}

    for ord_rec in open_ledger_orders:
        plan_str = ord_rec.get("full_order_plan")
        if not plan_str:
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="CORRUPT_LEDGER_INTENT",
                    symbol=ord_rec["symbol"],
                    description=f"Ledger open position order {ord_rec['client_order_id']} lacks full_order_plan JSON.",
                )
            )
            continue

        try:
            plan_dict = json.loads(plan_str)
        except Exception as e:
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="CORRUPT_LEDGER_INTENT",
                    symbol=ord_rec["symbol"],
                    description=f"Corrupt full_order_plan JSON for order {ord_rec['client_order_id']}: {str(e)}",
                )
            )
            continue

        # Effective unit count: use actual filled_quantity if > 0, else quantity
        effective_units = ord_rec.get("filled_quantity", 0)
        if effective_units <= 0 and ord_rec["status"] == ExecutionStatus.FILLED.value:
            effective_units = ord_rec["quantity"]

        for leg in plan_dict.get("legs", []):
            c_sym = leg["contract_symbol"]
            qty = leg["ratio_qty"] * effective_units
            side = leg["side"].lower()
            expected_signed_qty = qty if side == "buy" else -qty

            if c_sym not in expected_contracts:
                expected_contracts[c_sym] = {
                    "contract_symbol": c_sym,
                    "underlying": ord_rec["symbol"],
                    "expected_qty": expected_signed_qty,
                    "client_order_ids": [ord_rec["client_order_id"]],
                }
            else:
                expected_contracts[c_sym]["expected_qty"] += expected_signed_qty
                expected_contracts[c_sym]["client_order_ids"].append(ord_rec["client_order_id"])

    matched_positions = 0
    orphan_broker_positions = []
    orphan_ledger_positions = []

    # Check broker positions against expected contracts
    for pos in broker_positions:
        sym = pos["symbol"]
        try:
            signed_pos_qty = _signed_position_quantity(pos)
        except (TypeError, ValueError) as exc:
            orphan_broker_positions.append(pos)
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="INVALID_BROKER_POSITION",
                    symbol=sym[:6].strip(),
                    contract_symbol=sym,
                    broker_value=pos.get("qty"),
                    description=f"Broker position {sym} cannot be normalized safely: {exc}",
                )
            )
            continue

        if sym in expected_contracts:
            exp_info = expected_contracts[sym]
            if abs(signed_pos_qty - exp_info["expected_qty"]) > 1e-4:
                mismatches.append(
                    ReconciliationMismatch(
                        mismatch_type="QUANTITY_MISMATCH",
                        symbol=exp_info["underlying"],
                        contract_symbol=sym,
                        broker_value=signed_pos_qty,
                        ledger_value=exp_info["expected_qty"],
                        description=f"Broker position quantity ({signed_pos_qty}) != ledger expected ({exp_info['expected_qty']}) for {sym}",
                    )
                )
            else:
                matched_positions += 1
        else:
            orphan_broker_positions.append(pos)
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="ORPHAN_BROKER_POSITION",
                    symbol=sym[:6].strip(),
                    contract_symbol=sym,
                    broker_value=signed_pos_qty,
                    ledger_value=0,
                    description=f"Broker holds position {sym} (qty {signed_pos_qty}) not tracked in ledger open strategies.",
                )
            )

    # Check for missing broker positions
    for c_sym, exp_info in expected_contracts.items():
        if c_sym not in broker_positions_by_symbol:
            orphan_ledger_positions.append(exp_info)
            mismatches.append(
                ReconciliationMismatch(
                    mismatch_type="ORPHAN_LEDGER_POSITION",
                    symbol=exp_info["underlying"],
                    contract_symbol=c_sym,
                    broker_value=0,
                    ledger_value=exp_info["expected_qty"],
                    description=f"Ledger expects open position {c_sym} (qty {exp_info['expected_qty']}) but broker holds 0.",
                )
            )

    # 4. Determine final reconciliation status
    if orphan_broker_orders or orphan_broker_positions or orphan_ledger_positions or mismatches:
        final_status = ReconciliationStatus.HALTED
        ledger.trip_system_halt(
            reason=f"System halted by reconciliation: {len(mismatches)} mismatches/orphans detected (report: {rec_id})",
            evidence_id=rec_id,
        )
    elif unresolved_unknowns:
        final_status = ReconciliationStatus.WARNING
    else:
        final_status = ReconciliationStatus.CLEAN

    report = ReconciliationReport(
        reconciliation_id=rec_id,
        status=final_status,
        timestamp=now,
        matched_orders_count=matched_orders,
        matched_positions_count=matched_positions,
        orphan_broker_orders=orphan_broker_orders,
        orphan_broker_positions=orphan_broker_positions,
        orphan_ledger_positions=orphan_ledger_positions,
        mismatches=mismatches,
        resolved_unknown_orders=resolved_unknowns,
        unresolved_unknown_orders=unresolved_unknowns,
    )

    ledger.persist_reconciliation_report(
        report_id=rec_id,
        status=final_status.value,
        matched_orders=matched_orders,
        matched_positions=matched_positions,
        report_dict=report.model_dump(mode="json"),
    )

    return report
