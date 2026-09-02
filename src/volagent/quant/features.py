"""Quantitative feature construction with strict point-in-time provenance."""

import math
from typing import Any
import numpy as np

from volagent.domain.events import EarningsEvent, EvidenceItem
from volagent.domain.market import OptionContractSnapshot, UnderlyingSnapshot
from volagent.domain.state import EventMagnitudeAssessment
from volagent.quant.expected_move import ImpliedMoveMetrics


def build_quantitative_features(
    underlying: UnderlyingSnapshot,
    implied_metrics: ImpliedMoveMetrics,
    surface_quality: float,
    event: EarningsEvent,
    historical_event_moves: list[float] | None = None,
    event_assessment: EventMagnitudeAssessment | None = None,
) -> dict[str, Any]:
    """Construct deterministic quantitative feature vector.
    
    Includes missingness flags and bounded metrics.
    """
    hist_moves = [float(move) for move in (historical_event_moves or []) if math.isfinite(float(move)) and float(move) >= 0.0]
    hist_median = float(np.median(hist_moves)) if hist_moves else None
    hist_std = float(np.std(hist_moves)) if hist_moves else None

    # Realized vol difference
    rv30 = underlying.realized_vol_30d
    iv = implied_metrics.atm_iv
    iv_minus_recent_rv = iv - rv30 if rv30 is not None else None

    features: dict[str, Any] = {
        "symbol": underlying.symbol,
        "spot_price": underlying.price,
        "implied_move_pct": implied_metrics.implied_move_mid_pct,
        "implied_move_long_entry_pct": implied_metrics.implied_move_long_entry_pct,
        "implied_move_short_entry_pct": implied_metrics.implied_move_short_entry_pct,
        "atm_iv": implied_metrics.atm_iv,
        "realized_vol_10d": underlying.realized_vol_10d,
        "realized_vol_30d": underlying.realized_vol_30d,
        "iv_minus_recent_rv": iv_minus_recent_rv,
        "ratio_implied_to_hist_median": (
            implied_metrics.implied_move_mid_pct / max(1e-4, hist_median)
            if hist_median is not None else None
        ),
        "historical_move_median": hist_median,
        "historical_move_dispersion": hist_std,
        "historical_move_count": len(hist_moves),
        "has_historical_event_moves": bool(hist_moves),
        "surface_quality_score": surface_quality,
        "opportunity_kind": event.opportunity_kind.value,
        "forecast_horizon_days": max(
            1,
            (event.exit_time.date() - event.decision_time.date()).days,
        ),
        "has_rv10": underlying.realized_vol_10d is not None,
        "has_rv30": underlying.realized_vol_30d is not None,
    }

    if event_assessment is not None:
        features.update({
            "event_novelty_score": max(0.0, min(1.0, event_assessment.event_novelty_score)),
            "guidance_uncertainty_score": max(0.0, min(1.0, event_assessment.guidance_uncertainty_score)),
            "analyst_dispersion_score": max(0.0, min(1.0, event_assessment.analyst_dispersion_score)),
            "magnitude_pressure_score": max(0.0, min(1.0, event_assessment.magnitude_pressure_score)),
            "llm_confidence": max(0.0, min(1.0, event_assessment.confidence)),
            "has_event_assessment": True,
        })
    else:
        features.update({
            "event_novelty_score": 0.5,
            "guidance_uncertainty_score": 0.5,
            "analyst_dispersion_score": 0.5,
            "magnitude_pressure_score": 0.5,
            "llm_confidence": 0.5,
            "has_event_assessment": False,
        })

    return features
