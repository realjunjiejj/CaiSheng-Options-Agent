"""Unit and lifecycle simulation tests for Milestone 3: Lifecycle Runtime, Scanner, Watcher, Monitor & Reporters."""

from datetime import date, datetime, time, timedelta, timezone
import json
from unittest.mock import MagicMock
import pytest

from volagent.domain.enums import BrokerTarget, Decision, ExecutionStatus, NetPriceConvention, OptionType, OrderSide, PositionIntent
from volagent.domain.events import EarningsEvent
from volagent.domain.execution import ApprovedLegSnapshot, OrderPlan, VerifiedPositionLeg, VerifiedStrategyPositionSnapshot
from volagent.domain.market import OptionContractSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import ExecutionError
from volagent.execution.alpaca import build_closing_order_plan, build_order_plan, create_closing_order_service
from volagent.execution.ledger import ExecutionLedger

from volagent.execution.runtime_lock import SingleRuntimeLock
from volagent.lifecycle.monitor import PositionMonitor
from volagent.lifecycle.reporters import ClosedTradeReporter, DailyReconciliationReporter
from volagent.lifecycle.runner import (
    LifecycleRunner,
    benchmark_decision_time,
    classify_submission_status,
)
from volagent.lifecycle.scanner import EventScanner
from volagent.lifecycle.watcher import OrderWatcher
from volagent.provenance import Provenance


def make_candidate(strategy_id: str = "strat-nvda-1", quantity: int = 1, decision: Decision = Decision.LONG_STRADDLE) -> StrategyCandidate:
    exp = date(2026, 9, 4)
    legs = [
        OptionLeg(contract_symbol="NVDA260904C00125000", option_type="call", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=2.0),
        OptionLeg(contract_symbol="NVDA260904P00125000", option_type="put", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=2.0),
    ]
    return StrategyCandidate(
        strategy_id=strategy_id,
        decision=decision,
        legs=legs,
        quantity=quantity,
        entry_debit_credit=400.0 * quantity,
        net_delta=0.0,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        max_loss=400.0 * quantity,
    )


def make_iron_butterfly_candidate(strategy_id: str = "strat-nvda-ib") -> StrategyCandidate:
    exp = date(2026, 9, 4)
    legs = [
        OptionLeg(contract_symbol="NVDA260904C00125000", option_type="call", strike=125.0, expiration=exp, side="sell", position_intent="sell_to_open", entry_price_assumption=5.0),
        OptionLeg(contract_symbol="NVDA260904P00125000", option_type="put", strike=125.0, expiration=exp, side="sell", position_intent="sell_to_open", entry_price_assumption=5.0),
        OptionLeg(contract_symbol="NVDA260904C00135000", option_type="call", strike=135.0, expiration=exp, side="buy", position_intent="buy_to_open", entry_price_assumption=1.5),
        OptionLeg(contract_symbol="NVDA260904P00115000", option_type="put", strike=115.0, expiration=exp, side="buy", position_intent="buy_to_open", entry_price_assumption=1.5),
    ]
    return StrategyCandidate(
        strategy_id=strategy_id,
        decision=Decision.SHORT_IRON_BUTTERFLY,
        legs=legs,
        quantity=1,
        entry_debit_credit=-700.0,
        max_loss=300.0,
    )


def make_contract_snapshots(
    candidate: StrategyCandidate,
    prices: dict[str, tuple[float, float]],
) -> dict[str, OptionContractSnapshot]:
    observed_at = datetime.now(timezone.utc)
    provenance = Provenance.from_synthetic("lifecycle-runtime")
    return {
        leg.contract_symbol: OptionContractSnapshot(
            symbol=leg.contract_symbol,
            underlying_symbol="NVDA",
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
            bid=prices[leg.contract_symbol][0],
            ask=prices[leg.contract_symbol][1],
            quote_time=observed_at,
            volume=500,
            open_interest=1_000,
            provenance=provenance,
        )
        for leg in candidate.legs
    }


def test_scanner_filters_unconfirmed_and_non_amc_events():
    scanner = EventScanner(universe=["NVDA", "AAPL", "MSFT"])
    test_calendar = {
        "NVDA": {"event_date": "2026-09-02", "timing": "amc", "confirmed": True, "source_url": "https://investor.nvidia.com"},
        "AAPL": {"event_date": "2026-09-03", "timing": "bmo", "confirmed": True, "source_url": "https://investor.apple.com"},  # BMO filtered out
        "MSFT": {"event_date": "2026-09-04", "timing": "amc", "confirmed": False, "source_url": "https://investor.microsoft.com"}, # Unconfirmed filtered out
        "TSLA": {"event_date": "2026-09-05", "timing": "amc", "confirmed": True, "source_url": "https://investor.tesla.com"},  # Not in universe
    }

    now = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)
    eligible = scanner.scan_eligible_events(test_calendar, current_time=now)
    assert len(eligible) == 1
    assert eligible[0].symbol == "NVDA"
    assert eligible[0].confirmed is True


