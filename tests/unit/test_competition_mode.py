"""Competition-mode acceptance tests: arming, opportunity generation, and economic gates."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from volagent.competition import (
    competition_submission_permitted,
    issue_competition_lease,
    read_competition_status,
    revoke_competition_lease,
)
from volagent.config import load_config
from volagent.domain.enums import Decision, OpportunityKind
from volagent.domain.forecasts import MoveForecast
from volagent.domain.strategies import StrategyCandidate
from volagent.lifecycle.scanner import EventScanner
from volagent.quant.expected_move import ImpliedMoveMetrics
from volagent.quant.forecast import compute_implied_residual_forecast
from volagent.quant.strategy_selector import select_best_strategy


NY_TZ = ZoneInfo("America/New_York")


def test_competition_configuration_is_small_risk_live_paper_only(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "false")
    settings = load_config("config/competition.yaml")

    assert settings.volagent_data_mode == "live"
    assert settings.execution.paper_only is True
    assert settings.execution.allow_order_submission is True
    assert settings.execution.require_human_approval is False
    assert settings.risk.recommended_risk_nav_pct == pytest.approx(0.0025)
    assert settings.risk.hard_max_risk_nav_pct == pytest.approx(0.005)
    assert settings.mandate.max_open_strategies == 2
    assert settings.mandate.max_new_entries_per_day == 1
    assert settings.mandate.daily_loss_halt_dollars == pytest.approx(500.0)
    assert settings.competition.enabled is True
    assert settings.competition.lease_required is True
    assert settings.forecast.model_mode == "implied_residual"
    assert settings.forecast.require_confidence_bound_edge is True


def test_process_kill_switch_overrides_competition_yaml(monkeypatch):
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "false")
    settings = load_config("config/competition.yaml")

    assert settings.execution.allow_order_submission is False
    assert competition_submission_permitted(
        settings=settings,
        status={"submission_authorized": True},
        is_live_mode=True,
    ) is False


def test_competition_lease_is_account_bound_config_bound_expiring_and_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "false")
    settings = load_config("config/competition.yaml")
    lease_path = tmp_path / "competition-arm.json"
    now = datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)

    issued = issue_competition_lease(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        starting_nav=100_000.0,
        current_equity=100_125.0,
        now=now,
        duration=timedelta(hours=8),
    )

    assert issued["status"] == "ARMED"
    assert "paper-account-secret-id" not in str(issued)
    assert "paper-secret" not in lease_path.read_text()
    assert oct(lease_path.stat().st_mode & 0o777) == "0o600"
    assert len(issued["lease_hash"]) == 64

    active = read_competition_status(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        now=now + timedelta(hours=1),
    )
    assert active["status"] == "ARMED"
    assert active["submission_authorized"] is True

    wrong_account = read_competition_status(
        path=lease_path,
        settings=settings,
        paper_account_id="different-paper-account",
        now=now + timedelta(hours=1),
    )
    assert wrong_account["status"] == "BLOCKED"
    assert wrong_account["submission_authorized"] is False

    expired = read_competition_status(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        now=now + timedelta(hours=9),
    )
    assert expired["status"] == "EXPIRED"
    assert expired["submission_authorized"] is False

    assert competition_submission_permitted(
        settings=settings, status=active, is_live_mode=True
    ) is True
    assert competition_submission_permitted(
        settings=settings, status=expired, is_live_mode=True
    ) is False

    tampered_payload = json.loads(lease_path.read_text())
    tampered_payload["risk_limits"]["hard_loss_per_trade"] = 50_000.0
    lease_path.write_text(json.dumps(tampered_payload))
    tampered = read_competition_status(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        now=now + timedelta(hours=1),
    )
    assert tampered["status"] == "BLOCKED"
    assert tampered["submission_authorized"] is False


def test_operator_can_revoke_active_lease_without_disabling_position_monitoring(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret")
    monkeypatch.setenv("VOLAGENT_ALLOW_ORDER_SUBMISSION", "true")
    monkeypatch.setenv("VOLAGENT_REQUIRE_HUMAN_APPROVAL", "false")
    settings = load_config("config/competition.yaml")
    lease_path = tmp_path / "competition-arm.json"
    now = datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)

    issue_competition_lease(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        starting_nav=100_000.0,
        current_equity=100_125.0,
        now=now,
        duration=timedelta(hours=8),
    )
    revoked = revoke_competition_lease(
        path=lease_path,
        settings=settings,
        now=now + timedelta(minutes=5),
    )

    assert revoked["status"] == "DISARMED"
    assert revoked["submission_authorized"] is False
    assert "Operator revoked" in revoked["reason"]
    assert "paper-account-secret-id" not in lease_path.read_text()
    assert "paper-secret" not in lease_path.read_text()
    assert oct(lease_path.stat().st_mode & 0o777) == "0o600"

    status = read_competition_status(
        path=lease_path,
        settings=settings,
        paper_account_id="paper-account-secret-id",
        now=now + timedelta(minutes=6),
    )
    assert status["status"] == "DISARMED"
    assert status["submission_authorized"] is False
    assert competition_submission_permitted(
        settings=settings,
        status=status,
        is_live_mode=True,
    ) is False


def test_daily_volatility_scanner_emits_stable_liquid_etf_opportunities():
    scanner = EventScanner(daily_volatility_symbols=["SPY", "QQQ", "IWM"])
    scan_time = datetime(2026, 8, 31, 10, 20, tzinfo=NY_TZ)

    opportunities = scanner.scan_daily_volatility_opportunities(scan_time)

    assert [event.symbol for event in opportunities] == ["SPY", "QQQ", "IWM"]
    assert all(event.opportunity_kind == OpportunityKind.DAILY_VOLATILITY for event in opportunities)
    assert all(event.event_type == "scheduled_volatility" for event in opportunities)
    assert all(event.timing.value == "dmh" for event in opportunities)
    assert all(event.confirmed for event in opportunities)
    assert all(event.decision_time == scan_time for event in opportunities)
    assert all(event.exit_time > event.decision_time for event in opportunities)
    assert len({event.event_id for event in opportunities}) == 3

    too_early = datetime(2026, 8, 31, 9, 55, tzinfo=NY_TZ)
    assert scanner.scan_daily_volatility_opportunities(too_early) == []


def test_implied_residual_forecast_is_anchored_and_shrinks_the_rv_signal():
    features = {
        "implied_move_pct": 0.060,
        "atm_iv": 0.32,
        "realized_vol_10d": 0.16,
        "realized_vol_30d": 0.18,
        "forecast_horizon_days": 7,
        "surface_quality_score": 0.90,
        "opportunity_kind": "daily_volatility",
    }

    forecast, iv_forecast = compute_implied_residual_forecast(features)
    raw_rv_move = 0.17 * (7 / 252) ** 0.5

    assert raw_rv_move < forecast.median_abs_move_pct < features["implied_move_pct"]
    assert forecast.q20_abs_move_pct < forecast.median_abs_move_pct < forecast.q80_abs_move_pct
    assert forecast.model_version.startswith("v3.0.0-implied-residual")
    assert forecast.out_of_distribution is False
    assert -5.0 <= iv_forecast.median_iv_change_points <= 5.0


def test_implied_residual_forecast_defers_to_market_without_valid_signal():
    features = {
        "implied_move_pct": 0.055,
        "atm_iv": 0.40,
        "surface_quality_score": 0.90,
        "opportunity_kind": "earnings",
    }

    forecast, _ = compute_implied_residual_forecast(features)

    assert forecast.median_abs_move_pct == pytest.approx(0.055)
    assert forecast.edge_pct_spot == pytest.approx(0.0)
    assert forecast.out_of_distribution is True


def test_implied_residual_forecast_only_corrects_with_explicit_point_in_time_residuals():
    features = {
        "implied_move_pct": 0.050,
        "atm_iv": 0.38,
        "surface_quality_score": 0.90,
        "opportunity_kind": "earnings_event",
    }

    forecast, _ = compute_implied_residual_forecast(
        features,
        historical_residuals=[0.010] * 12,
        residual_shrinkage_weight=0.35,
    )

    assert 0.050 < forecast.median_abs_move_pct < 0.060
    assert forecast.out_of_distribution is False


def _implied_metrics() -> ImpliedMoveMetrics:
    return ImpliedMoveMetrics(
        atm_strike=100.0,
        implied_move_ask_dollars=5.2,
        implied_move_mid_dollars=5.0,
        implied_move_bid_dollars=4.8,
        implied_move_ask_pct=0.052,
        implied_move_mid_pct=0.050,
        implied_move_bid_pct=0.048,
        call_mid_iv=0.40,
        put_mid_iv=0.40,
        straddle_iv_avg=0.40,
    )


def _candidate(expected_pnl: float, max_loss: float = 400.0) -> StrategyCandidate:
    return StrategyCandidate(
        strategy_id="economic-candidate",
        decision=Decision.LONG_STRADDLE,
        legs=[],
        quantity=1,
        entry_debit_credit=400.0,
        max_loss=max_loss,
        expected_pnl=expected_pnl,
        expected_shortfall_95=120.0,
        risk_adjusted_score=expected_pnl - 2.4,
    )


def test_competition_selector_requires_confidence_bound_and_positive_ev_per_risk():
    forecast = MoveForecast(
        median_abs_move_pct=0.070,
        q20_abs_move_pct=0.060,
        q80_abs_move_pct=0.090,
        probability_exceeds_implied=0.70,
        implied_move_pct=0.050,
        edge_pct_spot=0.020,
        calibration_confidence=0.75,
        out_of_distribution=False,
    )

    selected, decision, _, _ = select_best_strategy(
        [_candidate(expected_pnl=20.0)],
        forecast,
        _implied_metrics(),
        require_confidence_bound_edge=True,
        minimum_ev_to_max_loss=0.02,
    )
    assert selected is not None
    assert decision == Decision.LONG_STRADDLE

    selected, decision, _, reasons = select_best_strategy(
        [_candidate(expected_pnl=2.0)],
        forecast,
        _implied_metrics(),
        require_confidence_bound_edge=True,
        minimum_ev_to_max_loss=0.02,
    )
    assert selected is None
    assert decision == Decision.NO_TRADE
    assert any("EV/max-loss" in reason for reason in reasons)

    uncertain = forecast.model_copy(update={"q20_abs_move_pct": 0.050})
    selected, decision, _, reasons = select_best_strategy(
        [_candidate(expected_pnl=20.0)],
        uncertain,
        _implied_metrics(),
        require_confidence_bound_edge=True,
        minimum_ev_to_max_loss=0.02,
    )
    assert selected is None
    assert decision == Decision.NO_TRADE
    assert any("confidence-bound" in reason for reason in reasons)
