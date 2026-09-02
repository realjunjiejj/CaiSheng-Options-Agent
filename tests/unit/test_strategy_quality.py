"""Unit and adversarial tests for Milestone 4: Agent & Strategy Quality, Dialectic Consensus, Allocator, OOD, and Shadow-Book."""

from datetime import date, datetime, timezone
import pytest

from volagent.config import MandateConfig, VolAgentSettings
from volagent.domain.decision_record import DecisionRecord, SnapshotMetadata, StrategyProposal, VolatilityView
from volagent.domain.enums import Decision, GateStatus, NetPriceConvention, OptionType
from volagent.domain.events import EarningsEvent
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.state import CriticReport, VolAgentState
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.evaluation.shadow_book import ShadowBookEvaluator
from volagent.execution.ledger import ExecutionLedger
from volagent.graph.nodes import strategy_and_risk_node
from volagent.quant.allocator import CandidateEvaluation, PortfolioAllocator
from volagent.quant.expected_move import ImpliedMoveMetrics
from volagent.quant.ood import detect_out_of_distribution
from volagent.quant.strategy_selector import select_best_strategy


def make_test_candidate(strategy_id: str, decision: Decision, max_loss: float, score: float, qty: int = 1) -> StrategyCandidate:
    exp = date(2026, 9, 4)
    legs = [
        OptionLeg(contract_symbol="NVDA260904C00125000", option_type="call", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=2.0),
        OptionLeg(contract_symbol="NVDA260904P00125000", option_type="put", strike=125.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=2.0),
    ]
    return StrategyCandidate(
        strategy_id=strategy_id,
        decision=decision,
        legs=legs,
        quantity=qty,
        entry_debit_credit=4.0,
        max_loss=max_loss,
        risk_adjusted_score=score,
    )


def test_decision_record_schema_and_hash_integrity():
    """Criterion 8: DecisionRecord adheres to schema caisheng.decision.v1 with deterministic SHA-256 hash."""
    snap = SnapshotMetadata(
        symbol="AAPL",
        spot=220.0,
        underlying_quote_time="2026-08-28T14:30:00Z",
        option_snapshot_time="2026-08-28T14:30:00Z",
        event_id="evt-20260828-AAPL",
        event_time="2026-08-28T20:00:00Z",
        event_source_url="https://ir.apple.com",
    )
    vol = VolatilityView(
        implied_move_bid_pct=0.038,
        implied_move_ask_pct=0.041,
        expected_move_median_pct=0.048,
        q20_pct=0.02,
        q80_pct=0.08,
        expected_iv_crush_points=-15.0,
        forecast_confidence=0.85,
    )
    prop = StrategyProposal(
        strategy="LONG_STRADDLE",
        executable_edge_pct=0.007,
        expected_pnl_dollars=120.0,
        max_loss_dollars=400.0,
        risk_adjusted_score=1.75,
    )
    from volagent.domain.decision_record import CriticSummary, RiskSummary

    rec = DecisionRecord.create_and_hash(
        decision_id="dec-20260828-AAPL-01",
        run_id="run-101",
        strategy_version="caisheng-1.0.0",
        mode="alpaca_paper",
        status="APPROVED",
        generated_at="2026-08-28T14:30:00Z",
        snapshot=snap,
        volatility_view=vol,
        proposals=[prop],
        selected_action="LONG_STRADDLE",
        selected_strategy_id="strat-aapl-01",
        quantity=1,
        risk=RiskSummary(
            current_equity=100_000.0,
            reserved_risk_before=0.0,
            reserved_risk_after=400.0,
            hard_checks=["MAX_LOSS_CAP: PASS"],
        ),
        critic=CriticSummary(recommendation="continue"),
    )

    assert rec.schema_version == "caisheng.decision.v1"
    assert rec.selected_action == "LONG_STRADDLE"
    assert len(rec.artifact_hash) == 64
    assert rec.compute_hash() == rec.artifact_hash


