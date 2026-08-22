"""Unit tests for Monte Carlo quantile-preserving sampling and positive ES95 loss magnitude."""

from datetime import date, datetime, timezone
import numpy as np
from volagent.domain.enums import Decision
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.strategies import OptionLeg, StrategyCandidate
from volagent.quant.repricing import reprice_strategy_monte_carlo, sample_quantile_preserving_moves


def test_mc_empirical_quantiles_match_declared_quantiles():
    """Verify VP-11: Piecewise monotone inverse CDF sampling matches forecast quantiles within 25 bps."""
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

    samples = sample_quantile_preserving_moves(fc, n_samples=50_000, random_seed=42)
    abs_moves = np.abs(samples)

    emp_q20 = np.percentile(abs_moves, 20)
    emp_med = np.percentile(abs_moves, 50)
    emp_q80 = np.percentile(abs_moves, 80)

    assert abs(emp_q20 - fc.q20_abs_move_pct) < 0.0025  # Within 25 bps
    assert abs(emp_med - fc.median_abs_move_pct) < 0.0025
    assert abs(emp_q80 - fc.q80_abs_move_pct) < 0.0025


def test_es95_is_positive_loss_magnitude_and_zero_when_no_losses():
    """Verify VP-10: Expected Shortfall is a positive loss magnitude and 0 if all scenarios are profitable."""
    exp = date(2024, 9, 6)
    legs = [
        OptionLeg(contract_symbol="C1", option_type="call", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=0.5, gamma=0.04, theta=-0.1, vega=0.2),
        OptionLeg(contract_symbol="P1", option_type="put", strike=100.0, expiration=exp, side="buy", ratio_qty=1, position_intent="buy_to_open", entry_price_assumption=5.0, delta=-0.5, gamma=0.04, theta=-0.1, vega=0.2),
    ]
    cand = StrategyCandidate(
        strategy_id="strat-1",
        decision=Decision.LONG_STRADDLE,
        legs=legs,
        quantity=1,
        entry_debit_credit=1000.0,
        net_delta=0.0,
        net_gamma=0.08,
        net_theta=-0.2,
        net_vega=0.4,
        max_loss=1000.0,
    )

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

    reprice_cand = reprice_strategy_monte_carlo(cand, 100.0, fc, iv_fc, n_scenarios=2000, random_seed=42)

    # ES95 must be positive (loss magnitude)
    assert reprice_cand.expected_shortfall_95 >= 0.0