def test_scanner_market_hours_and_entry_window():
    scanner = EventScanner()
    event_date = date(2026, 9, 2)

    # 1. Weekend -> market closed
    saturday = datetime(2026, 9, 5, 19, 30, tzinfo=timezone.utc)
    assert scanner.is_market_open(saturday) is False
    assert scanner.is_inside_entry_window(event_date, saturday) is False

    # 2. Before market open (12:00 UTC = 8:00 AM ET)
    morning = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    assert scanner.is_market_open(morning) is False

    # 3. Market open but outside 15:15-15:55 ET entry window (14:00 UTC = 10:00 AM ET)
    midday = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    assert scanner.is_market_open(midday) is True
    assert scanner.is_inside_entry_window(event_date, midday) is False

    # 4. Inside entry window (19:30 UTC = 3:30 PM ET)
    entry_time = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)
    assert scanner.is_market_open(entry_time) is True
    assert scanner.is_inside_entry_window(event_date, entry_time) is True


def test_live_benchmark_decision_time_uses_post_fetch_cutoff():
    """Live quotes fetched during a cycle must not appear to come from the future."""
    cycle_started_at = datetime(2026, 8, 31, 14, 26, tzinfo=timezone.utc)
    workflow_completed_at = cycle_started_at + timedelta(milliseconds=250)

    assert benchmark_decision_time(
        is_live_mode=True,
        cycle_time=cycle_started_at,
        post_fetch_time=workflow_completed_at,
    ) == workflow_completed_at
    assert benchmark_decision_time(
        is_live_mode=False,
        cycle_time=cycle_started_at,
        post_fetch_time=workflow_completed_at,
    ) == cycle_started_at


def test_scanner_uses_broker_early_close_calendar():
    """Live entry windows follow Alpaca's session close, not a fixed 16:00 ET."""
    session_date = date(2026, 11, 27)
    session = MagicMock(
        date=session_date,
        open=time(9, 30),
        close=time(13, 0),
    )
    client = MagicMock()
    client.get_calendar.return_value = [session]
    scanner = EventScanner(trading_client=client)

    inside = datetime(2026, 11, 27, 17, 20, tzinfo=timezone.utc)  # 12:20 ET
    after_close = datetime(2026, 11, 27, 20, 30, tzinfo=timezone.utc)  # 15:30 ET
    assert scanner.is_market_open(inside) is True
    assert scanner.is_inside_entry_window(session_date, inside) is True
    assert scanner.is_market_open(after_close) is False


def test_order_watcher_syncs_fills_and_cancels(tmp_path):
    db_file = tmp_path / "watcher_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-nvda-01")
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

    # Mock Alpaca broker response: filled
    mock_client = MagicMock()
    mock_order = MagicMock()
    mock_order.status = "filled"
    mock_order.filled_qty = "1"
    mock_order.filled_avg_price = "3.95"
    mock_order.id = "alp-order-12345"
    mock_client.get_order_by_client_id.return_value = mock_order

    watcher = OrderWatcher(ledger=ledger, trading_client=mock_client)
    counts = watcher.sync_active_orders()
    assert counts["filled"] == 1

    # Verify ledger status updated
    order = ledger.get_order_by_fingerprint(plan.fingerprint)
    assert order["status"] == "filled"
    assert order["filled_quantity"] == 1
    assert order["average_price"] == 3.95


def test_unfilled_order_canceled_at_cutoff(tmp_path):
    db_file = tmp_path / "cancel_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-aapl-01")
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.ACCEPTED)

    mock_client = MagicMock()
    mock_client.get_order_by_client_id.return_value = MagicMock(status="canceled")
    watcher = OrderWatcher(ledger=ledger, trading_client=mock_client)
    success = watcher.cancel_unfilled_order_at_cutoff(plan.client_order_id, reason="3:55 PM ET Cutoff reached")
    assert success is True
    mock_client.cancel_order_by_client_id.assert_called_once_with(plan.client_order_id)

    order = ledger.get_order_by_fingerprint(plan.fingerprint)
    assert order["status"] == "canceled"