def test_ood_detector_triggers_on_anomalous_regimes():
    """Criterion 7: Out-of-distribution detector flags anomalous IV, spreads, and jump dispersion."""
    # 1. Extreme IV > 200%
    res_iv = detect_out_of_distribution(spot=100.0, atm_iv=2.50, implied_move_pct=0.15, expected_move_median_pct=0.05)
    assert res_iv.is_out_of_distribution is True
    assert any("maximum safe ceiling" in r for r in res_iv.reasons)

    # 2. Extreme Option Spread > 25% of mid
    res_spread = detect_out_of_distribution(spot=100.0, atm_iv=0.50, implied_move_pct=0.05, expected_move_median_pct=0.05, atm_bid=1.0, atm_ask=2.0)
    assert res_spread.is_out_of_distribution is True
    assert any("bid-ask spread" in r for r in res_spread.reasons)

    # 3. Extreme Jump Dispersion > 3.5x median
    res_jump = detect_out_of_distribution(spot=100.0, atm_iv=0.50, implied_move_pct=0.05, expected_move_median_pct=0.04, historical_move_std=0.20)
    assert res_jump.is_out_of_distribution is True
    assert any("Historical move dispersion" in r for r in res_jump.reasons)

    # 4. Normal input passes clean
    res_clean = detect_out_of_distribution(spot=100.0, atm_iv=0.45, implied_move_pct=0.05, expected_move_median_pct=0.05, atm_bid=2.40, atm_ask=2.50, historical_move_std=0.05)
    assert res_clean.is_out_of_distribution is False
    assert len(res_clean.reasons) == 0


def test_portfolio_allocator_ranks_and_allocates_top_candidates():
    """Criterion 3: Portfolio allocator ranks candidates across multiple earnings events by risk-adjusted edge."""
    allocator = PortfolioAllocator(mandate=MandateConfig(max_new_entries_per_day=2, max_total_reserved_risk_nav_pct=0.02))

    c1 = make_test_candidate("strat-nvda", Decision.LONG_STRADDLE, max_loss=400.0, score=2.50)
    c2 = make_test_candidate("strat-aapl", Decision.LONG_STRADDLE, max_loss=350.0, score=1.80)
    c3 = make_test_candidate("strat-msft", Decision.LONG_STRADDLE, max_loss=300.0, score=0.90)

    evals = [
        CandidateEvaluation("NVDA", "evt-nvda", c1, Decision.LONG_STRADDLE, executable_edge_pct=0.025, max_loss_dollars=400.0, risk_adjusted_score=2.50, proposals=[]),
        CandidateEvaluation("AAPL", "evt-aapl", c2, Decision.LONG_STRADDLE, executable_edge_pct=0.018, max_loss_dollars=350.0, risk_adjusted_score=1.80, proposals=[]),
        CandidateEvaluation("MSFT", "evt-msft", c3, Decision.LONG_STRADDLE, executable_edge_pct=0.009, max_loss_dollars=300.0, risk_adjusted_score=0.90, proposals=[]),
    ]

    result = allocator.rank_and_allocate(evals, current_equity=100_000.0)

    # Top 2 candidates accepted (NVDA and AAPL)
    assert len(result.accepted_candidates) == 2
    assert result.accepted_candidates[0].strategy_id == "strat-nvda"
    assert result.accepted_candidates[1].strategy_id == "strat-aapl"

    # 3rd candidate rejected due to daily entries limit (2)
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0][0].strategy_id == "strat-msft"
    assert "Max daily entry limit" in result.rejected_candidates[0][1]


