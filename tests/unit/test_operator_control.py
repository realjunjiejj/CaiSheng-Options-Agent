"""Behavioral tests for private dashboard operator controls."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock

import pytest

from volagent.config import load_config
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.errors import ExecutionError
from volagent.execution.ledger import ExecutionLedger
from volagent.operator_control import (
    EMERGENCY_CONFIRMATION,
    OperatorController,
    read_monitor_heartbeat,
)


NOW = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)


def _settings(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "false")
    return load_config("config/competition.yaml")


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        equity=100_125.0,
        cash=100_125.0,
        buying_power=200_250.0,
        initial_nav=100_000.0,
        high_water_equity=100_125.0,
        timestamp=NOW,
        account_id="paper-account-id",
    )


def _heartbeat(path, *, generated_at=NOW, status="healthy"):
    path.write_text(
        json.dumps(
            {
                "receipt_type": "caisheng.monitor-heartbeat.v1",
                "generated_at": generated_at.isoformat(),
                "status": status,
                "cycle_count": 4,
                "positions_monitored": 1,
                "system_halted": status == "halted",
            }
        )
    )


def _controller(tmp_path, monkeypatch, *, watcher=None, scan_runner=None):
    settings = _settings(monkeypatch)
    settings.competition.lease_path = str(tmp_path / "competition-arm.json")
    ledger = ExecutionLedger(db_path=tmp_path / "ledger.db")
    heartbeat = tmp_path / "heartbeat.json"
    _heartbeat(heartbeat)
    adapter = MagicMock()
    adapter.fetch_portfolio_snapshot.return_value = _snapshot()
    controller = OperatorController(
        settings=settings,
        ledger=ledger,
        portfolio_adapter=adapter,
        heartbeat_path=heartbeat,
        audit_path=tmp_path / "operator-actions.jsonl",
        environ={},
        now_fn=lambda: NOW,
        watcher=watcher,
        scan_runner=scan_runner,
    )
    return controller, ledger, adapter


def test_monitor_heartbeat_fails_closed_when_missing_stale_or_error(tmp_path):
    heartbeat = tmp_path / "heartbeat.json"
    assert read_monitor_heartbeat(heartbeat, now=NOW)["monitor_active"] is False

    _heartbeat(heartbeat, generated_at=NOW - timedelta(minutes=3))
    stale = read_monitor_heartbeat(heartbeat, now=NOW)
    assert stale["monitor_active"] is False
    assert stale["status"] == "HEALTHY"
    assert "stale" in stale["reason"].lower()

    _heartbeat(heartbeat, status="error")
    failed = read_monitor_heartbeat(heartbeat, now=NOW)
    assert failed["monitor_active"] is False
    assert failed["status"] == "ERROR"


def test_start_and_stop_are_account_bound_signed_and_audited(tmp_path, monkeypatch):
    controller, _ledger, adapter = _controller(tmp_path, monkeypatch)

    started = controller.start_session(duration_hours=2)
    status = controller.status(paper_account_id="paper-account-id")
    assert started["action"] == "START_AUTONOMOUS_SESSION"
    assert started["outcome"] == "AUTHORIZED"
    assert status["lease"]["submission_authorized"] is True
    assert status["can_scan"] is True
    adapter.fetch_portfolio_snapshot.assert_called_once()

    stopped = controller.stop_new_entries()
    status = controller.status(paper_account_id="paper-account-id")
    assert stopped["action"] == "STOP_NEW_ENTRIES"
    assert stopped["details"]["monitoring_continues"] is True
    assert stopped["details"]["positions_flattened"] is False
    assert status["lease"]["submission_authorized"] is False

    receipts = list(reversed(controller.list_action_receipts()))
    assert len(receipts) == 2
    assert receipts[1]["previous_receipt_hash"] == receipts[0]["receipt_hash"]
    assert "paper-secret" not in controller.audit_path.read_text()
    assert oct(controller.audit_path.stat().st_mode & 0o777) == "0o600"


def test_start_refuses_stale_monitor_or_active_halt(tmp_path, monkeypatch):
    controller, ledger, _adapter = _controller(tmp_path, monkeypatch)
    _heartbeat(controller.heartbeat_path, generated_at=NOW - timedelta(minutes=5))
    with pytest.raises(ExecutionError, match="heartbeat is stale"):
        controller.start_session()

    _heartbeat(controller.heartbeat_path)
    ledger.trip_system_halt("test halt")
    with pytest.raises(ExecutionError, match="system halt is active"):
        controller.start_session()


def test_emergency_halt_requires_exact_confirmation_and_never_flattens(tmp_path, monkeypatch):
    watcher = MagicMock()
    watcher.cancel_open_entry_orders.return_value = ["entry-1"]
    controller, ledger, _adapter = _controller(tmp_path, monkeypatch, watcher=watcher)
    controller.start_session()

    with pytest.raises(ExecutionError, match=EMERGENCY_CONFIRMATION):
        controller.emergency_halt(confirmation="yes")
    assert ledger.is_system_halted()[0] is False

    receipt = controller.emergency_halt(confirmation=EMERGENCY_CONFIRMATION)
    halted, reason = ledger.is_system_halted()
    assert halted is True
    assert "Operator emergency halt" in str(reason)
    assert receipt["outcome"] == "HALTED"
    assert receipt["details"]["positions_flattened"] is False
    assert receipt["details"]["canceled_entry_client_order_ids"] == ["entry-1"]
    watcher.cancel_open_entry_orders.assert_called_once()
    status = controller.status(paper_account_id="paper-account-id")
    assert status["lease"]["submission_authorized"] is False
    assert status["heartbeat"]["monitor_active"] is True


def test_live_scan_requires_active_lease_and_records_summary(tmp_path, monkeypatch):
    scan_runner = MagicMock(
        return_value={
            "exit_code": 0,
            "summary": {"events_found": 3, "entries_submitted": 1},
        }
    )
    controller, _ledger, _adapter = _controller(
        tmp_path, monkeypatch, scan_runner=scan_runner
    )
    with pytest.raises(ExecutionError, match="Live scan is blocked"):
        controller.run_live_scan(paper_account_id="paper-account-id")
    scan_runner.assert_not_called()

    controller.start_session()
    receipt = controller.run_live_scan(paper_account_id="paper-account-id")
    assert receipt["action"] == "RUN_LIVE_SCAN_NOW"
    assert receipt["details"]["summary"]["entries_submitted"] == 1
    scan_runner.assert_called_once()


def test_operator_mutations_are_rejected_on_cloud_run(tmp_path, monkeypatch):
    controller, _ledger, _adapter = _controller(tmp_path, monkeypatch)
    controller.environ = {"K_SERVICE": "public-ui"}
    status = controller.status(paper_account_id="paper-account-id")
    assert status["host_safe"] is False
    assert status["can_start"] is False
    with pytest.raises(Exception, match="SQLite execution is disabled on Cloud Run"):
        controller.start_session()
