"""Fail-closed lifecycle entry points for persistent execution hosts.

Cloud Run services are used for the judge UI and authenticated MCP access.  The
authoritative execution ledger remains SQLite, so autonomous lifecycle commands
must run on one persistent host until a transactional network database backend
is implemented.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import signal
import time
from typing import Any, Mapping

import httpx

from volagent.config import load_config
from volagent.domain.enums import DataMode
from volagent.errors import ConfigurationError, ExecutionError, RuntimeLockBusyError
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.runtime_lock import SingleRuntimeLock
from volagent.lifecycle.runner import LifecycleRunner


_CLOUD_RUN_MARKERS = (
    "K_SERVICE",
    "CLOUD_RUN_JOB",
    "CLOUD_RUN_EXECUTION",
    "CLOUD_RUN_WORKER_POOL",
)


def _validate_calendar(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigurationError("Earnings calendar payload must be a JSON object.")
    items = payload.get("earnings_calendar")
    if not isinstance(items, list) or not items:
        raise ConfigurationError("Earnings calendar must contain a non-empty earnings_calendar list.")

    required = {"symbol", "event_date", "timing", "confirmed", "source_url"}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigurationError(f"Earnings calendar item {index} must be an object.")
        missing = sorted(required - set(item))
        if missing:
            raise ConfigurationError(
                f"Earnings calendar item {index} is missing required fields: {', '.join(missing)}."
            )
        try:
            date.fromisoformat(str(item["event_date"]))
        except ValueError as exc:
            raise ConfigurationError(
                f"Earnings calendar item {index} has an invalid ISO event_date."
            ) from exc
        if str(item["timing"]).strip().lower() != "amc":
            raise ConfigurationError(
                f"Earnings calendar item {index} is not a confirmed after-market-close event."
            )
        if item["confirmed"] is not True:
            raise ConfigurationError(f"Earnings calendar item {index} is not confirmed.")
        source_url = str(item["source_url"]).strip()
        if not source_url.startswith("https://"):
            raise ConfigurationError(
                f"Earnings calendar item {index} must provide an HTTPS source_url."
            )
    return payload


def load_event_calendar(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Load a verified calendar from exactly one explicit runtime source."""
    env = environ if environ is not None else os.environ
    configured_sources = {
        "json": env.get("CAISHENG_EVENT_CALENDAR_JSON"),
        "path": env.get("CAISHENG_EVENT_CALENDAR_PATH"),
        "url": env.get("CAISHENG_EVENT_CALENDAR_URL"),
    }
    active = {name: value for name, value in configured_sources.items() if value}
    if len(active) != 1:
        raise ConfigurationError(
            "Configure exactly one earnings calendar source: "
            "CAISHENG_EVENT_CALENDAR_JSON, CAISHENG_EVENT_CALENDAR_PATH, or "
            "CAISHENG_EVENT_CALENDAR_URL."
        )

    source, value = next(iter(active.items()))
    try:
        if source == "json":
            payload = json.loads(str(value))
        elif source == "path":
            payload = json.loads(Path(str(value)).read_text(encoding="utf-8"))
        else:
            url = str(value)
            if not url.startswith("https://"):
                raise ConfigurationError("Remote earnings calendar URL must use HTTPS.")
            headers: dict[str, str] = {}
            token = env.get("CAISHENG_EVENT_CALENDAR_BEARER_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=False)
            response.raise_for_status()
            payload = response.json()
    except ConfigurationError:
        raise
    except (OSError, json.JSONDecodeError, httpx.HTTPError, ValueError) as exc:
        raise ConfigurationError(f"Unable to load the configured earnings calendar: {exc}") from exc
    return _validate_calendar(payload)


def assert_execution_host_is_safe(
    *,
    environ: Mapping[str, str] | None = None,
    ledger_path: str | Path,
) -> None:
    """Prevent SQLite order execution on ephemeral or multi-instance Cloud Run."""
    env = environ if environ is not None else os.environ
    marker = next((name for name in _CLOUD_RUN_MARKERS if env.get(name)), None)
    if marker:
        raise ConfigurationError(
            "SQLite execution is disabled on Cloud Run because its filesystem is ephemeral "
            "and Cloud Storage FUSE is not database-safe. Run the lifecycle on one persistent "
            f"host instead (detected {marker}; ledger={ledger_path})."
        )


def _validate_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict) or "errors" not in result:
        raise ExecutionError("Lifecycle returned an invalid result: missing errors field.")
    errors = result.get("errors")
    if not isinstance(errors, list):
        raise ExecutionError("Lifecycle returned an invalid errors field.")
    if errors:
        raise ExecutionError("Lifecycle failed: " + "; ".join(str(error) for error in errors))
    return result