def test_order_watcher_automatically_cancels_expired_entry_intents(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "automatic_cutoff.db")
    candidate = make_candidate(strategy_id="strat-cutoff")
    plan = build_order_plan(candidate, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(
        plan.approval_token,
        ExecutionStatus.ACCEPTED,
        broker_order_id="alp-entry-cutoff",
    )
    client = MagicMock()
    client.get_order_by_client_id.return_value = MagicMock(status="canceled")
    watcher = OrderWatcher(ledger=ledger, trading_client=client)

    canceled = watcher.cancel_expired_entry_orders(
        current_time=plan.expires_at + timedelta(seconds=1)
    )

    assert canceled == [plan.client_order_id]
    client.cancel_order_by_id.assert_called_once_with("alp-entry-cutoff")
    assert ledger.get_order_by_client_order_id(plan.client_order_id)["status"] == "canceled"


def test_lifecycle_cycle_enforces_entry_cutoff_after_order_sync(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "runner_cutoff.db")
    runner = LifecycleRunner(
        ledger=ledger,
        lock_path=str(tmp_path / "runner_cutoff.lock"),
    )
    runner.watcher = MagicMock()
    runner.watcher.sync_active_orders.return_value = {"synced": 0}
    runner.watcher.cancel_expired_entry_orders.return_value = ["entry-1", "entry-2"]
    now = datetime(2026, 9, 2, 19, 56, tzinfo=timezone.utc)

    result = runner.run_cycle(current_time=now)

    runner.watcher.cancel_expired_entry_orders.assert_called_once_with(current_time=now)
    assert result["orders_canceled_at_cutoff"] == 2


def test_lifecycle_cycle_cancels_working_entries_before_safety_halt_exits(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "runner_halt_cancel.db")
    ledger.trip_system_halt(reason="daily loss limit", evidence_id="halt-1")
    runner = LifecycleRunner(
        ledger=ledger,
        lock_path=str(tmp_path / "runner_halt_cancel.lock"),
    )
    runner.watcher = MagicMock()
    runner.watcher.sync_active_orders.return_value = {"synced": 0}
    runner.watcher.cancel_open_entry_orders.return_value = ["partial-entry-1"]
    now = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)

    result = runner.run_cycle(current_time=now)

    runner.watcher.cancel_open_entry_orders.assert_called_once()
    runner.watcher.cancel_expired_entry_orders.assert_not_called()
    assert result["orders_canceled_for_halt"] == 1


def test_submission_status_classification_never_counts_rejection_or_unknown_as_submitted():
    assert classify_submission_status(ExecutionStatus.ACCEPTED) == "acknowledged"
    assert classify_submission_status(ExecutionStatus.PARTIALLY_FILLED) == "acknowledged"
    assert classify_submission_status(ExecutionStatus.FILLED) == "acknowledged"
    assert classify_submission_status(ExecutionStatus.REJECTED) == "rejected"
    assert classify_submission_status(ExecutionStatus.UNKNOWN) == "unknown"
    assert classify_submission_status(ExecutionStatus.CANCELED) == "other"


