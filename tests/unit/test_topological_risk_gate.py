"""Unit tests for the 20-point deterministic quantitative risk gate and adversarial probes."""

from datetime import date, datetime, timezone
import pytest
from volagent.config import RiskConfig
from volagent.domain.enums import AbstentionReason, DataMode, Decision, EventTiming, GateStatus
from volagent.domain.events import EarningsEvent
from volagent.domain.forecasts import MoveForecast
from volagent.domain.state import CriticReport
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.provenance import Provenance
from volagent.quant.risk_gate import evaluate_risk_gate


def create_test_candidate(max_loss: float, net_delta: float = 10.0, worst_stress: float = 800.0) -> StrategyCandidate:
    exp = date(2024, 9, 6)
    legs = [
        OptionLeg(contract_symbol="C1", option_type="call", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=max_loss/200.0, delta=0.5, gamma=0.04, theta=-0.1, vega=0.2),
        OptionLeg(contract_symbol="P1", option_type="put", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=max_loss/200.0, delta=-0.5, gamma=0.04, theta=-0.1, vega=0.2),
    ]
    return StrategyCandidate(
        strategy_id="strat-1",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=1,
        entry_debit_credit=max_loss,
        net_delta=net_delta,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        max_loss=max_loss,
        stress_losses={"P_000_IV_000": worst_stress},
        liquidity_score=0.90,
    )


def create_test_event() -> EarningsEvent:
    now = datetime(2024, 8, 28, 20, 0, 0, tzinfo=timezone.utc)
    prov = Provenance(source_name="t", source_uri="t", retrieved_at=now, observed_at=now, content_hash="h", data_mode=DataMode.REPLAY_SYNTHETIC)
    return EarningsEvent(
        event_id="E1",
        symbol="NVDA",
        fiscal_quarter="Q2",
        event_time=now,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=now,
        exit_time=now,
        provenance=prov,
    )


def create_test_forecast() -> MoveForecast:
    return MoveForecast(
        median_abs_move_pct=0.087,
        q20_abs_move_pct=0.065,
        q80_abs_move_pct=0.112,
        implied_move_pct=0.078,
        edge_pct_spot=0.009,
        uncertainty_buffer_pct_spot=0.0025,
        probability_exceeds_implied=0.58,
        calibration_confidence=0.85,
        out_of_distribution=False,
    )


def test_stress_cap_defaults_to_one_percent_not_fifty():
    """Verify VP-01: Stress cap is strictly 1.0% NAV ($1,001 fails, $1,000 passes on $100k NAV)."""
    nav = 100_000.0
    risk_cfg = RiskConfig(max_stress_loss_nav_pct=0.01)
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    # 1. Stress loss $1,000 (Exactly 1.0% NAV) -> PASS
    cand_pass = create_test_candidate(max_loss=800.0, worst_stress=1000.0)
    rep_pass = evaluate_risk_gate(cand_pass, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg)
    assert rep_pass.overall_status == GateStatus.PASS

    # 2. Stress loss $1,001 (1.001% NAV) -> FAIL
    cand_fail = create_test_candidate(max_loss=800.0, worst_stress=1001.0)
    rep_fail = evaluate_risk_gate(cand_fail, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg)
    assert rep_fail.overall_status == GateStatus.FAIL
    assert any("worst_stress_loss" in r for r in rep_fail.rejection_reasons)


def test_all_twenty_risk_checks_executed():
    """Verify that all 20 enumerated checks are evaluated on an approved candidate."""
    nav = 100_000.0
    risk_cfg = RiskConfig()
    cand = create_test_candidate(max_loss=800.0)
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    report = evaluate_risk_gate(cand, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg)
    assert len(report.checks) == 20
    assert report.overall_status == GateStatus.PASS
    assert report.approved_quantity == 1


def test_missing_critic_fails_closed():
    """Verify that missing critic report (None) causes risk gate to FAIL closed."""
    nav = 100_000.0
    risk_cfg = RiskConfig()
    cand = create_test_candidate(max_loss=800.0)
    event = create_test_event()
    fc = create_test_forecast()

    report = evaluate_risk_gate(cand, Decision.LONG_STRADDLE, nav, event, fc, None, risk_cfg)
    assert report.overall_status == GateStatus.FAIL
    assert report.approved_quantity == 0
    assert any("critic_approval" in r for r in report.rejection_reasons)


