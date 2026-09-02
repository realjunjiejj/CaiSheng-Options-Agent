"""Alpaca Operations Proof: Post-Close Daily Reconciliation CLI & Receipt Generator."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
from volagent.execution.ledger import ExecutionLedger
from volagent.lifecycle.reporters import DailyReconciliationReporter


def run_cli_reconciliation(
    ledger: ExecutionLedger | None = None,
    trading_client: Any | None = None,
    output_path: Path | str = "data/evaluation/reconciliation_receipt.json",
) -> dict[str, Any]:
    """Execute post-market close daily reconciliation and export sanitized JSON receipt."""
    ledger = ledger or ExecutionLedger()
    reporter = DailyReconciliationReporter(ledger=ledger, trading_client=trading_client)

    report = reporter.generate_daily_report()

    rep_status = str(report.get("status", "")).upper()
    is_halted = bool(report.get("is_system_halted")) or (rep_status == "HALTED")
    
    if is_halted:
        overall_status = "HALTED"
    elif rep_status in ["CLEAN", "PASS"]:
        overall_status = "CLEAN"
    else:
        overall_status = "WARNING"

    receipt = {
        "receipt_type": "caisheng.daily_reconciliation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "reconciliation_id": report.get("reconciliation_id", "rec-001"),
        "matched_order_count": report.get("matched_orders", 0),
        "matched_position_count": report.get("matched_positions", 0),
        "orphan_broker_orders": report.get("orphan_broker_orders", 0),
        "orphan_broker_positions": report.get("orphan_broker_positions", 0),
        "orphan_ledger_positions": report.get("orphan_ledger_positions", 0),
        "quantity_mismatches": report.get("quantity_mismatches", 0),
        "is_system_halted": is_halted,
        "raw_report": report,
    }


    # Save to disk
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(receipt, indent=2) + "\n")

    return receipt