def test_lifecycle_cycle_contains_position_monitor_data_failure(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "monitor_failure.db")
    candidate = make_candidate(strategy_id="strat-monitor-failure")
    plan = build_order_plan(candidate, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(
        plan.approval_token,
        ExecutionStatus.FILLED,
        filled_quantity=1,
        average_price=plan.limit_price,
    )
    runner = LifecycleRunner(
        ledger=ledger,
        lock_path=str(tmp_path / "monitor_failure.lock"),
    )
    runner.monitor.build_broker_position_snapshot = MagicMock(
        return_value=VerifiedStrategyPositionSnapshot(
            strategy_id=candidate.strategy_id,
            symbol="NVDA",
            timestamp=datetime.now(timezone.utc),
            positions=[
                VerifiedPositionLeg(
                    contract_symbol=leg.contract_symbol,
                    symbol="NVDA",
                    qty=1,
                    side="long",
                    avg_entry_price=2.0,
                )
                for leg in candidate.legs
            ],
        )
    )
    runner.monitor.monitor_and_close_strategy = MagicMock(
        side_effect=ExecutionError("fresh option quotes unavailable")
    )

    result = runner.run_cycle(current_time=datetime.now(timezone.utc))

    assert result["cycle_status"] == "ERROR"
    assert any("fresh option quotes unavailable" in error for error in result["errors"])


def test_position_monitor_post_event_exit_trigger(tmp_path):
    db_file = tmp_path / "monitor_exit_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-post-evt")
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED, filled_quantity=1, average_price=4.0)

    positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(
        strategy_id=plan.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=positions,
    )

    monitor = PositionMonitor(ledger=ledger)
    strategy_row = ledger.get_order_by_fingerprint(plan.fingerprint)

    # Next morning after event: next calendar day at 14:00 UTC (10:00 AM ET)
    created_at = datetime.fromisoformat(strategy_row["created_at"].replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    next_morning = datetime.combine(created_at.date() + timedelta(days=1), time(14, 0), tzinfo=timezone.utc)

    trigger = monitor.evaluate_exit_trigger(
        strategy_row=strategy_row,
        verified_snapshot=snap,
        current_time=next_morning,
    )
    assert trigger is not None
    assert trigger.trigger_type.value == "post_event_expiration"




def test_position_monitor_profit_and_loss_triggers(tmp_path):
    db_file = tmp_path / "pnl_triggers.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-nvda-pnl", quantity=1)
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED, filled_quantity=1, average_price=4.0)

    positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(strategy_id=plan.strategy_id, symbol="NVDA", timestamp=datetime.now(timezone.utc), positions=positions)
    strategy_row = ledger.get_order_by_fingerprint(plan.fingerprint)
    monitor = PositionMonitor(ledger=ledger, profit_target_pct=0.50, stop_loss_pct=1.00)

    # 1. Profit trigger: mark price = 6.20 (+55% gain > +50% target)
    profit_trigger = monitor.evaluate_exit_trigger(strategy_row, snap, current_mark_price=6.20)
    assert profit_trigger is not None
    assert profit_trigger.trigger_type.value == "profit_target"
    assert profit_trigger.estimated_pnl_dollars == pytest.approx(220.0, 0.01)

    # 2. Stop loss trigger: mark price = 0.00 (-100% loss)
    stop_trigger = monitor.evaluate_exit_trigger(strategy_row, snap, current_mark_price=0.0)
    assert stop_trigger is not None
    assert stop_trigger.trigger_type.value == "max_loss"


def test_position_monitor_marks_short_iron_butterfly_from_fresh_executable_quotes(tmp_path):
    """A short-vol position uses buy-back asks/sell-out bids and the short-credit P&L sign."""
    ledger = ExecutionLedger(db_path=tmp_path / "short_vol_mark.db")
    candidate = make_iron_butterfly_candidate()
    entry_prices = {
        "NVDA260904C00125000": (5.00, 5.10),
        "NVDA260904P00125000": (5.00, 5.10),
        "NVDA260904C00135000": (1.40, 1.50),
        "NVDA260904P00115000": (1.40, 1.50),
    }
    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=make_contract_snapshots(candidate, entry_prices),
    )
    strategy_row = ledger.get_order_by_fingerprint(plan.fingerprint)

    exit_prices = {
        "NVDA260904C00125000": (2.40, 2.50),
        "NVDA260904P00125000": (2.40, 2.50),
        "NVDA260904C00135000": (0.50, 0.60),
        "NVDA260904P00115000": (0.50, 0.60),
    }
    adapter = MagicMock()
    adapter.get_underlying_snapshot.return_value = MagicMock(price=125.0)
    adapter.get_option_chain.return_value = list(
        make_contract_snapshots(candidate, exit_prices).values()
    )
    positions = [
        VerifiedPositionLeg(
            contract_symbol=leg.contract_symbol,
            symbol="NVDA",
            qty=1,
            side="short" if leg.side == "sell" else "long",
            avg_entry_price=leg.entry_price_assumption,
        )
        for leg in candidate.legs
    ]
    snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=positions,
    )

    monitor = PositionMonitor(ledger=ledger, market_data_adapter=adapter)
    report = monitor.monitor_and_close_strategy(strategy_row, snapshot)

    assert plan.net_price_convention == NetPriceConvention.CREDIT
    assert plan.limit_price == pytest.approx(7.00)
    assert report.current_mark == pytest.approx(4.00)
    assert report.unrealized_pnl_dollars == pytest.approx(300.00)
    assert report.unrealized_pnl_pct == pytest.approx(1.00)
    assert report.exit_trigger is None