def test_risk_gate_recomputes_loss_from_approved_legs():
    """P0-02 Fix: Risk gate must recompute max loss from immutable legs, not trust claimed candidate.max_loss."""
    nav = 100_000.0
    risk_cfg = RiskConfig(hard_max_risk_nav_pct=0.01)  # $1,000 cap
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    # Legs imply $1,200 loss ($6 call + $6 put * 100), but candidate forged max_loss to $1.00
    exp = date(2024, 9, 6)
    forged_cand = StrategyCandidate(
        strategy_id="strat-forged",
        decision=Decision.LONG_STRADDLE,
        legs=[
            OptionLeg(contract_symbol="C1", option_type="call", strike=100.0, expiration=exp, side="buy", ratio_qty=1, entry_price_assumption=6.0),
            OptionLeg(contract_symbol="P1", option_type="put", strike=100.0, expiration=exp, side="buy", ratio_qty=1, entry_price_assumption=6.0),
        ],
        quantity=1,
        entry_debit_credit=1.0,  # Forged
        max_loss=1.0,  # Forged to bypass gate
        stress_losses={"P_000_IV_000": 800.0},
    )

    report = evaluate_risk_gate(forged_cand, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg)
    # Must fail because recomputed loss is $1,200 > $1,000 limit
    assert report.overall_status == GateStatus.FAIL
    assert any("hard_max_loss" in r for r in report.rejection_reasons)


def test_dollar_delta_multiplies_share_delta_by_spot():
    """P0-04 Fix: Dollar delta must multiply share delta by spot price."""
    nav = 100_000.0
    spot = 100.0
    risk_cfg = RiskConfig(max_abs_dollar_delta_nav_pct=0.02)  # $2,000 max dollar delta (2.0% NAV)
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    # Net delta = 50 shares. At $100 spot, dollar delta = $5,000 (5.0% NAV > 2.0% NAV) -> FAIL
    cand = create_test_candidate(max_loss=800.0, net_delta=50.0)
    report = evaluate_risk_gate(cand, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg, spot_price=spot)
    assert report.overall_status == GateStatus.FAIL
    assert any("delta_neutrality" in r for r in report.rejection_reasons)


def test_risk_gate_rejects_mixed_expiration_straddle():
    """P0-06 Fix: Straddle with legs expiring on different dates must be rejected."""
    nav = 100_000.0
    risk_cfg = RiskConfig()
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")

    mixed_cand = StrategyCandidate(
        strategy_id="strat-mixed-exp",
        decision=Decision.LONG_STRADDLE,
        legs=[
            OptionLeg(contract_symbol="C1", option_type="call", strike=100.0, expiration=date(2024, 9, 6), side="buy", ratio_qty=1, entry_price_assumption=3.5),
            OptionLeg(contract_symbol="P1", option_type="put", strike=100.0, expiration=date(2024, 9, 13), side="buy", ratio_qty=1, entry_price_assumption=3.5),
        ],
        quantity=1,
        entry_debit_credit=700.0,
        max_loss=700.0,
    )

    report = evaluate_risk_gate(mixed_cand, Decision.LONG_STRADDLE, nav, event, fc, critic, risk_cfg)
    assert report.overall_status == GateStatus.FAIL
    assert any("common_expiration" in r for r in report.rejection_reasons)


def test_risk_gate_rejects_inverted_butterfly_at_final_boundary():
    """P0-05 Fix: Inverted wing strikes in Iron Butterfly must be rejected by risk gate."""
    nav = 100_000.0
    risk_cfg = RiskConfig()
    event = create_test_event()
    fc = create_test_forecast()
    critic = CriticReport(status=GateStatus.PASS, directional_leakage_detected=False, temporal_leakage_detected=False, stale_data_detected=False, excessive_model_disagreement=False, recommendation="continue")
    exp = date(2024, 9, 6)

    # Inverted topology: Long Put strike (105) > Short Put strike (100)
    inverted_cand = StrategyCandidate(
        strategy_id="strat-inverted-ibfly",
        decision=Decision.SHORT_IRON_BUTTERFLY,
        legs=[
            OptionLeg(contract_symbol="P105", option_type="put", strike=105.0, expiration=exp, side="buy", ratio_qty=1, entry_price_assumption=1.0),
            OptionLeg(contract_symbol="P100", option_type="put", strike=100.0, expiration=exp, side="sell", ratio_qty=1, entry_price_assumption=3.0),
            OptionLeg(contract_symbol="C100", option_type="call", strike=100.0, expiration=exp, side="sell", ratio_qty=1, entry_price_assumption=3.0),
            OptionLeg(contract_symbol="C110", option_type="call", strike=110.0, expiration=exp, side="buy", ratio_qty=1, entry_price_assumption=1.0),
        ],
        quantity=1,
        entry_debit_credit=-400.0,
        max_loss=600.0,
    )

    report = evaluate_risk_gate(inverted_cand, Decision.SHORT_IRON_BUTTERFLY, nav, event, fc, critic, risk_cfg)
    assert report.overall_status == GateStatus.FAIL
    assert any("defined_risk_topology" in r for r in report.rejection_reasons)