def test_portfolio_allocator_respects_total_reserved_risk_budget():
    """Criterion 3: Portfolio allocator halts when total reserved risk reaches 2.0% NAV cap."""
    allocator = PortfolioAllocator(mandate=MandateConfig(max_new_entries_per_day=5, max_total_reserved_risk_nav_pct=0.02, absolute_max_loss_nav_pct=0.01))

    # Three candidates ($900, $800, $800 max loss on $100k equity; single limit is $1,000, total limit is $2,000)
    c1 = make_test_candidate("strat-1", Decision.LONG_STRADDLE, max_loss=900.0, score=3.0)
    c2 = make_test_candidate("strat-2", Decision.LONG_STRADDLE, max_loss=800.0, score=2.0)
    c3 = make_test_candidate("strat-3", Decision.LONG_STRADDLE, max_loss=800.0, score=1.0)

    evals = [
        CandidateEvaluation("SYM1", "evt-1", c1, Decision.LONG_STRADDLE, executable_edge_pct=0.03, max_loss_dollars=900.0, risk_adjusted_score=3.0, proposals=[]),
        CandidateEvaluation("SYM2", "evt-2", c2, Decision.LONG_STRADDLE, executable_edge_pct=0.02, max_loss_dollars=800.0, risk_adjusted_score=2.0, proposals=[]),
        CandidateEvaluation("SYM3", "evt-3", c3, Decision.LONG_STRADDLE, executable_edge_pct=0.01, max_loss_dollars=800.0, risk_adjusted_score=1.0, proposals=[]),
    ]

    result = allocator.rank_and_allocate(evals, current_equity=100_000.0)
    assert len(result.accepted_candidates) == 2
    assert result.accepted_candidates[0].strategy_id == "strat-1"
    assert result.accepted_candidates[1].strategy_id == "strat-2"
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0][0].strategy_id == "strat-3"
    assert "exceeds total limit" in result.rejected_candidates[0][1]


def test_shadow_book_evaluator_records_counterfactual_payoffs(tmp_path):
    """Criterion 6: Shadow-book recording captures selected strategy and counterfactual alternatives."""
    db_file = tmp_path / "shadow_test.db"
    ledger = ExecutionLedger(db_path=db_file)
    evaluator = ShadowBookEvaluator(ledger=ledger)

    snap = SnapshotMetadata(symbol="NVDA", spot=125.0, underlying_quote_time="2026-08-28T14:30:00Z", option_snapshot_time="2026-08-28T14:30:00Z", event_id="evt-nvda", event_time="2026-08-28T20:00:00Z", event_source_url="https://ir.nvidia.com")
    vol = VolatilityView(implied_move_bid_pct=0.04, implied_move_ask_pct=0.05, expected_move_median_pct=0.08, q20_pct=0.04, q80_pct=0.12, expected_iv_crush_points=-15.0, forecast_confidence=0.85)
    from volagent.domain.decision_record import CriticSummary, RiskSummary

    rec = DecisionRecord.create_and_hash(
        decision_id="dec-nvda-1",
        run_id="run-1",
        strategy_version="caisheng-1.0.0",
        mode="alpaca_paper",
        status="APPROVED",
        generated_at="2026-08-28T14:30:00Z",
        snapshot=snap,
        volatility_view=vol,
        proposals=[],
        selected_action="LONG_STRADDLE",
        selected_strategy_id="strat-nvda-1",
        quantity=1,
        risk=RiskSummary(current_equity=100_000.0, reserved_risk_before=0.0, reserved_risk_after=400.0),
        critic=CriticSummary(),
    )

    # Actual post-event move is +8.0% ($10 move on $125 spot)
    shadow_record = evaluator.evaluate_shadow_record(
        decision_record=rec,
        actual_post_event_move_pct=0.08,
        actual_post_event_iv_crush_pts=16.0,
        straddle_entry_price=4.00,
        butterfly_entry_credit=2.50,
        butterfly_wing_width=5.00,
    )

    assert shadow_record.selected_action == "LONG_STRADDLE"
    assert shadow_record.selected_strategy_pnl == pytest.approx(600.0, 0.1)  # ($10 exit - $4 entry) * 100
    assert len(shadow_record.counterfactual_proposals) == 2

    # Check persistence in SQLite
    saved = ledger.list_shadow_book_records()
    assert len(saved) == 1
    assert saved[0]["shadow_id"] == shadow_record.shadow_id
    assert saved[0]["selected_strategy_pnl"] == 600.0