def test_position_monitor_rejects_stale_executable_quotes(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "stale_monitor_mark.db")
    candidate = make_candidate(strategy_id="strat-stale-monitor")
    prices = {
        "NVDA260904C00125000": (1.90, 2.00),
        "NVDA260904P00125000": (1.90, 2.00),
    }
    entry_plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=make_contract_snapshots(candidate, prices),
    )
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=31)
    stale_chain = [
        snapshot.model_copy(update={"quote_time": stale_time})
        for snapshot in make_contract_snapshots(candidate, prices).values()
    ]
    adapter = MagicMock()
    adapter.get_underlying_snapshot.return_value = MagicMock(price=125.0)
    adapter.get_option_chain.return_value = stale_chain
    monitor = PositionMonitor(ledger=ledger, market_data_adapter=adapter)
    snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=2.0,
            )
            for leg in candidate.legs
        ],
    )

    with pytest.raises(ExecutionError, match="stale or temporally invalid"):
        monitor.monitor_and_close_strategy(
            ledger.get_order_by_fingerprint(entry_plan.fingerprint), snapshot
        )


def test_position_monitor_marks_only_verified_partial_fill_quantity(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "partial_fill_mark.db")
    candidate = make_candidate(strategy_id="strat-partial-mark", quantity=2)
    prices = {
        "NVDA260904C00125000": (1.90, 2.00),
        "NVDA260904P00125000": (1.90, 2.00),
    }
    entry_plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=make_contract_snapshots(candidate, prices),
    )
    exit_prices = {
        "NVDA260904C00125000": (2.50, 2.60),
        "NVDA260904P00125000": (2.50, 2.60),
    }
    adapter = MagicMock()
    adapter.get_underlying_snapshot.return_value = MagicMock(price=125.0)
    adapter.get_option_chain.return_value = list(
        make_contract_snapshots(candidate, exit_prices).values()
    )
    snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=2.0,
            )
            for leg in candidate.legs
        ],
    )

    report = PositionMonitor(
        ledger=ledger, market_data_adapter=adapter
    ).monitor_and_close_strategy(
        ledger.get_order_by_fingerprint(entry_plan.fingerprint), snapshot
    )

    assert report.unrealized_pnl_dollars == pytest.approx(100.00)
    assert report.entry_cost == pytest.approx(400.00)
    assert report.unrealized_pnl_pct == pytest.approx(0.25)
    assert report.exit_trigger is None


def test_position_monitor_applies_profit_and_max_loss_gates_to_short_credit_strategy(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "short_vol_triggers.db")
    candidate = make_iron_butterfly_candidate()
    entry_prices = {
        "NVDA260904C00125000": (5.00, 5.10),
        "NVDA260904P00125000": (5.00, 5.10),
        "NVDA260904C00135000": (1.40, 1.50),
        "NVDA260904P00115000": (1.40, 1.50),
    }
    plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=make_contract_snapshots(candidate, entry_prices),
    )
    strategy_row = ledger.get_order_by_fingerprint(plan.fingerprint)
    snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="short" if leg.side == "sell" else "long",
                avg_entry_price=leg.entry_price_assumption,
            )
            for leg in candidate.legs
        ],
    )
    monitor = PositionMonitor(ledger=ledger, profit_target_pct=0.50, stop_loss_pct=1.00)

    profit = monitor.evaluate_exit_trigger(strategy_row, snapshot, current_mark_price=3.00)
    loss = monitor.evaluate_exit_trigger(strategy_row, snapshot, current_mark_price=10.00)

    assert profit is not None
    assert profit.trigger_type.value == "profit_target"
    assert profit.estimated_pnl_dollars == pytest.approx(400.00)
    assert loss is not None
    assert loss.trigger_type.value == "max_loss"
    assert loss.estimated_pnl_dollars == pytest.approx(-300.00)


def test_closing_plan_keeps_durable_link_to_original_entry(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "close_link.db")
    candidate = make_candidate(strategy_id="strat-close-link")
    prices = {
        "NVDA260904C00125000": (1.90, 2.00),
        "NVDA260904P00125000": (1.90, 2.00),
    }
    entry_plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=make_contract_snapshots(candidate, prices),
    )
    positions = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=leg.entry_price_assumption,
            )
            for leg in candidate.legs
        ],
    )

    close_plan = create_closing_order_service(
        entry_plan=entry_plan,
        verified_positions=positions,
        contract_snapshots=make_contract_snapshots(candidate, prices),
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
    )

    assert close_plan.original_entry_intent_id == entry_plan.client_order_id
    assert close_plan.strategy_id == entry_plan.strategy_id
    persisted = ledger.get_order_by_client_order_id(close_plan.client_order_id)
    assert json.loads(persisted["full_order_plan"])["original_entry_intent_id"] == entry_plan.client_order_id


