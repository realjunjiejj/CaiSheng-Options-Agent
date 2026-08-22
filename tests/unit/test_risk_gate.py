"""Unit tests for deterministic risk gate."""

from datetime import date, datetime, timezone
import pytest
from volagent.config import RiskConfig
from volagent.domain.enums import DataMode, Decision, EventTiming, GateStatus
from volagent.domain.events import EarningsEvent
from volagent.domain.forecasts import MoveForecast
from volagent.domain.state import CriticReport
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.provenance import Provenance
from volagent.quant.risk_gate import evaluate_risk_gate


def create_dummy_provenance():
    return Provenance(
        source_name="test",
        source_uri="test",
        retrieved_at=datetime.now(timezone.utc),
        observed_at=datetime.now(timezone.utc),
        content_hash="test",
        data_mode=DataMode.REPLAY_SYNTHETIC,
    )


def test_risk_gate_max_loss_rejection():
    risk_cfg = RiskConfig(hard_max_risk_nav_pct=0.01)  # 1% of NAV
    nav = 100_000.0  # Max loss limit = $1,000

    exp = date(2024, 9, 6)
    legs = [
        OptionLeg(contract_symbol="C1", option_type="call", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=0.5, gamma=0.04, theta=-0.1, vega=0.2),
        OptionLeg(contract_symbol="P1", option_type="put", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=-0.5, gamma=0.04, theta=-0.1, vega=0.2),
    ]

    candidate = StrategyCandidate(
        strategy_id="test-strat",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=5,
        entry_debit_credit=1500.0,
        max_profit=None,
        max_loss=1500.0,  # Exceeds $1,000 limit!
        break_evens=[90.0, 110.0],
        expected_pnl=200.0,
        expected_shortfall_95=1200.0,
        net_delta=10.0,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        stress_losses={"P_000_IV_000": 1500.0},
        liquidity_score=0.90,
    )

    event = EarningsEvent(
        event_id="test-event",
        symbol="NVDA",
        fiscal_period="Q2 2024",
        event_time=datetime(2024, 8, 28, 20, 0, 0, tzinfo=timezone.utc),
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=datetime(2024, 8, 28, 19, 45, 0, tzinfo=timezone.utc),
        exit_time=datetime(2024, 8, 29, 14, 0, 0, tzinfo=timezone.utc),
        provenance=create_dummy_provenance(),
    )

    forecast = MoveForecast(
        median_abs_move_pct=0.085,
        q20_abs_move_pct=0.065,
        q80_abs_move_pct=0.110,
        implied_move_pct=0.075,
        edge_pct_spot=0.010,
        uncertainty_buffer_pct_spot=0.0025,
        probability_exceeds_implied=0.65,
        calibration_confidence=0.85,
        out_of_distribution=False,
    )

    critic = CriticReport(
        status=GateStatus.PASS,
        directional_leakage_detected=False,
        temporal_leakage_detected=False,
        stale_data_detected=False,
        excessive_model_disagreement=False,
        recommendation="continue",
    )

    report = evaluate_risk_gate(
        candidate=candidate,
        decision=Decision.LONG_STRADDLE,
        nav=nav,
        event=event,
        move_forecast=forecast,
        critic_report=critic,
        risk_config=risk_cfg,
    )

    assert report.overall_status == GateStatus.FAIL
    assert report.approved_quantity == 0
    assert any("hard_max_loss" in r for r in report.rejection_reasons)
