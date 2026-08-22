"""Forecast domain models for absolute movement and post-event IV change."""

from pydantic import BaseModel, ConfigDict, Field


class MoveForecast(BaseModel):
    """Unsigned event move forecast quantiles and exceedance probability."""
    model_config = ConfigDict(extra="ignore")

    median_abs_move_pct: float
    q20_abs_move_pct: float
    q80_abs_move_pct: float
    probability_exceeds_implied: float
    implied_move_pct: float
    edge_pct_spot: float
    uncertainty_buffer_pct_spot: float = 0.0025
    calibration_confidence: float = 0.85
    out_of_distribution: bool = False
    model_version: str = "v1.0"
    feature_snapshot_hash: str = "default_hash"


class IVCrushForecast(BaseModel):
    """Post-event implied volatility change forecast in percentage points."""
    model_config = ConfigDict(extra="ignore")

    median_iv_change_points: float
    q20_iv_change_points: float
    q80_iv_change_points: float
    model_version: str = "v1.0"
    calibration_confidence: float = 0.82
    confidence: float | None = None