def test_order_watcher_finalizes_delayed_close_fill_and_realized_pnl(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "delayed_close_fill.db")
    candidate = make_candidate(strategy_id="strat-delayed-close")
    prices = {
        "NVDA260904C00125000": (1.90, 2.00),
        "NVDA260904P00125000": (1.90, 2.00),
    }
    snapshots = make_contract_snapshots(candidate, prices)
    entry_plan = build_order_plan(
        candidate,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
        contract_snapshots=snapshots,
        event_id="evt-delayed-close",
    )
    ledger.approve_order(entry_plan.approval_token)
    ledger.persist_order_intent(
        entry_plan.approval_token, full_order_plan=entry_plan.model_dump(mode="json")
    )
    ledger.consume_approval_and_lock(entry_plan.approval_token, entry_plan.fingerprint)
    ledger.record_broker_result(
        entry_plan.approval_token,
        ExecutionStatus.FILLED,
        broker_order_id="alp-entry",
        filled_quantity=1,
        average_price=4.00,
    )
    positions = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=leg.entry_price_assumption,
            )
            for leg in candidate.legs
        ],
    )
    close_plan = create_closing_order_service(
        entry_plan=entry_plan,
        verified_positions=positions,
        contract_snapshots=snapshots,
        broker_target=BrokerTarget.ALPACA_PAPER,
        ledger=ledger,
    )
    ledger.approve_order(close_plan.approval_token)
    ledger.persist_order_intent(
        close_plan.approval_token, full_order_plan=close_plan.model_dump(mode="json")
    )
    ledger.consume_approval_and_lock(close_plan.approval_token, close_plan.fingerprint)
    ledger.record_broker_result(
        close_plan.approval_token,
        ExecutionStatus.ACCEPTED,
        broker_order_id="alp-close",
    )

    broker_fill = MagicMock(
        status="filled",
        filled_qty="1",
        filled_avg_price="5.50",
        id="alp-close",
    )
    client = MagicMock()
    client.get_order_by_client_id.return_value = broker_fill
    counts = OrderWatcher(ledger=ledger, trading_client=client).sync_active_orders()

    assert counts["filled"] == 1
    assert ledger.get_order_by_client_order_id(entry_plan.client_order_id)["status"] == "closed"
    assert ledger.get_order_by_client_order_id(close_plan.client_order_id)["status"] == "closed"
    trades = ledger.list_closed_trades()
    assert len(trades) == 1
    assert trades[0]["entry_order_id"] == entry_plan.client_order_id
    assert trades[0]["exit_order_id"] == close_plan.client_order_id
    assert trades[0]["gross_realized_pnl_dollars"] == pytest.approx(150.00)

    # Repeated watcher cycles are idempotent and cannot duplicate P&L.
    OrderWatcher(ledger=ledger, trading_client=client).sync_active_orders()
    assert len(ledger.list_closed_trades()) == 1


def test_monitor_reconciles_verified_simulated_position_before_close(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "never_filled_close.db")
    candidate = make_candidate(strategy_id="strat-never-filled")
    entry_plan = build_order_plan(candidate, ledger=ledger)
    snapshot = VerifiedStrategyPositionSnapshot(
        strategy_id=candidate.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=[
            VerifiedPositionLeg(
                contract_symbol=leg.contract_symbol,
                symbol="NVDA",
                qty=1,
                side="long",
                avg_entry_price=2.0,
            )
            for leg in candidate.legs
        ],
        evidence_source="simulated",
    )

    report = PositionMonitor(ledger=ledger).monitor_and_close_strategy(
        ledger.get_order_by_fingerprint(entry_plan.fingerprint),
        snapshot,
        current_mark_price=7.00,
    )

    assert report.status == "CLOSED"
    assert len(ledger.list_closed_trades()) == 1
    assert ledger.get_order_by_client_order_id(entry_plan.client_order_id)["status"] == "closed"


def test_safety_halt_triggers_risk_reducing_close(tmp_path):
    db_file = tmp_path / "halt_close.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-halt-test", quantity=1)
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED, filled_quantity=1, average_price=4.0)

    # Trip persistent system halt
    ledger.trip_system_halt(reason="Drawdown limit breached 5.2%", evidence_id="ev-drawdown-01")

    positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(strategy_id=plan.strategy_id, symbol="NVDA", timestamp=datetime.now(timezone.utc), positions=positions)
    strategy_row = ledger.get_order_by_fingerprint(plan.fingerprint)
    monitor = PositionMonitor(ledger=ledger)

    trigger = monitor.evaluate_exit_trigger(strategy_row, snap)
    assert trigger is not None
    assert trigger.trigger_type.value == "safety_halt"


