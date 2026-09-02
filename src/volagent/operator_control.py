"""Fail-closed operator controls for the private CaiSheng execution host."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping
import uuid

from volagent.cloud_runtime import assert_execution_host_is_safe
from volagent.competition import (
    issue_competition_lease,
    read_competition_status,
    revoke_competition_lease,
)
from volagent.config import VolAgentSettings
from volagent.data.alpaca_sdk import AlpacaPortfolioAdapter
from volagent.errors import ConfigurationError, ExecutionError
from volagent.execution.ledger import ExecutionLedger
from volagent.lifecycle.watcher import OrderWatcher


OPERATOR_RECEIPT_SCHEMA = "caisheng.operator-action.v1"
EMERGENCY_CONFIRMATION = "HALT NEW ENTRIES"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)


def _receipt_hash(payload: Mapping[str, Any], secret: str) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "receipt_hash"}
    return hmac.new(
        secret.encode("utf-8"),
        _canonical_json(unsigned).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def read_monitor_heartbeat(
    path: str | Path,
    *,
    now: datetime | None = None,
    maximum_age_seconds: int = 90,
) -> dict[str, Any]:
    """Read the monitor's liveness receipt and reject missing, stale, or error states."""
    target = Path(path)
    checked_at = _as_utc(now or _utc_now())
    if not target.exists():
        return {
            "monitor_active": False,
            "status": "MISSING",
            "reason": "Monitor heartbeat receipt is missing",
            "generated_at": None,
            "age_seconds": None,
        }
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        generated_at = _as_utc(datetime.fromisoformat(str(payload["generated_at"])))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "monitor_active": False,
            "status": "INVALID",
            "reason": "Monitor heartbeat receipt is unreadable",
            "generated_at": None,
            "age_seconds": None,
        }

    age_seconds = max(0.0, (checked_at - generated_at).total_seconds())
    raw_status = str(payload.get("status", "unknown")).lower()
    active = age_seconds <= maximum_age_seconds and raw_status in {"healthy", "halted"}
    if age_seconds > maximum_age_seconds:
        reason = f"Monitor heartbeat is stale ({age_seconds:.0f}s old)"
    elif raw_status not in {"healthy", "halted"}:
        reason = f"Monitor heartbeat reports {raw_status.upper()}"
    else:
        reason = "Continuous position monitor heartbeat is current"
    return {
        "monitor_active": active,
        "status": raw_status.upper(),
        "reason": reason,
        "generated_at": generated_at.isoformat(),
        "age_seconds": age_seconds,
        "cycle_count": payload.get("cycle_count"),
        "positions_monitored": payload.get("positions_monitored", 0),
        "system_halted": bool(payload.get("system_halted")),
    }


