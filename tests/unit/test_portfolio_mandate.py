"""Unit and adversarial tests for Milestone 2: Portfolio Mandate, Account State & Autonomous Order Gate."""

from datetime import date, datetime, timezone
import pytest

from volagent.config import MandateConfig
from volagent.domain.enums import Decision, GateStatus
from volagent.domain.portfolio import PortfolioSnapshot
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.errors import ExecutionError
from volagent.execution.ledger import ExecutionLedger
from volagent.execution.runtime_lock import SingleRuntimeLock
from volagent.quant.portfolio_gate import evaluate_portfolio_gate, get_symbol_sector


def test_competition_ledger_rejects_paper_account_switch(tmp_path):
    ledger = ExecutionLedger(db_path=tmp_path / "account_binding.db")
    first = ledger.get_or_init_competition_metadata(paper_account_id="paper-account-a")
    assert first["paper_account_id"] == "paper-account-a"
    with pytest.raises(ExecutionError, match="different Alpaca paper account"):
        ledger.get_or_init_competition_metadata(paper_account_id="paper-account-b")


def make_test_candidate(
    decision: Decision = Decision.LONG_STRADDLE,
    max_loss: float = 400.0,
    entry_cost: float = 400.0,
    quantity: int = 1,
) -> StrategyCandidate:
    legs = [
        OptionLeg(
            contract_symbol="NVDA260904C00120000",
            option_type="call",
            strike=120.0,
            expiration=date(2026, 9, 4),
            side="buy",
            entry_price_assumption=2.0,
            delta=0.5,
            gamma=0.05,
            theta=-0.1,
            vega=0.15,
        ),
        OptionLeg(
            contract_symbol="NVDA260904P00120000",
            option_type="put",
            strike=120.0,
            expiration=date(2026, 9, 4),
            side="buy",
            entry_price_assumption=2.0,
            delta=-0.5,
            gamma=0.05,
            theta=-0.1,
            vega=0.15,
        ),
    ]
    return StrategyCandidate(
        strategy_id="strat-test-01",
        decision=decision,
        legs=legs,
        max_profit=float("inf"),
        max_loss=max_loss,
        entry_debit_credit=entry_cost,
        net_delta=0.0,
        net_gamma=0.10,
        net_theta=-0.20,
        net_vega=0.30,
        risk_adjusted_score=1.5,
        liquidity_score=0.90,
        quantity=quantity,
    )



def test_competition_metadata_initialization(tmp_path):
    db_file = tmp_path / "metadata_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    meta = ledger.get_or_init_competition_metadata(starting_nav=100000.0)
    assert meta["starting_nav"] == 100000.0
    assert meta["competition_id"] == "caisheng-options-alpha-2026"
    assert meta["mandate_version"] == "caisheng-mandate-v1"

    # Second call returns existing record without re-initializing
    meta2 = ledger.get_or_init_competition_metadata(starting_nav=50000.0)
    assert meta2["starting_nav"] == 100000.0


def test_valid_trade_passes_portfolio_gate():
    mandate = MandateConfig()
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=1,
        new_entries_today_count=0,
        reserved_risk_dollars=400.0,
        sector_reserved_risk={"technology": 400.0},
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=400.0, entry_cost=400.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        underlying_symbol="NVDA",
    )
    assert report.overall_status == GateStatus.PASS
    assert report.approved_quantity == 1
    assert report.reserved_risk_after == 800.0
    assert report.risk_reservation_ref is not None


def test_third_open_strategy_rejected_by_portfolio_gate():
    mandate = MandateConfig(max_open_strategies=3)
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=3,  # Already at maximum 3 open strategies
        new_entries_today_count=1,
        reserved_risk_dollars=1200.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=300.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("max_open_strategies" in r for r in report.rejection_reasons)


