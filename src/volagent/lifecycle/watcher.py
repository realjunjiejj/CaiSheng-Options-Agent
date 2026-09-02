"""Order Watcher managing active order states, partial fills, deadline cancellations, and risk updates."""

from datetime import datetime, timezone
import json
import logging
from typing import Any

from volagent.domain.enums import Decision, ExecutionStatus
from volagent.domain.execution import OrderPlan
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.mapper import extract_fill_metrics, map_broker_status

logger = logging.getLogger(__name__)


class OrderWatcher:
    """Watches and advances pending and open broker orders against Alpaca Trading API."""

    def __init__(self, ledger: ExecutionLedger, trading_client: Any | None = None):
        self.ledger = ledger
        self.trading_client = trading_client

    def sync_active_orders(self) -> dict[str, int]:
        """Poll all non-terminal orders, query broker status, and transition ledger records."""
        for filled_close in self.ledger.list_filled_close_orders():
            self.finalize_filled_close(filled_close)
        active_orders = self.ledger.list_active_orders()
        counts = {"synced": 0, "filled": 0, "partially_filled": 0, "canceled": 0, "rejected": 0, "unknown": 0}

        if not self.trading_client or not active_orders:
            return counts

        for order_row in active_orders:
            client_order_id = order_row["client_order_id"]
            current_status = order_row["status"]
            fingerprint = order_row["fingerprint"]

            # Only query broker if order has reached at least submitting/accepted/partially_filled/unknown
            if current_status not in ["submitting", "accepted", "partially_filled", "unknown"]:
                continue

            try:
                broker_order = self.trading_client.get_order_by_client_id(client_order_id)
                if not broker_order:
                    continue

                raw_status = str(getattr(broker_order, "status", "unknown"))
                mapped_status = map_broker_status(raw_status)
                filled_qty, avg_price = extract_fill_metrics(broker_order)
                broker_order_id = str(getattr(broker_order, "id", ""))

                if mapped_status.value != current_status:
                    self.ledger.update_status_by_client_order_id(
                        client_order_id=client_order_id,
                        status=mapped_status,
                        broker_order_id=broker_order_id,
                        filled_quantity=filled_qty,
                        average_price=avg_price,
                        actor="order_watcher",
                        evidence_id=broker_order_id,
                    )

                if mapped_status == ExecutionStatus.FILLED:
                    filled_close = self.ledger.get_order_by_client_order_id(client_order_id)
                    if filled_close:
                        self.finalize_filled_close(filled_close)


                counts["synced"] += 1
                if mapped_status == ExecutionStatus.FILLED:
                    counts["filled"] += 1
                elif mapped_status == ExecutionStatus.PARTIALLY_FILLED:
                    counts["partially_filled"] += 1
                elif mapped_status == ExecutionStatus.CANCELED:
                    counts["canceled"] += 1
                elif mapped_status == ExecutionStatus.REJECTED:
                    counts["rejected"] += 1
                elif mapped_status == ExecutionStatus.UNKNOWN:
                    counts["unknown"] += 1

            except Exception as exc:
                logger.warning(f"Error syncing order {client_order_id}: {exc}")
                continue

        return counts

    def finalize_filled_close(self, close_row: dict[str, Any]) -> bool:
        """Finalize a filled close exactly once and close its linked entry."""
        try:
            close_plan = OrderPlan.model_validate(
                json.loads(close_row.get("full_order_plan") or "{}")
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Cannot finalize close %s: %s", close_row.get("client_order_id"), exc)
            return False
        entry_client_order_id = close_plan.original_entry_intent_id
        if not entry_client_order_id:
            return False
        entry_row = self.ledger.get_order_by_client_order_id(entry_client_order_id)
        if not entry_row:
            logger.error(
                "Cannot finalize close %s: linked entry %s is missing",
                close_plan.client_order_id,
                entry_client_order_id,
            )
            return False
        closable_entry_statuses = {
            ExecutionStatus.FILLED.value,
            ExecutionStatus.PARTIALLY_FILLED.value,
            ExecutionStatus.SIMULATED.value,
        }
        if entry_row.get("status") not in closable_entry_statuses:
            logger.error(
                "Cannot finalize close %s: linked entry %s has non-position state %s",
                close_plan.client_order_id,
                entry_client_order_id,
                entry_row.get("status"),
            )
            return False
        try:
            entry_plan = OrderPlan.model_validate(
                json.loads(entry_row.get("full_order_plan") or "{}")
            )
            entry_price = float(entry_row.get("average_price") or entry_plan.limit_price)
            exit_price = float(close_row.get("average_price") or close_plan.limit_price)
            quantity = int(close_row.get("filled_quantity") or close_plan.quantity)
            opened_at = datetime.fromisoformat(
                str(entry_row.get("filled_at") or entry_row["created_at"]).replace("Z", "+00:00")
            )
            closed_at = datetime.fromisoformat(
                str(close_row.get("filled_at") or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            )
            if not self.ledger.has_closed_trade_for_exit_order(close_plan.client_order_id):
                from volagent.lifecycle.reporters import ClosedTradeReporter

                ClosedTradeReporter(self.ledger).record_completed_trade(
                    strategy_id=entry_plan.strategy_id or entry_row.get("strategy_id") or "strategy-unknown",
                    symbol=entry_plan.symbol,
                    decision=Decision(entry_plan.decision),
                    event_id=entry_plan.event_id,
                    entry_order_id=entry_plan.client_order_id,
                    exit_order_id=close_plan.client_order_id,
                    quantity=quantity,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    fees_and_slippage=0.0,
                    opened_at=opened_at,
                    closed_at=closed_at,
                    max_loss_budget=entry_plan.max_loss_dollars,
                    raw_receipt={
                        "entry_broker_order_id": entry_row.get("broker_order_id"),
                        "exit_broker_order_id": close_row.get("broker_order_id"),
                    },
                )

            if entry_row.get("status") != ExecutionStatus.CLOSED.value:
                self.ledger.update_status_by_client_order_id(
                    client_order_id=entry_plan.client_order_id,
                    status=ExecutionStatus.CLOSED,
                    broker_order_id=entry_row.get("broker_order_id"),
                    filled_quantity=int(entry_row.get("filled_quantity") or entry_plan.quantity),
                    average_price=entry_price,
                    actor="order_watcher_close_finalizer",
                    evidence_id=close_row.get("broker_order_id"),
                )
            if close_row.get("status") != ExecutionStatus.CLOSED.value:
                self.ledger.update_status_by_client_order_id(
                    client_order_id=close_plan.client_order_id,
                    status=ExecutionStatus.CLOSED,
                    broker_order_id=close_row.get("broker_order_id"),
                    filled_quantity=quantity,
                    average_price=exit_price,
                    actor="order_watcher_close_finalizer",
                    evidence_id=close_row.get("broker_order_id"),
                )
            return True
        except Exception as exc:
            logger.error("Failed to finalize close %s: %s", close_plan.client_order_id, exc)
            return False

    def cancel_expired_entry_orders(
        self, current_time: datetime | None = None
    ) -> list[str]:
        """Cancel expired, non-terminal entry intents and return confirmed cancellations."""
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        canceled: list[str] = []
        for order_row in self.ledger.list_active_orders():
            try:
                plan = OrderPlan.model_validate(
                    json.loads(order_row.get("full_order_plan") or "{}")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if plan.original_entry_intent_id or all(
                leg.position_intent.value.endswith("to_close") for leg in plan.legs
            ):
                continue
            expires_at = plan.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now.astimezone(timezone.utc) <= expires_at.astimezone(timezone.utc):
                continue
            if (
                order_row.get("status") == ExecutionStatus.PARTIALLY_FILLED.value
                and "unfilled remainder canceled" in str(order_row.get("error_message") or "")
            ):
                continue
            if self.cancel_unfilled_order_at_cutoff(
                plan.client_order_id,
                reason=f"Entry intent expired at {expires_at.isoformat()}",
            ):
                canceled.append(plan.client_order_id)
        return canceled

    def cancel_open_entry_orders(self, reason: str) -> list[str]:
        """Cancel every broker-working entry before risk-reducing halt actions."""
        canceled: list[str] = []
        working_statuses = {
            ExecutionStatus.SUBMITTING.value,
            ExecutionStatus.ACCEPTED.value,
            ExecutionStatus.PARTIALLY_FILLED.value,
            ExecutionStatus.UNKNOWN.value,
        }
        for order_row in self.ledger.list_active_orders():
            if order_row.get("status") not in working_statuses:
                continue
            try:
                plan = OrderPlan.model_validate(
                    json.loads(order_row.get("full_order_plan") or "{}")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if plan.original_entry_intent_id or all(
                leg.position_intent.value.endswith("to_close") for leg in plan.legs
            ):
                continue
            if (
                order_row.get("status") == ExecutionStatus.PARTIALLY_FILLED.value
                and "unfilled remainder canceled" in str(order_row.get("error_message") or "")
            ):
                continue
            if self.cancel_unfilled_order_at_cutoff(plan.client_order_id, reason=reason):
                canceled.append(plan.client_order_id)
        return canceled

    def cancel_unfilled_order_at_cutoff(self, client_order_id: str, reason: str = "Entry cutoff reached") -> bool:
        """Request broker cancellation of an open unfilled order at cutoff."""
        order = self.ledger.get_order_by_client_order_id(client_order_id)
        if not order:
            return False

        current_status = order["status"]
        if current_status in ["filled", "canceled", "rejected", "closed"]:
            return False

        if self.trading_client:
            cancel_sent = False
            try:
                broker_order_id = order.get("broker_order_id")
                if broker_order_id:
                    if hasattr(self.trading_client, "cancel_order_by_id"):
                        self.trading_client.cancel_order_by_id(broker_order_id)
                        cancel_sent = True
                    elif hasattr(self.trading_client, "cancel_order"):
                        self.trading_client.cancel_order(broker_order_id)
                        cancel_sent = True
                    elif hasattr(self.trading_client, "cancel_order_by_client_id"):
                        self.trading_client.cancel_order_by_client_id(broker_order_id)
                        cancel_sent = True
                else:
                    if hasattr(self.trading_client, "cancel_order_by_client_id"):
                        self.trading_client.cancel_order_by_client_id(client_order_id)
                        cancel_sent = True
                    elif hasattr(self.trading_client, "cancel_order_by_id"):
                        self.trading_client.cancel_order_by_id(client_order_id)
                        cancel_sent = True
                    elif hasattr(self.trading_client, "cancel_order"):
                        self.trading_client.cancel_order(client_order_id)
                        cancel_sent = True

                if not cancel_sent:
                    logger.warning(f"No compatible cancellation method on trading client for {client_order_id}")
                    self.ledger.update_status_by_client_order_id(
                        client_order_id=client_order_id,
                        status=ExecutionStatus.UNKNOWN,
                        error_message="Broker cancellation method unsupported on client",
                        actor="order_watcher",
                    )
                    return False

            except Exception as exc:
                logger.warning(f"Failed to submit cancel for {client_order_id}: {exc}")
                self.ledger.update_status_by_client_order_id(
                    client_order_id=client_order_id,
                    status=ExecutionStatus.UNKNOWN,
                    error_message=f"Broker cancel failed: {exc}",
                    actor="order_watcher",
                )
                return False

        # A cancel request is not cancellation evidence. Re-read the broker
        # order and only persist CANCELED after the broker confirms it.
        if not self.trading_client:
            return False
        try:
            broker_order = self.trading_client.get_order_by_client_id(client_order_id)
            confirmed_status = map_broker_status(str(getattr(broker_order, "status", "unknown")))
        except Exception as exc:
            self.ledger.update_status_by_client_order_id(
                client_order_id=client_order_id,
                status=ExecutionStatus.UNKNOWN,
                error_message=f"Cancel sent but confirmation unavailable: {exc}",
                actor="order_watcher",
            )
            return False
        if confirmed_status != ExecutionStatus.CANCELED:
            self.ledger.update_status_by_client_order_id(
                client_order_id=client_order_id,
                status=ExecutionStatus.UNKNOWN,
                error_message=f"Cancel sent; broker status is {confirmed_status.value}",
                actor="order_watcher",
            )
            return False

        # Transition to CANCELED only after broker confirmation.
        try:
            terminal_status = (
                ExecutionStatus.PARTIALLY_FILLED
                if current_status == ExecutionStatus.PARTIALLY_FILLED.value
                else ExecutionStatus.CANCELED
            )
            self.ledger.update_status_by_client_order_id(
                client_order_id=client_order_id,
                status=terminal_status,
                error_message=(
                    f"{reason}; unfilled remainder canceled, filled exposure remains open"
                    if terminal_status == ExecutionStatus.PARTIALLY_FILLED else reason
                ),
                actor="order_watcher",
            )
            return True
        except Exception:
            return False
