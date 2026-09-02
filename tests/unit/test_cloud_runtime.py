import json

import pytest

from volagent.cloud_runtime import (
    assert_execution_host_is_safe,
    load_event_calendar,
    main,
    run_monitor_supervisor,
    run_lifecycle_cycle,
)
from volagent.errors import RuntimeLockBusyError
from volagent.errors import ConfigurationError, ExecutionError


def _calendar_payload():
    return {
        "earnings_calendar": [
            {
                "symbol": "AAPL",
                "event_date": "2026-09-01",
                "timing": "amc",
                "confirmed": True,
                "source_url": "https://example.test/calendar/aapl",
            }
        ]
    }


def test_load_event_calendar_from_json_environment():
    calendar = load_event_calendar(
        environ={"CAISHENG_EVENT_CALENDAR_JSON": json.dumps(_calendar_payload())}
    )
    assert calendar == _calendar_payload()


def test_load_event_calendar_fails_closed_without_source():
    with pytest.raises(ConfigurationError, match="calendar source"):
        load_event_calendar(environ={})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"earnings_calendar": []},
        {"earnings_calendar": [{"symbol": "AAPL"}]},
        {
            "earnings_calendar": [
                {
                    "symbol": "AAPL",
                    "event_date": "2026-09-01",
                    "timing": "bmo",
                    "confirmed": True,
                    "source_url": "https://example.test/calendar/aapl",
                }
            ]
        },
    ],
)
def test_load_event_calendar_rejects_incomplete_or_ineligible_payload(payload):
    with pytest.raises(ConfigurationError):
        load_event_calendar(
            environ={"CAISHENG_EVENT_CALENDAR_JSON": json.dumps(payload)}
        )


def test_execution_host_rejects_cloud_run_sqlite():
    with pytest.raises(ConfigurationError, match="SQLite execution is disabled on Cloud Run"):
        assert_execution_host_is_safe(
            environ={"CLOUD_RUN_JOB": "caisheng-scan"},
            ledger_path="/tmp/execution_ledger.db",
        )


def test_execution_host_allows_persistent_non_cloud_runner(tmp_path):
    assert_execution_host_is_safe(
        environ={},
        ledger_path=str(tmp_path / "execution_ledger.db"),
    )


def test_lifecycle_cycle_passes_calendar_and_rejects_reported_errors():
    class Runner:
        def __init__(self):
            self.calendar = None

        def run_cycle(self, calendar=None):
            self.calendar = calendar
            return {"events_found": 1, "errors": []}

    runner = Runner()
    calendar = _calendar_payload()
    result = run_lifecycle_cycle(runner, calendar=calendar)
    assert runner.calendar is calendar
    assert result["events_found"] == 1

    class BrokenRunner:
        def run_cycle(self, calendar=None):
            return {"errors": ["market data unavailable"]}

    with pytest.raises(ExecutionError, match="market data unavailable"):
        run_lifecycle_cycle(BrokenRunner(), calendar=calendar)


def test_lifecycle_cycle_rejects_false_success_shape():
    class InvalidRunner:
        def run_cycle(self, calendar=None):
            return {"events_found": 0}

    with pytest.raises(ExecutionError, match="missing errors field"):
        run_lifecycle_cycle(InvalidRunner(), calendar=_calendar_payload())


def test_monitor_mode_never_scans_for_new_opportunities(monkeypatch):
    class Runner:
        def __init__(self):
            self.scan_opportunities = None

        def run_cycle(self, calendar=None, scan_opportunities=True):
            self.scan_opportunities = scan_opportunities
            return {"events_found": 0, "errors": []}

    runner = Runner()
    monkeypatch.setattr("volagent.cloud_runtime._build_runner", lambda environ: runner)

    assert main(["monitor"]) == 0
    assert runner.scan_opportunities is False


def test_monitor_supervisor_repeats_monitor_only_cycles_and_writes_heartbeat(tmp_path):
    class Ledger:
        def trip_system_halt(self, reason):  # pragma: no cover - failure-only guard
            raise AssertionError(reason)

        def is_system_halted(self):
            return False, None

    class Runner:
        def __init__(self):
            self.ledger = Ledger()
            self.calls = []

        def run_cycle(self, calendar=None, scan_opportunities=True):
            self.calls.append((calendar, scan_opportunities))
            return {
                "timestamp": "2026-09-01T01:02:03+00:00",
                "positions_monitored": 1,
                "exits_triggered": 0,
                "reconciliation_status": "CLEAN",
                "errors": [],
            }

    runner = Runner()
    sleeps = []
    heartbeat_path = tmp_path / "monitor-heartbeat.json"

    result = run_monitor_supervisor(
        runner,
        interval_seconds=20,
        heartbeat_path=heartbeat_path,
        supervisor_lock_path=tmp_path / "supervisor.lock",
        max_cycles=2,
        sleep_fn=sleeps.append,
    )

    assert runner.calls == [(None, False), (None, False)]
    assert sleeps == [20]
    assert result["positions_monitored"] == 1
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "healthy"
    assert heartbeat["system_halted"] is False
    assert heartbeat["cycle_count"] == 2
    assert heartbeat["positions_monitored"] == 1


