"""Unit tests for agent citation integrity, mock LLM injection, and directional compliance."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from volagent.agents.event_magnitude import run_event_magnitude_agent
from volagent.agents.long_vol import run_long_vol_advocate, run_short_vol_advocate
from volagent.agents.model_risk import run_model_risk_critic, validate_track_compliance
from volagent.domain.enums import DataMode, EventTiming, GateStatus, OpportunityKind
from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.state import EventMagnitudeAssessment, VolatilityThesis
from volagent.provenance import Provenance


def test_llm_hallucinated_evidence_id_rejected():
    """P0-15 Fix: Injected LLM returning hallucinated ID is sanitized and hallucinated ID is stripped."""
    now = datetime.now(timezone.utc)
    prov = Provenance.from_synthetic("t")
    evidence = [
        EvidenceItem(
            evidence_id="EVID-VALID-01",
            source_type="sec_filing_10q",
            source_uri="file://test",
            observed_at=now,
            metric_name="jump",
            numeric_value=0.1,
            summary="Valid filing",
        )
    ]

    event = EarningsEvent(
        event_id="EV-1",
        symbol="NVDA",
        fiscal_quarter="Q2",
        event_time=now,
        timing=EventTiming.AFTER_MARKET_CLOSE,
        confirmed=True,
        decision_time=now,
        exit_time=now,
        provenance=prov,
    )

    # Mock LLM that hallucinates "HALLUCINATED-ID-999"
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = EventMagnitudeAssessment(
        directional_view="none",
        event_novelty_score=0.8,
        guidance_uncertainty_score=0.7,
        analyst_dispersion_score=0.6,
        magnitude_pressure_score=0.7,
        confidence=0.85,
        supporting_evidence_ids=["EVID-VALID-01", "HALLUCINATED-ID-999"],  # Injected hallucination
        summary="LLM Summary",
        missing_information=[],
    )
    mock_llm.with_structured_output.return_value = mock_structured

    res = run_event_magnitude_agent(event, evidence, llm_client=mock_llm)

    assert "HALLUCINATED-ID-999" not in res.supporting_evidence_ids
    assert res.supporting_evidence_ids == ["EVID-VALID-01"]


def test_directional_leakage_scans_every_text_field():
    """P1-20 Fix: Directional leakage scan checks numeric_argument and invalidation conditions."""
    thesis_with_leaked_num_arg = VolatilityThesis(
        side="long_vol",
        directional_view="none",
        thesis="Delta-neutral straddle structure",
        numeric_argument="The stock will go up strongly after earnings",  # Leaked directional claim
        supporting_evidence_ids=["E1"],
        invalidation_conditions=[],
        confidence=0.8,
    )

    compliant, violations = validate_track_compliance(thesis_with_leaked_num_arg, None)
    assert compliant is False
    assert any("Forbidden directional term detected" in v for v in violations)


def test_missing_advocate_or_critic_fails_closed():
    """P1-21 Fix: Missing advocate role causes critic to fail closed with force_no_trade."""
    now = datetime(2024, 8, 28, 20, 0, 0, tzinfo=timezone.utc)
    prov = Provenance.from_synthetic("t")
    underlying = UnderlyingSnapshot(symbol="NVDA", price=100.0, bid=99.9, ask=100.1, quote_time=now, previous_close=99.0, realized_vol_10d=0.5, realized_vol_30d=0.5, provenance=prov)
    event = EarningsEvent(event_id="EV1", symbol="NVDA", fiscal_quarter="Q2", event_time=now, timing=EventTiming.AFTER_MARKET_CLOSE, confirmed=True, decision_time=now, exit_time=now, provenance=prov)
    fc = MoveForecast(median_abs_move_pct=0.08, q20_abs_move_pct=0.05, q80_abs_move_pct=0.11, implied_move_pct=0.07, edge_pct_spot=0.01, probability_exceeds_implied=0.6, calibration_confidence=0.85, out_of_distribution=False)

    # Missing both long and short theses
    report = run_model_risk_critic(underlying, event, [], fc, long_thesis=None, short_thesis=None)
    assert report.status == GateStatus.FAIL
    assert report.recommendation == "force_no_trade"
    assert any("Missing required advocate thesis" in r for r in report.failure_reasons)


def test_daily_opportunity_quotes_are_bounded_by_decision_time_not_scan_start():
    """An ongoing daily opportunity may fetch quotes after scanning but never after decision."""
    scan_started_at = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    quote_time = scan_started_at + timedelta(seconds=3)
    decision_time = quote_time + timedelta(seconds=1)
    prov = Provenance.from_synthetic("daily-live")
    underlying = UnderlyingSnapshot(
        symbol="SPY",
        price=650.0,
        bid=649.99,
        ask=650.01,
        quote_time=quote_time,
        realized_vol_10d=0.12,
        realized_vol_30d=0.15,
        provenance=prov,
    )
    event = EarningsEvent(
        event_id="daily-vol-2026-08-31-SPY",
        symbol="SPY",
        event_type="scheduled_volatility",
        opportunity_kind=OpportunityKind.DAILY_VOLATILITY,
        event_time=scan_started_at,
        timing=EventTiming.DURING_MARKET_HOURS,
        confirmed=True,
        decision_time=decision_time,
        exit_time=decision_time + timedelta(days=1),
        provenance=prov,
    )
    option = OptionContractSnapshot(
        symbol="SPY260911C00650000",
        underlying_symbol="SPY",
        option_type="call",
        strike=650.0,
        expiration=date(2026, 9, 11),
        bid=5.0,
        ask=5.1,
        quote_time=quote_time,
        volume=500,
        open_interest=1_000,
        provenance=prov,
    )
    forecast = MoveForecast(
        median_abs_move_pct=0.02,
        q20_abs_move_pct=0.01,
        q80_abs_move_pct=0.03,
        implied_move_pct=0.02,
        edge_pct_spot=0.0,
        probability_exceeds_implied=0.5,
        calibration_confidence=0.7,
        out_of_distribution=False,
    )

    report = run_model_risk_critic(
        underlying,
        event,
        [option, option],
        forecast,
        require_advocates=False,
    )

    assert report.temporal_leakage_detected is False
    assert not any("Temporal leakage" in reason for reason in report.failure_reasons)


def test_high_confidence_thesis_conflict_sets_disagreement():
    """P1-22 Fix: When both advocates claim >= 80% confidence on opposite theses, disagreement is flagged."""
    now = datetime(2024, 8, 28, 20, 0, 0, tzinfo=timezone.utc)
    prov = Provenance.from_synthetic("t")
    underlying = UnderlyingSnapshot(symbol="NVDA", price=100.0, bid=99.9, ask=100.1, quote_time=now, previous_close=99.0, realized_vol_10d=0.5, realized_vol_30d=0.5, provenance=prov)
    event = EarningsEvent(event_id="EV1", symbol="NVDA", fiscal_quarter="Q2", event_time=now, timing=EventTiming.AFTER_MARKET_CLOSE, confirmed=True, decision_time=now, exit_time=now, provenance=prov)
    opt = OptionContractSnapshot(symbol="C100", underlying_symbol="NVDA", option_type="call", strike=100.0, expiration=date(2024, 9, 6), bid=3.0, ask=3.2, bid_size=10, ask_size=10, quote_time=now, provenance=prov)
    fc = MoveForecast(median_abs_move_pct=0.08, q20_abs_move_pct=0.05, q80_abs_move_pct=0.11, implied_move_pct=0.07, edge_pct_spot=0.01, probability_exceeds_implied=0.6, calibration_confidence=0.85, out_of_distribution=False)

    long_th = VolatilityThesis(side="long_vol", directional_view="none", thesis="Long vol edge", numeric_argument="Edge +1%", supporting_evidence_ids=[], invalidation_conditions=[], confidence=0.85)
    short_th = VolatilityThesis(side="short_vol", directional_view="none", thesis="Short vol edge", numeric_argument="Edge +1%", supporting_evidence_ids=[], invalidation_conditions=[], confidence=0.85)

    report = run_model_risk_critic(underlying, event, [opt, opt], fc, long_thesis=long_th, short_thesis=short_th)
    assert report.excessive_model_disagreement is True