def test_sector_concentration_rejected_by_portfolio_gate():
    mandate = MandateConfig(max_same_sector_reserved_risk=1000.0)
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=1,
        new_entries_today_count=0,
        reserved_risk_dollars=800.0,
        sector_reserved_risk={"technology": 800.0},
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    # NVDA is in technology sector -> $800 + $300 = $1,100 > $1,000 cap
    cand = make_test_candidate(max_loss=300.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        underlying_symbol="NVDA",
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("sector_risk_cap" in r for r in report.rejection_reasons)


def test_daily_loss_exceeding_1500_trips_persistent_halt(tmp_path):
    db_file = tmp_path / "halt_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    mandate = MandateConfig(daily_loss_halt_dollars=1500.0)

    portfolio = PortfolioSnapshot(
        equity=98400.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        daily_realized_pl=-1200.0,
        daily_unrealized_pl=-400.0,  # Total daily loss = -$1,600 <= -$1,500
        open_strategies_count=0,
        new_entries_today_count=0,
        reserved_risk_dollars=0.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=300.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        ledger=ledger,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("daily_loss_limit" in r for r in report.rejection_reasons)

    # Verify persistent halt is tripped in ledger
    is_halted, reason = ledger.is_system_halted()
    assert is_halted is True
    assert "Daily loss limit breached" in reason


def test_drawdown_exceeding_5_percent_trips_persistent_drawdown_halt(tmp_path):
    db_file = tmp_path / "drawdown_halt_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    mandate = MandateConfig(drawdown_halt_pct=0.05)

    portfolio = PortfolioSnapshot(
        equity=94000.0,  # Drawdown = (100k - 94k) / 100k = 6.0% > 5.0%
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=0,
        new_entries_today_count=0,
        reserved_risk_dollars=0.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=300.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        ledger=ledger,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("drawdown_limit" in r for r in report.rejection_reasons)

    is_halted, reason = ledger.is_system_halted()
    assert is_halted is True
    assert "Competition drawdown limit breached" in reason


def test_stale_or_missing_account_snapshot_fails_closed():
    mandate = MandateConfig()
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=0,
        new_entries_today_count=0,
        reserved_risk_dollars=0.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=True,  # Stale broker data
    )
    cand = make_test_candidate(max_loss=300.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("fresh_account_snapshot" in r for r in report.rejection_reasons)


def test_insufficient_buying_power_rejected():
    mandate = MandateConfig()
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=200.0,
        buying_power=200.0,  # Only $200 buying power
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=0,
        new_entries_today_count=0,
        reserved_risk_dollars=0.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=300.0, entry_cost=400.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("sufficient_buying_power" in r for r in report.rejection_reasons)


def test_strategy_max_loss_cap_at_1_percent_equity():
    mandate = MandateConfig(absolute_max_loss_nav_pct=0.01)
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=0,
        new_entries_today_count=0,
        reserved_risk_dollars=0.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    # $1,050 > 1.0% of $100,000 ($1,000)
    cand = make_test_candidate(max_loss=1050.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("strategy_max_loss_cap" in r for r in report.rejection_reasons)


def test_total_reserved_risk_cap_at_2_percent_equity():
    mandate = MandateConfig(max_total_reserved_risk_nav_pct=0.02)
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=2,
        new_entries_today_count=1,
        reserved_risk_dollars=1600.0,  # + $500 = $2,100 > $2,000 (2.0% equity)
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=500.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("total_reserved_risk_cap" in r for r in report.rejection_reasons)


def test_max_daily_entries_limit_at_2():
    mandate = MandateConfig(max_new_entries_per_day=2)
    portfolio = PortfolioSnapshot(
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=1,
        new_entries_today_count=2,  # Already 2 entries today
        reserved_risk_dollars=400.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=400.0)
    report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
    )
    assert report.overall_status == GateStatus.FAIL
    assert any("max_daily_entries" in r for r in report.rejection_reasons)


def test_concurrent_runtime_lock_race_grants_single_owner(tmp_path):
    lock_file = tmp_path / "scheduler.lock"
    lock1 = SingleRuntimeLock(lock_path=lock_file)
    lock2 = SingleRuntimeLock(lock_path=lock_file)

    # First lock acquires successfully
    with lock1:
        # Second lock attempt raises ExecutionError
        with pytest.raises(ExecutionError, match="Another CaiSheng runtime instance holds the exclusive lock"):
            lock2.acquire()

    # After release, lock2 can acquire successfully
    with lock2:
        assert True


def test_kill_switch_and_halts_persist_across_process_restart(tmp_path):
    db_file = tmp_path / "persistent_halt_test.db"
    ledger1 = ExecutionLedger(db_path=db_file)
    ledger1.trip_system_halt("Operator manual emergency halt triggered.")

    is_halted1, reason1 = ledger1.is_system_halted()
    assert is_halted1 is True

    # Simulate restart by creating new independent ledger connection
    ledger2 = ExecutionLedger(db_path=db_file)
    is_halted2, reason2 = ledger2.is_system_halted()
    assert is_halted2 is True
    assert "Operator manual emergency halt" in reason2


def test_risk_reducing_close_remains_permitted_during_entry_halt(tmp_path):
    db_file = tmp_path / "close_during_halt.db"
    ledger = ExecutionLedger(db_path=db_file)
    ledger.trip_system_halt("Drawdown halt active.")
    mandate = MandateConfig()

    portfolio = PortfolioSnapshot(
        equity=94000.0,
        cash=50000.0,
        buying_power=50000.0,
        initial_nav=100000.0,
        high_water_equity=100000.0,
        open_strategies_count=1,
        new_entries_today_count=0,
        reserved_risk_dollars=500.0,
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    cand = make_test_candidate(max_loss=500.0)

    # New entry attempt fails
    entry_report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        ledger=ledger,
        is_close_order=False,
    )
    assert entry_report.overall_status == GateStatus.FAIL
    assert any("halt_state" in r for r in entry_report.rejection_reasons)

    # Closing order passes
    close_report = evaluate_portfolio_gate(
        candidate=cand,
        decision=Decision.LONG_STRADDLE,
        portfolio=portfolio,
        mandate_config=mandate,
        ledger=ledger,
        is_close_order=True,
    )
    assert close_report.overall_status == GateStatus.PASS


def test_snapshot_persistence_and_retrieval(tmp_path):
    db_file = tmp_path / "snap_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    snapshot = PortfolioSnapshot(
        equity=101500.0,
        cash=60000.0,
        buying_power=60000.0,
        initial_nav=100000.0,
        high_water_equity=102000.0,
        daily_realized_pl=1200.0,
        daily_unrealized_pl=300.0,
        open_strategies_count=2,
        new_entries_today_count=1,
        reserved_risk_dollars=750.0,
        sector_reserved_risk={"technology": 750.0},
        timestamp=datetime.now(timezone.utc),
        is_stale=False,
    )
    ledger.record_portfolio_snapshot(snapshot)
    retrieved = ledger.get_latest_portfolio_snapshot()
    assert retrieved is not None
    assert retrieved["equity"] == 101500.0
    assert retrieved["sector_reserved_risk"] == {"technology": 750.0}
    assert retrieved["open_strategies_count"] == 2