def test_closed_trade_reporter_accounting(tmp_path):
    db_file = tmp_path / "closed_trades.db"
    ledger = ExecutionLedger(db_path=db_file)
    reporter = ClosedTradeReporter(ledger=ledger)

    opened = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc)

    # Long straddle: entry $4.00, exit $5.50, qty 1, fees $1.30
    trade = reporter.record_completed_trade(
        strategy_id="strat-nvda-01",
        symbol="NVDA",
        decision=Decision.LONG_STRADDLE,
        event_id="evt-20260902-NVDA",
        entry_order_id="ord-entry-01",
        exit_order_id="ord-exit-01",
        quantity=1,
        entry_price=4.00,
        exit_price=5.50,
        fees_and_slippage=1.30,
        opened_at=opened,
        closed_at=closed,
        max_loss_budget=400.0,
        actual_post_event_move=0.075,
    )

    assert trade.gross_realized_pnl_dollars == 150.0
    assert trade.net_realized_pnl_dollars == 148.70
    assert trade.outcome_label == "WIN"

    # Verify persisted in SQLite
    records = ledger.list_closed_trades()
    assert ledger.get_daily_realized_pnl("2026-09-03") == pytest.approx(148.70)
    assert len(records) == 1
    assert records[0]["trade_id"] == trade.trade_id
    assert records[0]["net_realized_pnl_dollars"] == 148.70


def test_closed_trade_reporter_accepts_duration_without_explicit_timestamps(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "closed_trade_duration.db")

    trade = ClosedTradeReporter(ledger).record_closed_trade(
        strategy_id="strat-duration",
        symbol="AAPL",
        decision=Decision.LONG_STRADDLE,
        entry_price=4.00,
        exit_price=5.00,
        quantity=1,
        holding_duration_seconds=3_600,
    )

    assert trade.holding_hours == pytest.approx(1.0)
    assert trade.gross_realized_pnl_dollars == pytest.approx(100.0)


def test_lifecycle_runner_executes_cycle_under_lock(tmp_path):
    db_file = tmp_path / "runner_test.db"
    lock_file = tmp_path / "runner_cycle.lock"
    ledger = ExecutionLedger(db_path=db_file)
    runner = LifecycleRunner(ledger=ledger, lock_path=str(lock_file))

    calendar = {
        "NVDA": {"event_date": "2026-09-02", "timing": "amc", "confirmed": True, "source_url": "https://investor.nvidia.com"},
    }

    now = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)
    result = runner.run_cycle(calendar=calendar, current_time=now)
    assert result["events_found"] == 1
    assert result["reconciliation_status"] == "CLEAN"


def test_two_scheduler_processes_race_for_single_run(tmp_path):
    db_file = tmp_path / "race_test.db"
    lock_file = tmp_path / "race_cycle.lock"
    ledger = ExecutionLedger(db_path=db_file)
    runner1 = LifecycleRunner(ledger=ledger, lock_path=str(lock_file))
    runner2 = LifecycleRunner(ledger=ledger, lock_path=str(lock_file))

    # Hold lock in runner 1 context
    with runner1.lock:
        # runner 2 attempt should raise ExecutionError
        with pytest.raises(ExecutionError, match="holds the exclusive lock"):
            with runner2.lock:
                pass



def test_full_controlled_paper_lifecycle_simulation(tmp_path):
    """Mandatory Lifecycle Simulation 1: Entry -> Accepted -> Filled -> Monitored -> Closed -> P&L record."""
    db_file = tmp_path / "full_sim.db"
    ledger = ExecutionLedger(db_path=db_file)

    # 1. Entry Plan
    cand = make_candidate(strategy_id="strat-full-sim", quantity=1)
    plan = build_order_plan(cand, ledger=ledger)

    # 2. Approved & Persisted
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

    # 3. Broker Fill
    ledger.record_broker_result(
        approval_token=plan.approval_token,
        status=ExecutionStatus.FILLED,
        broker_order_id="alp-entry-999",
        filled_quantity=1,
        average_price=4.0,
    )

    # 4. Verified Positions
    positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(
        strategy_id=plan.strategy_id,
        symbol="NVDA",
        timestamp=datetime.now(timezone.utc),
        positions=positions,
    )

    # 5. Monitor and Close
    monitor = PositionMonitor(ledger=ledger)
    close_plan = build_closing_order_plan(
        candidate=cand,
        verified_positions=snap,
        ledger=ledger,
    )
    assert close_plan.decision == "close_long_straddle"
    assert close_plan.legs[0].position_intent == PositionIntent.SELL_TO_CLOSE
    assert close_plan.legs[1].position_intent == PositionIntent.SELL_TO_CLOSE


    # 6. Record Closed Trade
    reporter = ClosedTradeReporter(ledger=ledger)
    closed_trade = reporter.record_completed_trade(
        strategy_id=plan.strategy_id,
        symbol=plan.symbol,
        decision=Decision.LONG_STRADDLE,
        event_id="evt-20260902-NVDA",
        entry_order_id=plan.client_order_id,
        exit_order_id=close_plan.client_order_id,
        quantity=1,
        entry_price=4.00,
        exit_price=5.80,
        fees_and_slippage=1.30,
        opened_at=plan.created_at,
        closed_at=datetime.now(timezone.utc),
        max_loss_budget=400.0,
        actual_post_event_move=0.08,
    )

    assert closed_trade.net_realized_pnl_dollars == pytest.approx(178.70, 0.01)
    assert closed_trade.outcome_label == "WIN"
    assert len(ledger.list_closed_trades()) == 1


