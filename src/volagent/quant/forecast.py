"""Forecast engine using deterministic historical shrinkage and IV crush calibration.

Academic Foundations:
- James, W., & Stein, C. (1961). "Estimation with Quadratic Loss." Proc. 4th Berkeley Symp., 361-379.
- Efron, B. (2012). "Large-Scale Inference: Empirical Bayes Methods." Cambridge University Press.
- Patell, J. M., & Wolfson, M. A. (1981). "The Ex-Ante Information Content of Accounting Earnings Announcements." J. Account. Res., 19(2), 661-687.
"""

import math
from typing import Any
import numpy as np

from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.provenance import compute_canonical_hash


def compute_implied_residual_forecast(
    features: dict[str, Any],
    historical_residuals: list[float] | None = None,
    residual_shrinkage_weight: float = 0.35,
    model_version: str = "v3.0.0-implied-residual",
) -> tuple[MoveForecast, IVCrushForecast]:
    """Anchor to executable implied move and apply only a strongly shrunk correction.

    A valid correction must be supported either by point-in-time historical residuals
    or, for daily-volatility opportunities, by trailing realized volatility.  Missing
    evidence leaves the market estimate unchanged and marks the forecast OOD.
    """
    implied_move = float(features["implied_move_pct"])
    atm_iv = float(features.get("atm_iv", 0.0))
    quality = float(features.get("surface_quality_score", 0.0))
    opportunity_kind = str(features.get("opportunity_kind", "earnings"))
    weight = max(0.0, min(1.0, float(residual_shrinkage_weight)))
    finite_residuals = [
        float(value)
        for value in (historical_residuals or [])
        if math.isfinite(float(value))
    ]

    signal: float | None = None
    effective_weight = 0.0
    if finite_residuals:
        sample_shrinkage = len(finite_residuals) / (len(finite_residuals) + 8.0)
        signal = float(np.median(finite_residuals))
        effective_weight = weight * sample_shrinkage
    elif opportunity_kind in {"daily_volatility", "OpportunityKind.DAILY_VOLATILITY"}:
        realized = [
            float(features[key])
            for key in ("realized_vol_10d", "realized_vol_30d")
            if key in features and math.isfinite(float(features[key])) and float(features[key]) >= 0.0
        ]
        horizon = max(1.0, float(features.get("forecast_horizon_days", 1.0)))
        if realized:
            realized_move = float(np.mean(realized)) * math.sqrt(horizon / 252.0)
            signal = realized_move - implied_move
            effective_weight = weight

    correction = effective_weight * signal if signal is not None else 0.0
    median = max(0.001, implied_move + correction)
    uncertainty = max(0.0025, abs(correction) * 1.5, implied_move * 0.12)
    q20 = max(0.001, median - uncertainty)
    q80 = median + uncertainty
    in_distribution = signal is not None and quality >= 0.70
    probability_exceeds = 0.5 + max(-0.35, min(0.35, correction / max(implied_move, 1e-6)))

    move_forecast = MoveForecast(
        median_abs_move_pct=median,
        q20_abs_move_pct=q20,
        q80_abs_move_pct=q80,
        probability_exceeds_implied=max(0.01, min(0.99, probability_exceeds)),
        implied_move_pct=implied_move,
        edge_pct_spot=median - implied_move,
        uncertainty_buffer_pct_spot=0.0025,
        calibration_confidence=0.70 if in_distribution else 0.50,
        out_of_distribution=not in_distribution,
        model_version=model_version,
        feature_snapshot_hash=compute_canonical_hash(features),
    )

    # Daily mode estimates bounded near-term IV mean reversion; event mode retains
    # the established earnings-crush prior until a calibrated IV history is supplied.
    if opportunity_kind in {"daily_volatility", "OpportunityKind.DAILY_VOLATILITY"}:
        iv_change = max(-5.0, min(5.0, correction * 100.0))
    else:
        iv_change = -(atm_iv * 0.55 * 100.0)
    iv_forecast = IVCrushForecast(
        median_iv_change_points=iv_change,
        q20_iv_change_points=iv_change - 2.0,
        q80_iv_change_points=iv_change + 2.0,
        model_version=model_version,
        calibration_confidence=0.70 if in_distribution else 0.50,
    )
    return move_forecast, iv_forecast