def test_strategy_and_risk_node_emits_valid_decision_record():
    """Criterion 4 & 8: One scan emits exactly one DecisionRecord with exactly one selected action."""
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    from volagent.domain.enums import DataMode, EventTiming
    from volagent.provenance import Provenance
    prov = Provenance(
        source_name="Test Calendar",
        source_uri="https://ir.nvidia.com",
        retrieved_at=now,
        observed_at=now,
        content_hash="test-hash-nvda",
        data_mode=DataMode.LIVE,
    )
    ev = EarningsEvent(
        event_id="evt-20260902-NVDA",
        symbol="NVDA",
        event_date=date(2026, 9, 2),
        event_time=now,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        source_url="https://ir.nvidia.com",
        decision_time=now,
        exit_time=now + timedelta(hours=18),
        provenance=prov,
    )

    underlying = UnderlyingSnapshot(symbol="NVDA", price=125.0, quote_time=now, provenance=prov)

    exp = date(2026, 9, 4)
    c_atm = OptionContractSnapshot(symbol="NVDA260904C00125000", underlying_symbol="NVDA", expiration=exp, strike=125.0, option_type="call", bid=2.40, ask=2.50, quote_time=now, provenance=prov)
    p_atm = OptionContractSnapshot(symbol="NVDA260904P00125000", underlying_symbol="NVDA", expiration=exp, strike=125.0, option_type="put", bid=2.40, ask=2.50, quote_time=now, provenance=prov)


    from volagent.domain.forecasts import IVCrushForecast, MoveForecast
    move_fc = MoveForecast(
        median_abs_move_pct=0.08,  # > 4.0% implied move -> Long Straddle
        q20_abs_move_pct=0.04,
        q80_abs_move_pct=0.12,
        implied_move_pct=0.039,
        edge_pct_spot=0.041,
        probability_exceeds_implied=0.75,
        calibration_confidence=0.85,
    )
    iv_fc = IVCrushForecast(median_iv_change_points=-15.0, q20_iv_change_points=-20.0, q80_iv_change_points=-10.0, expected_post_event_atm_iv=0.45)

    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    implied_metrics = ImpliedMoveMetrics(
        atm_strike=125.0,
        implied_move_mid_dollars=4.90,
        implied_move_mid_pct=0.0392,
        implied_move_bid_dollars=4.80,
        implied_move_bid_pct=0.0384,
        implied_move_ask_dollars=5.00,
        implied_move_ask_pct=0.040,
        call_mid_iv=0.45,
        put_mid_iv=0.45,
        straddle_iv_avg=0.45,
    )


    state: VolAgentState = {
        "run_id": "run-m4-test",
        "symbol": "NVDA",
        "nav": 100_000.0,
        "event": ev,
        "underlying": underlying,
        "option_chain": [c_atm, p_atm],
        "feature_set": {"atm_call": c_atm, "atm_put": p_atm, "implied_metrics": implied_metrics},
        "move_forecast": move_fc,
        "iv_forecast": iv_fc,
        "critic_report": critic,
        "enable_risk_governor": True,
    }

    settings = VolAgentSettings()
    out = strategy_and_risk_node(state, settings)

    assert "decision_record" in out
    dec_rec: DecisionRecord = out["decision_record"]
    assert dec_rec.schema_version == "caisheng.decision.v1"
    assert dec_rec.selected_action in ["LONG_STRADDLE", "SHORT_IRON_BUTTERFLY", "NO_TRADE"]
    assert dec_rec.selected_action == "LONG_STRADDLE"
    assert dec_rec.status == "APPROVED"
    assert len(dec_rec.artifact_hash) == 64