def test_monitor_supervisor_halts_new_entries_and_records_error_on_cycle_failure(tmp_path):
    class Ledger:
        def __init__(self):
            self.halt_reason = None

        def trip_system_halt(self, reason):
            self.halt_reason = reason

    class Runner:
        def __init__(self):
            self.ledger = Ledger()

        def run_cycle(self, calendar=None, scan_opportunities=True):
            return {"errors": ["broker position query failed"]}

    runner = Runner()
    heartbeat_path = tmp_path / "monitor-heartbeat.json"

    with pytest.raises(ExecutionError, match="broker position query failed"):
        run_monitor_supervisor(
            runner,
            interval_seconds=20,
            heartbeat_path=heartbeat_path,
            supervisor_lock_path=tmp_path / "supervisor.lock",
            max_cycles=1,
            sleep_fn=lambda _seconds: None,
        )

    assert "Continuous monitor failed closed" in runner.ledger.halt_reason
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "error"
    assert "broker position query failed" in heartbeat["error"]


def test_monitor_supervisor_fails_closed_when_broker_cycle_times_out(tmp_path, monkeypatch):
    class Ledger:
        def __init__(self):
            self.halt_reason = None

        def trip_system_halt(self, reason):
            self.halt_reason = reason

    class Runner:
        def __init__(self):
            self.ledger = Ledger()

    def timed_out(_runner, _timeout_seconds):
        raise TimeoutError("Monitor cycle exceeded the broker deadline")

    monkeypatch.setattr(
        "volagent.cloud_runtime._run_monitor_cycle_with_timeout",
        timed_out,
    )
    runner = Runner()
    heartbeat_path = tmp_path / "monitor-heartbeat.json"
    with pytest.raises(TimeoutError, match="broker deadline"):
        run_monitor_supervisor(
            runner,
            interval_seconds=20,
            cycle_timeout_seconds=60,
            heartbeat_path=heartbeat_path,
            supervisor_lock_path=tmp_path / "supervisor.lock",
            max_cycles=1,
            sleep_fn=lambda _seconds: None,
        )

    assert "Continuous monitor failed closed" in runner.ledger.halt_reason
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "error"
    assert "broker deadline" in heartbeat["error"]


def test_monitor_supervisor_treats_valid_runtime_lock_contention_as_serialization(tmp_path):
    class Ledger:
        def __init__(self):
            self.halt_reasons = []

        def trip_system_halt(self, reason):
            self.halt_reasons.append(reason)

        def is_system_halted(self):
            return False, None

    class Runner:
        def __init__(self):
            self.ledger = Ledger()

        def run_cycle(self, calendar=None, scan_opportunities=True):
            raise RuntimeLockBusyError("scheduled scan owns runtime lock")

    runner = Runner()
    heartbeat_path = tmp_path / "monitor-heartbeat.json"
    result = run_monitor_supervisor(
        runner,
        interval_seconds=20,
        heartbeat_path=heartbeat_path,
        supervisor_lock_path=tmp_path / "supervisor.lock",
        max_cycles=1,
        sleep_fn=lambda _seconds: None,
    )

    assert runner.ledger.halt_reasons == []
    assert result["runtime_busy"] is True
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "healthy"
    assert heartbeat["runtime_busy"] is True
    assert heartbeat["reconciliation_status"] == "SERIALIZED"


def test_monitor_supervisor_keeps_running_during_existing_halt(tmp_path):
    class Ledger:
        def is_system_halted(self):
            return True, "Daily loss limit breached"

    class Runner:
        def __init__(self):
            self.ledger = Ledger()

        def run_cycle(self, calendar=None, scan_opportunities=True):
            assert scan_opportunities is False
            return {
                "positions_monitored": 1,
                "exits_triggered": 1,
                "errors": [],
            }

    heartbeat_path = tmp_path / "monitor-heartbeat.json"
    run_monitor_supervisor(
        Runner(),
        interval_seconds=20,
        heartbeat_path=heartbeat_path,
        supervisor_lock_path=tmp_path / "supervisor.lock",
        max_cycles=1,
        sleep_fn=lambda _seconds: None,
    )

    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "halted"
    assert heartbeat["system_halted"] is True
    assert heartbeat["exits_triggered"] == 1


@pytest.mark.parametrize("interval", [0, 9, 301])
def test_monitor_supervisor_rejects_unsafe_poll_intervals(tmp_path, interval):
    with pytest.raises(ConfigurationError, match="between 10 and 300 seconds"):
        run_monitor_supervisor(
            object(),
            interval_seconds=interval,
            heartbeat_path=tmp_path / "monitor-heartbeat.json",
            supervisor_lock_path=tmp_path / "supervisor.lock",
            max_cycles=1,
            sleep_fn=lambda _seconds: None,
        )