class OperatorController:
    """One deep interface for dashboard arming, scanning, stopping, and halting."""

    def __init__(
        self,
        *,
        settings: VolAgentSettings,
        ledger: ExecutionLedger,
        portfolio_adapter: AlpacaPortfolioAdapter,
        heartbeat_path: str | Path | None = None,
        audit_path: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        now_fn: Callable[[], datetime] = _utc_now,
        scan_runner: Callable[[], dict[str, Any]] | None = None,
        watcher: OrderWatcher | None = None,
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.portfolio_adapter = portfolio_adapter
        self.environ = environ if environ is not None else os.environ
        self.now_fn = now_fn
        state_dir = ledger.db_path.parent
        self.heartbeat_path = Path(
            heartbeat_path
            or self.environ.get("CAISHENG_HEARTBEAT_PATH")
            or state_dir / "monitor-heartbeat.json"
        )
        self.audit_path = Path(
            audit_path
            or self.environ.get("CAISHENG_OPERATOR_AUDIT_PATH")
            or state_dir / "operator-actions.jsonl"
        )
        self.scan_runner = scan_runner or self._run_scan_subprocess
        self.watcher = watcher

    def _assert_private_persistent_host(self) -> None:
        assert_execution_host_is_safe(
            environ=self.environ,
            ledger_path=self.ledger.db_path,
        )

    def _record_action(
        self,
        *,
        action: str,
        outcome: str,
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        secret = self.settings.alpaca_secret_key
        if not secret:
            raise ConfigurationError("Operator audit signing key is unavailable.")
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            previous_hash = ""
            for line in handle:
                if not line.strip():
                    continue
                try:
                    previous_hash = str(json.loads(line).get("receipt_hash", previous_hash))
                except json.JSONDecodeError:
                    previous_hash = "INVALID_PREVIOUS_RECEIPT"
            receipt: dict[str, Any] = {
                "schema_version": OPERATOR_RECEIPT_SCHEMA,
                "action_id": f"operator-{uuid.uuid4().hex}",
                "generated_at": _as_utc(self.now_fn()).isoformat(),
                "actor": "private_dashboard_operator",
                "action": action,
                "outcome": outcome,
                "paper_only": True,
                "previous_receipt_hash": previous_hash,
                "details": dict(details),
            }
            receipt["receipt_hash"] = _receipt_hash(receipt, secret)
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(receipt, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            os.chmod(self.audit_path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return receipt

    def list_action_receipts(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        receipts: list[dict[str, Any]] = []
        try:
            for line in self.audit_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    receipts.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            return []
        return list(reversed(receipts[-max(1, limit) :]))

    def status(self, *, paper_account_id: str | None) -> dict[str, Any]:
        try:
            self._assert_private_persistent_host()
            host_safe = True
            host_reason = "Private persistent execution host verified"
        except ConfigurationError as exc:
            host_safe = False
            host_reason = str(exc)
        lease = read_competition_status(
            path=self.settings.competition.lease_path,
            settings=self.settings,
            paper_account_id=paper_account_id,
            now=self.now_fn(),
        )
        heartbeat = read_monitor_heartbeat(self.heartbeat_path, now=self.now_fn())
        halted, halt_reason = self.ledger.is_system_halted()
        return {
            "host_safe": host_safe,
            "host_reason": host_reason,
            "lease": lease,
            "heartbeat": heartbeat,
            "system_halted": halted,
            "halt_reason": halt_reason,
            "can_start": bool(
                host_safe
                and heartbeat["monitor_active"]
                and paper_account_id
                and not halted
                and not lease["submission_authorized"]
            ),
            "can_scan": bool(
                host_safe
                and heartbeat["monitor_active"]
                and not halted
                and lease["submission_authorized"]
            ),
            "can_stop": bool(lease["submission_authorized"]),
        }

    def start_session(self, *, duration_hours: int | None = None) -> dict[str, Any]:
        """Verify the broker and monitor, then issue a signed entry lease."""
        self._assert_private_persistent_host()
        heartbeat = read_monitor_heartbeat(self.heartbeat_path, now=self.now_fn())
        if not heartbeat["monitor_active"]:
            raise ExecutionError(f"Cannot arm: {heartbeat['reason']}.")
        halted, halt_reason = self.ledger.is_system_halted()
        if halted:
            raise ExecutionError(f"Cannot arm while the system halt is active: {halt_reason}.")
        snapshot = self.portfolio_adapter.fetch_portfolio_snapshot(ledger=self.ledger)
        if snapshot.is_stale or not snapshot.account_id or snapshot.equity <= 0:
            raise ExecutionError("Cannot arm without a fresh authenticated Alpaca paper snapshot.")
        if not math.isclose(float(snapshot.initial_nav), 100_000.0, abs_tol=0.01):
            raise ExecutionError("Cannot arm: the competition mandate is not bound to $100,000.")
        hours = duration_hours or self.settings.competition.arm_duration_hours
        lease = issue_competition_lease(
            path=self.settings.competition.lease_path,
            settings=self.settings,
            paper_account_id=snapshot.account_id,
            starting_nav=snapshot.initial_nav,
            current_equity=snapshot.equity,
            now=self.now_fn(),
            duration=timedelta(hours=hours),
        )
        return self._record_action(
            action="START_AUTONOMOUS_SESSION",
            outcome="AUTHORIZED",
            details={
                "lease_status": lease["status"],
                "expires_at": lease["expires_at"],
                "current_equity_at_arm": snapshot.equity,
                "monitor_status": heartbeat["status"],
                "lease_hash": lease["lease_hash"],
            },
        )

    def stop_new_entries(self) -> dict[str, Any]:
        """Revoke the entry lease while the position monitor keeps running."""
        self._assert_private_persistent_host()
        lease = revoke_competition_lease(
            path=self.settings.competition.lease_path,
            settings=self.settings,
            now=self.now_fn(),
        )
        return self._record_action(
            action="STOP_NEW_ENTRIES",
            outcome="DISARMED",
            details={
                "lease_status": lease["status"],
                "monitoring_continues": True,
                "positions_flattened": False,
                "lease_hash": lease["lease_hash"],
            },
        )

    def emergency_halt(self, *, confirmation: str) -> dict[str, Any]:
        """Persistently halt entries and cancel governed working entry orders."""
        self._assert_private_persistent_host()
        if confirmation.strip() != EMERGENCY_CONFIRMATION:
            raise ExecutionError(
                f"Emergency Halt requires the exact confirmation: {EMERGENCY_CONFIRMATION}"
            )
        action_id = f"operator-emergency-{uuid.uuid4().hex}"
        self.ledger.trip_system_halt(
            reason="Operator emergency halt from private dashboard",
            evidence_id=action_id,
        )
        lease_error: str | None = None
        try:
            revoke_competition_lease(
                path=self.settings.competition.lease_path,
                settings=self.settings,
                now=self.now_fn(),
            )
        except Exception as exc:  # halt already blocks entries; preserve failure evidence
            lease_error = f"{type(exc).__name__}: {exc}"

        watcher = self.watcher
        if watcher is None:
            watcher = OrderWatcher(
                ledger=self.ledger,
                trading_client=self.portfolio_adapter._get_client(),
            )
        cancel_error: str | None = None
        canceled: list[str] = []
        try:
            canceled = watcher.cancel_open_entry_orders(
                reason="Operator emergency halt from private dashboard"
            )
        except Exception as exc:
            cancel_error = f"{type(exc).__name__}: {exc}"

        outcome = "HALTED" if not lease_error and not cancel_error else "HALTED_WITH_WARNINGS"
        return self._record_action(
            action="EMERGENCY_HALT",
            outcome=outcome,
            details={
                "evidence_id": action_id,
                "new_entries_blocked": True,
                "monitoring_continues": True,
                "positions_flattened": False,
                "canceled_entry_client_order_ids": canceled,
                "lease_error": lease_error,
                "cancel_error": cancel_error,
            },
        )

    def run_live_scan(self, *, paper_account_id: str | None) -> dict[str, Any]:
        """Run one fixed-argument lifecycle scan only while all entry gates are open."""
        status = self.status(paper_account_id=paper_account_id)
        if not status["can_scan"]:
            reasons = [status["host_reason"], status["heartbeat"]["reason"], status["lease"]["reason"]]
            if status["system_halted"]:
                reasons.append(str(status["halt_reason"] or "System halt active"))
            raise ExecutionError("Live scan is blocked: " + " | ".join(reasons))
        result = self.scan_runner()
        outcome = "COMPLETED" if result.get("exit_code") == 0 else "FAILED"
        receipt = self._record_action(
            action="RUN_LIVE_SCAN_NOW",
            outcome=outcome,
            details={
                "exit_code": result.get("exit_code"),
                "summary": result.get("summary", {}),
            },
        )
        if outcome != "COMPLETED":
            raise ExecutionError(f"Live scan failed; audit receipt {receipt['action_id']} recorded.")
        return receipt

    @staticmethod
    def _run_scan_subprocess() -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, "-m", "volagent.cloud_runtime", "scan"],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        summary: dict[str, Any] = {}
        stdout = completed.stdout.strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
                summary = {
                    key: parsed.get(key)
                    for key in (
                        "market_open",
                        "events_found",
                        "decisions_generated",
                        "entries_submitted",
                        "abstentions",
                        "errors",
                    )
                }
            except json.JSONDecodeError:
                summary = {"output_tail": stdout[-1000:]}
        if completed.stderr.strip():
            summary["error_tail"] = completed.stderr.strip()[-1000:]
        return {"exit_code": completed.returncode, "summary": summary}