def test_decision_record_hash_tamper_detection():
    """Criterion 8: Tampering with any DecisionRecord field invalidates the SHA-256 artifact_hash."""
    snap = SnapshotMetadata(symbol="AAPL", spot=220.0, underlying_quote_time="2026-08-28T14:30:00Z", option_snapshot_time="2026-08-28T14:30:00Z", event_id="evt-1", event_time="2026-08-28T20:00:00Z", event_source_url="https://ir.apple.com")
    vol = VolatilityView(implied_move_bid_pct=0.038, implied_move_ask_pct=0.041, expected_move_median_pct=0.048, q20_pct=0.02, q80_pct=0.08, expected_iv_crush_points=-15.0, forecast_confidence=0.85)
    from volagent.domain.decision_record import CriticSummary, RiskSummary

    rec = DecisionRecord.create_and_hash(
        decision_id="dec-1",
        run_id="run-1",
        status="APPROVED",
        generated_at="2026-08-28T14:30:00Z",
        snapshot=snap,
        volatility_view=vol,
        proposals=[],
        selected_action="LONG_STRADDLE",
        quantity=1,
        risk=RiskSummary(current_equity=100_000.0, reserved_risk_before=0.0, reserved_risk_after=400.0),
        critic=CriticSummary(),
    )

    original_hash = rec.artifact_hash
    # Recomputed hash matches
    assert rec.compute_hash() == original_hash

    # Tamper with quantity (change from 1 to 5)
    tampered_rec = DecisionRecord(
        schema_version=rec.schema_version,
        decision_id=rec.decision_id,
        run_id=rec.run_id,
        strategy_version=rec.strategy_version,
        mode=rec.mode,
        status=rec.status,
        generated_at=rec.generated_at,
        snapshot=rec.snapshot,
        volatility_view=rec.volatility_view,
        proposals=rec.proposals,
        selected_action=rec.selected_action,
        quantity=5,  # Tampered!
        risk=rec.risk,
        critic=rec.critic,
        artifact_hash=original_hash,  # Kept old hash
    )

    # Recomputed hash fails to match tampered artifact_hash
    assert tampered_rec.compute_hash() != tampered_rec.artifact_hash


def test_no_trade_abstention_emits_valid_decision_record_with_reasons():
    """Criterion 4 & 8: Abstention produces NO_TRADE DecisionRecord with exact reasons."""
    snap = SnapshotMetadata(symbol="TSLA", spot=200.0, underlying_quote_time="2026-08-28T14:30:00Z", option_snapshot_time="2026-08-28T14:30:00Z", event_id="evt-tsla", event_time="2026-08-28T20:00:00Z", event_source_url="https://ir.tesla.com")
    vol = VolatilityView(implied_move_bid_pct=0.06, implied_move_ask_pct=0.065, expected_move_median_pct=0.062, q20_pct=0.03, q80_pct=0.09, expected_iv_crush_points=-15.0, forecast_confidence=0.85)
    from volagent.domain.decision_record import CriticSummary, RiskSummary

    rec = DecisionRecord.create_and_hash(
        decision_id="dec-tsla-no-trade",
        run_id="run-tsla-1",
        status="NO_TRADE",
        generated_at="2026-08-28T14:30:00Z",
        snapshot=snap,
        volatility_view=vol,
        proposals=[],
        selected_action="NO_TRADE",
        quantity=0,
        risk=RiskSummary(current_equity=100_000.0, reserved_risk_before=0.0, reserved_risk_after=0.0, rejection_reasons=["Insufficient executable edge"]),
        critic=CriticSummary(),
    )

    assert rec.selected_action == "NO_TRADE"
    assert rec.status == "NO_TRADE"
    assert rec.quantity == 0
    assert "Insufficient executable edge" in rec.risk.rejection_reasons