def compute_shrinkage_forecast(
    features: dict[str, Any],
    historical_ticker_moves: list[float] | None = None,
    sector_median_move: float = 0.065,
    global_median_move: float = 0.070,
    vrp_discount_ratio: float = 0.85,
    model_version: str = "v2.0.0-hybrid-vrp",
) -> tuple[MoveForecast, IVCrushForecast]:
    r"""Compute deterministic hybrid VRP shrinkage move forecast and heavy-tailed IV crush distribution.
    
    Academic Foundations:
    - James, W., & Stein, C. (1961). "Estimation with Quadratic Loss." Proc. 4th Berkeley Symp., 361-379.
    - Carr, P., & Wu, L. (2009). "Variance Risk Premiums." Rev. Financ. Stud., 22(3), 1311-1341.
    - Efron, B. (2012). "Large-Scale Inference: Empirical Bayes Methods." Cambridge University Press.
    """
    ticker_moves = [float(move) for move in (historical_ticker_moves or []) if math.isfinite(float(move)) and float(move) >= 0.0]
    n_ticker = len(ticker_moves)
    implied_move_pct = float(features["implied_move_pct"])

    # 1. Forward-looking market expectation adjusted by Variance Risk Premium
    market_adjusted_move = implied_move_pct * vrp_discount_ratio

    # 2. Empirical Bayes Weights Scaling
    if n_ticker >= 6:
        w_t, w_mkt, w_sec = 0.50, 0.35, 0.15
    elif n_ticker >= 3:
        w_t, w_mkt, w_sec = 0.35, 0.45, 0.20
    elif n_ticker > 0:
        w_t, w_mkt, w_sec = 0.15, 0.60, 0.25
    else:
        # A declared cross-sectional prior is not ticker history. The result
        # remains OOD and cannot pass the risk governor.
        w_t, w_mkt, w_sec = 0.00, 0.60, 0.40

    m_ticker = float(np.median(ticker_moves)) if ticker_moves else global_median_move
    shrunk_base = w_t * m_ticker + w_mkt * market_adjusted_move + w_sec * sector_median_move

    # 3. Non-Linear Catalyst Magnitude Scaling
    mag_pressure = float(features.get("magnitude_pressure_score", 0.5))
    magnitude_shift = 0.75 + 0.40 * mag_pressure + 0.45 * (mag_pressure ** 2)
    q50 = shrunk_base * magnitude_shift

    # 4. Heavy-Tailed Empirical / Student-t Interval Scaling
    if n_ticker >= 3 and m_ticker > 0:
        p20_ratio = float(np.percentile(ticker_moves, 20)) / m_ticker
        p80_ratio = float(np.percentile(ticker_moves, 80)) / m_ticker
        scale_20 = max(0.35, min(0.80, p20_ratio))
        scale_80 = max(1.35, min(2.80, p80_ratio))
    else:
        # Calibrated Student-t default (nu = 3.5 df)
        scale_20 = 0.60
        scale_80 = 1.75

    q20 = max(0.005, q50 * scale_20)
    q80 = q50 * scale_80

    edge_pct_spot = q50 - implied_move_pct
    uncertainty_buffer = 0.0025  # 0.25% spot buffer

    # 5. Heavy-Tailed Log-Logistic Survival Exceedance Function
    # S(x) = 1 / (1 + (x / q50)^alpha) where alpha = ln(3) / ln(q80 / q50)
    tail_spread_ratio = max(1.05, q80 / max(1e-5, q50))
    alpha = math.log(3.0) / math.log(tail_spread_ratio)
    p_exceeds = 1.0 / (1.0 + (implied_move_pct / max(1e-5, q50)) ** alpha)
    p_exceeds = max(0.01, min(0.99, float(p_exceeds)))

    feature_hash = compute_canonical_hash(features)

    move_forecast = MoveForecast(
        median_abs_move_pct=float(q50),
        q20_abs_move_pct=float(q20),
        q80_abs_move_pct=float(q80),
        probability_exceeds_implied=float(p_exceeds),
        implied_move_pct=float(implied_move_pct),
        edge_pct_spot=float(edge_pct_spot),
        uncertainty_buffer_pct_spot=float(uncertainty_buffer),
        calibration_confidence=0.88 if n_ticker >= 3 else (0.70 if n_ticker else 0.50),
        out_of_distribution=n_ticker == 0,
        model_version=model_version,
        feature_snapshot_hash=feature_hash,
    )

    # IV Crush Forecast (historical post-earnings IV drops typically 50-60% of pre-event IV)
    atm_iv = float(features["atm_iv"])
    expected_iv_drop_pts = -(atm_iv * 0.55 * 100.0)

    iv_crush_forecast = IVCrushForecast(
        median_iv_change_points=float(expected_iv_drop_pts),
        q20_iv_change_points=float(expected_iv_drop_pts * 1.4),
        q80_iv_change_points=float(expected_iv_drop_pts * 0.6),
        model_version=model_version,
        calibration_confidence=0.85,
    )

    return move_forecast, iv_crush_forecast