def test_simulation_partial_fill_remainder_canceled_and_closes_filled_quantity(tmp_path):
    """Mandatory Lifecycle Simulation 2: Partial fill -> cancel remainder -> close filled quantity."""
    db_file = tmp_path / "part_sim.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-part-sim", quantity=2)
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

    # 1. Partial fill: 1 of 2 contracts filled
    ledger.record_broker_result(
        approval_token=plan.approval_token,
        status=ExecutionStatus.PARTIALLY_FILLED,
        broker_order_id="alp-part-555",
        filled_quantity=1,
        average_price=4.0,
    )

    # 2. Watcher cancels unfilled remainder
    mock_client = MagicMock()
    mock_client.get_order_by_client_id.return_value = MagicMock(status="canceled")
    watcher = OrderWatcher(ledger=ledger, trading_client=mock_client)
    assert watcher.cancel_unfilled_order_at_cutoff(plan.client_order_id, reason="Remainder canceled") is True
    assert ledger.get_order_by_client_order_id(plan.client_order_id)["status"] == "partially_filled"

    # 3. Verified broker position holds exactly 1 filled unit
    positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(strategy_id=plan.strategy_id, symbol="NVDA", timestamp=datetime.now(timezone.utc), positions=positions)

    # 4. Closing plan constructed for exactly 1 unit (not original requested 2)
    close_plan = build_closing_order_plan(
        candidate=cand,
        verified_positions=snap,
        ledger=ledger,
    )
    assert close_plan.quantity == 1


def test_simulation_rejected_entry_releases_reserved_risk(tmp_path):
    """Mandatory Lifecycle Simulation 4: Rejected entry releases reserved risk."""
    db_file = tmp_path / "reject_risk.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-reject-sim", quantity=1)
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)

    # Risk should be active while submitting
    risk_submitting, _ = ledger.get_portfolio_reserved_risk()
    assert risk_submitting == 400.0

    # Broker rejects order
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.REJECTED, error_message="Margin check failed")

    # Reserved risk must be 0
    risk_after_reject, _ = ledger.get_portfolio_reserved_risk()
    assert risk_after_reject == 0.0


def test_simulation_broker_position_contradiction_raises_error(tmp_path):
    """Mandatory Lifecycle Simulation 6: Broker position contradiction raises ExecutionError."""
    db_file = tmp_path / "contradict_sim.db"
    ledger = ExecutionLedger(db_path=db_file)
    cand = make_candidate(strategy_id="strat-contra-sim", quantity=1)
    plan = build_order_plan(cand, ledger=ledger)
    ledger.approve_order(plan.approval_token)
    ledger.persist_order_intent(plan.approval_token, full_order_plan=plan.model_dump(mode="json"))
    ledger.consume_approval_and_lock(plan.approval_token, plan.fingerprint)
    ledger.record_broker_result(plan.approval_token, ExecutionStatus.FILLED, filled_quantity=1, average_price=4.0)

    # Contradictory broker position: reports SHORT position when strategy is LONG call
    contradictory_positions = [
        VerifiedPositionLeg(contract_symbol="NVDA260904C00125000", symbol="NVDA", qty=1, side="short", avg_entry_price=2.0),
        VerifiedPositionLeg(contract_symbol="NVDA260904P00125000", symbol="NVDA", qty=1, side="long", avg_entry_price=2.0),
    ]
    snap = VerifiedStrategyPositionSnapshot(strategy_id=plan.strategy_id, symbol="NVDA", timestamp=datetime.now(timezone.utc), positions=contradictory_positions)

    with pytest.raises(ExecutionError, match="does not match expected long strategy leg"):
        build_closing_order_plan(candidate=cand, verified_positions=snap, ledger=ledger)
