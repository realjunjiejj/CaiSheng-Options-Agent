"""Unit tests for agent citation integrity and directional compliance."""

from datetime import datetime, timezone
from volagent.agents.long_vol import run_long_vol_advocate
from volagent.agents.model_risk import validate_track_compliance
from volagent.domain.enums import DataMode
from volagent.domain.events import EvidenceItem
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.state import VolatilityThesis
from volagent.provenance import Provenance


def test_hallucinated_evidence_id_rejected():
    """Verify AG-05: Advocates strictly cite only provided evidence IDs and never invent IDs."""
    now = datetime.now(timezone.utc)
    prov = Provenance(source_name="t", source_uri="t", retrieved_at=now, observed_at=now, content_hash="h", data_mode=DataMode.REPLAY_SYNTHETIC)
    
    evidence = [
        EvidenceItem(
            evidence_id="NVDA-EV-01",
            category="guidance_uncertainty",
            claim="Guidance dispersion high",
            magnitude_relevance="High variance",
            numeric_value=0.8,
            units="index",
            confidence=0.9,
            provenance=prov,
        )
    ]

    fc = MoveForecast(
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

    iv_fc = IVCrushForecast(
        median_iv_change_points=-15.0,
        q20_iv_change_points=-22.0,
        q80_iv_change_points=-8.0,
        confidence=0.82,
    )

    thesis = run_long_vol_advocate("NVDA", fc, iv_fc, evidence)

    assert "EVID-DEFAULT" not in thesis.supporting_evidence_ids
    assert thesis.supporting_evidence_ids == ["NVDA-EV-01"]


def test_directional_leakage_audit_across_all_text():
    """Verify AG-17: Critic detects forbidden directional phrasing."""
    clean_thesis = VolatilityThesis(
        side="long_vol",
        directional_view="none",
        thesis="Volatility is underpriced, buy long straddle.",
        numeric_argument="Edge +0.88%",
        supporting_evidence_ids=["E1"],
        invalidation_conditions=[],
        confidence=0.8,
    )

    leaked_thesis = VolatilityThesis(
        side="long_vol",
        directional_view="none",
        thesis="Stock is extremely bullish, expect upside rally.",
        numeric_argument="Edge +0.88%",
        supporting_evidence_ids=["E1"],
        invalidation_conditions=[],
        confidence=0.8,
    )

    compliant, violations = validate_track_compliance(clean_thesis, clean_thesis)
    assert compliant is True
    assert len(violations) == 0

    non_compliant, violations_bad = validate_track_compliance(leaked_thesis, clean_thesis)
    assert non_compliant is False
    assert any("bullish" in v for v in violations_bad)
