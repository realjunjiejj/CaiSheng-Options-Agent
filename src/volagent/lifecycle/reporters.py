"""Closed-Trade and Daily Reconciliation Reporters.

Generates immutable accounting records and end-of-day broker/ledger reconciliation proofs.
"""

from datetime import datetime, timedelta, timezone
import json
import uuid
from typing import Any

from volagent.domain.enums import Decision
from volagent.domain.lifecycle import ClosedTradeRecord
from volagent.execution.alpaca import AlpacaPaperBroker
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.reconciliation import ReconciliationStatus, reconcile_broker_and_ledger



class ClosedTradeReporter:
    """Calculates trade P&L, risk utilization, and persists immutable closed trade history."""

    def __init__(self, ledger: ExecutionLedger):
        self.ledger = ledger

    def record_completed_trade(
        self,
        strategy_id: str,
        symbol: str,
        decision: Decision,
        event_id: str,
        entry_order_id: str,
        exit_order_id: str,
        quantity: int,
        entry_price: float,
        exit_price: float,
        fees_and_slippage: float,
        opened_at: datetime,
        closed_at: datetime,
        max_loss_budget: float,
        pre_event_expected_move: float = 0.05,
        pre_event_implied_move: float = 0.045,
        actual_post_event_move: float = 0.06,
        raw_receipt: dict[str, Any] | None = None,
    ) -> ClosedTradeRecord:
        """Generate and persist ClosedTradeRecord with exact cash flow identities."""
        trade_id = f"trd-{uuid.uuid4().hex[:8]}"
        is_long = "straddle" in decision.value.lower()

        # Gross P&L calculation: (exit - entry) * 100 * qty for long; (entry - exit) * 100 * qty for short credit
        if is_long:
            gross_pnl = (exit_price - entry_price) * 100.0 * quantity
        else:
            gross_pnl = (entry_price - exit_price) * 100.0 * quantity

        net_pnl = gross_pnl - fees_and_slippage
        cost_basis = entry_price * 100.0 * quantity if is_long else max_loss_budget
        return_pct = (net_pnl / cost_basis) if cost_basis > 0 else 0.0
        risk_util = (abs(net_pnl) / max_loss_budget) if max_loss_budget > 0 else 1.0
        holding_hours = max(0.1, (closed_at - opened_at).total_seconds() / 3600.0)

        outcome = "WIN" if net_pnl > 5.0 else ("LOSS" if net_pnl < -5.0 else "SCRATCH")

        record = ClosedTradeRecord(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol=symbol.upper(),
            decision=decision,
            event_id=event_id,
            entry_order_id=entry_order_id,
            exit_order_id=exit_order_id,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_realized_pnl_dollars=gross_pnl,
            fees_and_slippage=fees_and_slippage,
            net_realized_pnl_dollars=net_pnl,
            realized_return_pct=return_pct,
            max_loss_budget=max_loss_budget,
            risk_utilization_pct=risk_util,
            opened_at=opened_at,
            closed_at=closed_at,
            holding_hours=holding_hours,
            pre_event_expected_move=pre_event_expected_move,
            pre_event_implied_move=pre_event_implied_move,
            actual_post_event_move=actual_post_event_move,
            outcome_label=outcome,
            raw_execution_receipt=raw_receipt or {},
        )

        self.ledger.record_closed_trade(record)
        return record

    def record_closed_trade(
        self,
        strategy_id: str,
        symbol: str,
        decision: Decision | str,
        entry_receipt_id: str = "",
        exit_receipt_id: str = "",
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        quantity: int = 1,
        realized_pnl_dollars: float = 0.0,
        holding_duration_seconds: float = 3600.0,
        entry_timestamp: datetime | None = None,
        exit_timestamp: datetime | None = None,
    ) -> ClosedTradeRecord:
        """Convenience method to record a closed trade with flexible timestamps and IDs."""
        now = datetime.now(timezone.utc)
        opened_at = entry_timestamp or (now - timedelta(seconds=holding_duration_seconds))
        closed_at = exit_timestamp or now
        dec = decision if isinstance(decision, Decision) else (Decision(decision) if hasattr(Decision, "__call__") else Decision.LONG_STRADDLE)
        return self.record_completed_trade(
            strategy_id=strategy_id,
            symbol=symbol,
            decision=dec,
            event_id="evt-default",
            entry_order_id=entry_receipt_id,
            exit_order_id=exit_receipt_id,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            fees_and_slippage=0.0,
            opened_at=opened_at,
            closed_at=closed_at,
            max_loss_budget=max(1.0, entry_price * quantity * 100.0),
        )



class DailyReconciliationReporter:
    """Generates daily start/end of day broker reconciliation proofs and equity curve updates."""

    def __init__(self, ledger: ExecutionLedger, trading_client: Any | None = None):
        self.ledger = ledger
        self.trading_client = trading_client

    def generate_daily_report(self, broker: AlpacaPaperBroker | None = None) -> dict[str, Any]:
        """Execute full two-way reconciliation against Alpaca broker and export structured report."""
        if broker is None:
            if self.trading_client is not None:
                broker = AlpacaPaperBroker(ledger=self.ledger)
                broker._trading_client = self.trading_client
            else:
                from volagent.config import load_config
                cfg = load_config()
                if cfg.alpaca_api_key and cfg.alpaca_secret_key:
                    broker = AlpacaPaperBroker(
                        api_key=cfg.alpaca_api_key,
                        secret_key=cfg.alpaca_secret_key,
                        ledger=self.ledger,
                    )
                else:
                    return {
                        "reconciliation_id": f"rec-{uuid.uuid4().hex[:10]}",
                        "status": "HALTED",
                        "reason": "No Alpaca trading credentials configured for reconciliation",
                        "is_system_halted": True,
                        "matched_orders": 0,
                        "matched_positions": 0,
                        "orphan_broker_orders": 0,
                        "orphan_broker_positions": 0,
                        "orphan_ledger_positions": 0,
                        "quantity_mismatches": 0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

        report = reconcile_broker_and_ledger(alpaca_broker=broker, ledger=self.ledger)
        is_halted, _ = self.ledger.is_system_halted()
        return {
            "reconciliation_id": report.reconciliation_id,
            "status": report.status.value,
            "matched_orders": report.matched_orders_count,
            "matched_positions": report.matched_positions_count,
            "orphan_broker_orders": len(report.orphan_broker_orders),
            "orphan_broker_positions": len(report.orphan_broker_positions),
            "orphan_ledger_positions": len(report.orphan_ledger_positions),
            "quantity_mismatches": len(report.mismatches),
            "is_system_halted": is_halted or (report.status.value == "HALTED"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