def run_lifecycle_cycle(
    runner: Any,
    *,
    calendar: dict[str, Any],
) -> dict[str, Any]:
    """Run a scan cycle and reject false-success result shapes."""
    return _validate_result(runner.run_cycle(calendar=calendar))


def _write_monitor_heartbeat(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Atomically publish a small local liveness receipt for external monitoring."""
    heartbeat_path = Path(path)
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = heartbeat_path.with_name(
        f".{heartbeat_path.name}.{os.getpid()}.tmp"
    )
    temporary_path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, heartbeat_path)


def _run_monitor_cycle_with_timeout(runner: Any, timeout_seconds: int) -> Any:
    """Bound a broker-monitoring cycle so a stuck HTTPS call cannot fake liveness."""
    if not hasattr(signal, "SIGALRM"):
        return runner.run_cycle(calendar=None, scan_opportunities=False)

    def _raise_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(
            f"Monitor cycle exceeded the {timeout_seconds}s broker deadline"
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return runner.run_cycle(calendar=None, scan_opportunities=False)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_monitor_supervisor(
    runner: Any,
    *,
    interval_seconds: int = 20,
    cycle_timeout_seconds: int = 60,
    heartbeat_path: str | Path,
    supervisor_lock_path: str | Path,
    max_cycles: int | None = None,
    sleep_fn: Any = time.sleep,
) -> dict[str, Any]:
    """Continuously monitor positions under one process-level supervisor lock.

    A failed cycle trips the persistent halt so subsequent scans cannot create
    new exposure. The monitor service itself is then restarted by systemd and
    remains able to perform risk-reducing exits while the halt is active.
    """
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
        raise ConfigurationError("Monitor interval must be an integer number of seconds.")
    if interval_seconds < 10 or interval_seconds > 300:
        raise ConfigurationError("Monitor interval must be between 10 and 300 seconds.")
    if isinstance(cycle_timeout_seconds, bool) or not isinstance(cycle_timeout_seconds, int):
        raise ConfigurationError("Monitor cycle timeout must be an integer number of seconds.")
    if cycle_timeout_seconds < 10 or cycle_timeout_seconds > 300:
        raise ConfigurationError("Monitor cycle timeout must be between 10 and 300 seconds.")
    if max_cycles is not None and max_cycles < 1:
        raise ConfigurationError("max_cycles must be at least 1 when provided.")

    cycle_count = 0
    latest_result: dict[str, Any] = {}
    with SingleRuntimeLock(lock_path=supervisor_lock_path):
        while max_cycles is None or cycle_count < max_cycles:
            try:
                latest_result = _validate_result(
                    _run_monitor_cycle_with_timeout(runner, cycle_timeout_seconds)
                )
            except RuntimeLockBusyError as exc:
                # A scheduled or operator-triggered lifecycle scan owns the same
                # exclusive lock and performs monitoring before opportunity work.
                # This is healthy serialization, not a monitor failure.
                cycle_count += 1
                system_halted, halt_reason = runner.ledger.is_system_halted()
                latest_result = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "runtime_busy": True,
                    "positions_monitored": 0,
                    "exits_triggered": 0,
                    "errors": [],
                }
                _write_monitor_heartbeat(
                    heartbeat_path,
                    {
                        "receipt_type": "caisheng.monitor-heartbeat.v1",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "status": "halted" if system_halted else "healthy",
                        "cycle_count": cycle_count,
                        "cycle_timestamp": latest_result["timestamp"],
                        "runtime_busy": True,
                        "runtime_busy_reason": str(exc)[:1000],
                        "positions_monitored": 0,
                        "exits_triggered": 0,
                        "system_halted": system_halted,
                        "halt_reason": halt_reason,
                        "reconciliation_status": "SERIALIZED",
                    },
                )
                if max_cycles is None or cycle_count < max_cycles:
                    sleep_fn(interval_seconds)
                continue
            except Exception as exc:
                error_text = str(exc)[:1000]
                try:
                    runner.ledger.trip_system_halt(
                        f"Continuous monitor failed closed: {error_text}"
                    )
                except Exception:
                    # Preserve the original monitoring failure. A stale/error
                    # heartbeat still ensures the external alert fires.
                    pass
                _write_monitor_heartbeat(
                    heartbeat_path,
                    {
                        "receipt_type": "caisheng.monitor-heartbeat.v1",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "status": "error",
                        "cycle_count": cycle_count,
                        "error": error_text,
                    },
                )
                raise

            cycle_count += 1
            system_halted, halt_reason = runner.ledger.is_system_halted()
            _write_monitor_heartbeat(
                heartbeat_path,
                {
                    "receipt_type": "caisheng.monitor-heartbeat.v1",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "halted" if system_halted else "healthy",
                    "cycle_count": cycle_count,
                    "cycle_timestamp": latest_result.get("timestamp"),
                    "market_open": latest_result.get("market_open"),
                    "positions_monitored": latest_result.get("positions_monitored", 0),
                    "exits_triggered": latest_result.get("exits_triggered", 0),
                    "system_halted": system_halted,
                    "halt_reason": halt_reason,
                    "reconciliation_status": latest_result.get(
                        "reconciliation_status", "UNKNOWN"
                    ),
                },
            )
            if max_cycles is None or cycle_count < max_cycles:
                sleep_fn(interval_seconds)
    return latest_result


def _build_runner(environ: Mapping[str, str]) -> LifecycleRunner:
    ledger_path = environ.get("VOLAGENT_LEDGER_DB_PATH")
    if not ledger_path:
        raise ConfigurationError(
            "VOLAGENT_LEDGER_DB_PATH must point to durable storage on the persistent execution host."
        )
    assert_execution_host_is_safe(environ=environ, ledger_path=ledger_path)

    settings = load_config(environ.get("CAISHENG_CONFIG_PATH"))
    if str(settings.volagent_data_mode).lower() != DataMode.LIVE.value:
        raise ConfigurationError("Lifecycle jobs require VOLAGENT_DATA_MODE=live.")
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise ConfigurationError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required.")

    execution_mode = environ.get("CAISHENG_EXECUTION_MODE", "preview").strip().lower()
    if execution_mode not in {"preview", "autonomous"}:
        raise ConfigurationError("CAISHENG_EXECUTION_MODE must be preview or autonomous.")
    if execution_mode == "autonomous" and (
        not settings.execution.allow_order_submission
        or settings.execution.require_human_approval
    ):
        raise ConfigurationError(
            "Autonomous mode requires VOLAGENT_ALLOW_ORDER_SUBMISSION=true and "
            "VOLAGENT_REQUIRE_HUMAN_APPROVAL=false."
        )

    from alpaca.trading.client import TradingClient

    trading_client = TradingClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        paper=True,
    )
    lock_path = environ.get("CAISHENG_RUNTIME_LOCK_PATH")
    return LifecycleRunner(
        ledger=ExecutionLedger(db_path=ledger_path),
        trading_client=trading_client,
        lock_path=lock_path,
        settings=settings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CaiSheng persistent-host lifecycle runtime")
    parser.add_argument("mode", choices=("scan", "monitor", "supervise"))
    parser.add_argument("--interval-seconds", type=int)
    parser.add_argument("--max-cycles", type=int)
    args = parser.parse_args(argv)

    runner = _build_runner(os.environ)
    if args.mode == "scan":
        has_calendar = any(
            os.environ.get(name)
            for name in (
                "CAISHENG_EVENT_CALENDAR_JSON",
                "CAISHENG_EVENT_CALENDAR_PATH",
                "CAISHENG_EVENT_CALENDAR_URL",
            )
        )
        result = run_lifecycle_cycle(
            runner,
            calendar=load_event_calendar() if has_calendar else {},
        )
    elif args.mode == "monitor":
        result = _validate_result(
            runner.run_cycle(calendar=None, scan_opportunities=False)
        )
    else:
        ledger_path = Path(os.environ["VOLAGENT_LEDGER_DB_PATH"])
        interval_seconds = args.interval_seconds
        if interval_seconds is None:
            raw_interval = os.environ.get("CAISHENG_MONITOR_INTERVAL_SECONDS", "20")
            try:
                interval_seconds = int(raw_interval)
            except ValueError as exc:
                raise ConfigurationError(
                    "CAISHENG_MONITOR_INTERVAL_SECONDS must be an integer."
                ) from exc
        raw_cycle_timeout = os.environ.get(
            "CAISHENG_MONITOR_CYCLE_TIMEOUT_SECONDS", "60"
        )
        try:
            cycle_timeout_seconds = int(raw_cycle_timeout)
        except ValueError as exc:
            raise ConfigurationError(
                "CAISHENG_MONITOR_CYCLE_TIMEOUT_SECONDS must be an integer."
            ) from exc
        result = run_monitor_supervisor(
            runner,
            interval_seconds=interval_seconds,
            cycle_timeout_seconds=cycle_timeout_seconds,
            heartbeat_path=os.environ.get(
                "CAISHENG_HEARTBEAT_PATH",
                str(ledger_path.parent / "monitor-heartbeat.json"),
            ),
            supervisor_lock_path=os.environ.get(
                "CAISHENG_SUPERVISOR_LOCK_PATH",
                str(ledger_path.parent / "monitor-supervisor.lock"),
            ),
            max_cycles=args.max_cycles,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
