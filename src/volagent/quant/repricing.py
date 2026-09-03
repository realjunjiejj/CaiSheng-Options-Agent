"""Monte Carlo repricing, Expected Shortfall (ES95), and 2D stress matrix.

Academic References:
- Rockafellar, R. T., & Uryasev, S. (2000). "Optimization of Conditional Value-at-Risk." Journal of Risk, 2(3), 21-41.
- Carr, P., & Wu, L. (2009). "The Finite-Moment Log-Normal Model for Option Pricing and the Variance Risk Premium." J. Financial Economics, 93(3), 476-499.
"""

import math
import numpy as np
from scipy.interpolate import PchipInterpolator

from volagent.domain.enums import OptionType
from volagent.domain.forecasts import IVCrushForecast, MoveForecast
from volagent.domain.strategies import StrategyCandidate
from volagent.quant.pricing import bsm_price


def sample_quantile_preserving_moves(
    forecast: MoveForecast,
    n_samples: int = 3000,
    random_seed: int = 42,
) -> np.ndarray:
    """Sample moves using a piecewise monotone inverse CDF matching forecast quantiles."""
    rng = np.random.default_rng(random_seed)

    # Establish quantile anchor knots
    q_points = np.array([0.01, 0.05, 0.20, 0.50, 0.80, 0.95, 0.99])
    
    # Scale quantiles based on forecast spread
    med = forecast.median_abs_move_pct
    q20 = forecast.q20_abs_move_pct
    q80 = forecast.q80_abs_move_pct
    q05 = max(0.001, q20 - 0.7 * (med - q20))
    q95 = q80 + 1.2 * (q80 - med)
    q01 = max(0.0005, q05 * 0.5)
    q99 = q95 * 1.5

    move_knots = np.array([q01, q05, q20, med, q80, q95, q99])
    # Monotone cubic spline (PCHIP) for inverse CDF
    inv_cdf = PchipInterpolator(q_points, move_knots)

    u = rng.uniform(0.01, 0.99, size=n_samples)
    abs_moves = inv_cdf(u)

    # Direction symmetry (unconditional on direction)
    signs = rng.choice([-1.0, 1.0], size=n_samples)
    return signs * abs_moves


def reprice_strategy_monte_carlo(
    candidate: StrategyCandidate,
    spot_price: float,
    move_forecast: MoveForecast,
    iv_forecast: IVCrushForecast,
    n_scenarios: int = 3000,
    random_seed: int = 42,
    exit_horizon_years: float = 1.0 / 365.0,
    slippage_per_contract: float = 0.02,
    fee_per_contract: float = 0.65,
) -> StrategyCandidate:
    """Reprice multi-leg strategy across Monte Carlo scenarios with positive ES95 loss magnitude."""
    sampled_log_moves = sample_quantile_preserving_moves(move_forecast, n_samples=n_scenarios, random_seed=random_seed)
    sampled_spots = spot_price * np.exp(sampled_log_moves)

    # IV Crush change in volatility points
    iv_shock = iv_forecast.median_iv_change_points / 100.0  # e.g. -0.15 for -15 pts
    entry_cost = candidate.entry_debit_credit
    qty = candidate.quantity

    if qty <= 0:
        candidate.expected_pnl = 0.0
        candidate.expected_shortfall_95 = 0.0
        candidate.risk_adjusted_score = 0.0
        candidate.stress_losses = {}
        return candidate

    pnl_samples = np.zeros(n_scenarios)
    total_round_trip_friction = (
        len(candidate.legs)
        * 2.0
        * (fee_per_contract + slippage_per_contract * 100.0)
        * qty
    )

    for i in range(n_scenarios):
        scenario_spot = sampled_spots[i]
        scenario_val = 0.0

        for leg in candidate.legs:
            # Reprice from the point-in-time contract IV. Legacy synthetic
            # candidates without IV retain a documented neutral fallback.
            entry_iv = leg.implied_vol if leg.implied_vol is not None else 0.60
            leg_iv = max(0.05, min(5.0, entry_iv + iv_shock))
            opt_type = OptionType.CALL if leg.option_type == "call" else OptionType.PUT
            px = bsm_price(
                spot=scenario_spot,
                strike=leg.strike,
                time_to_expiry=max(1.0 / 365.0, exit_horizon_years),
                volatility=leg_iv,
                option_type=opt_type,
            )
            # Long adds value, Short subtracts value to close
            if leg.side == "buy":
                scenario_val += px * 100.0 * leg.ratio_qty * qty
            else:
                scenario_val -= px * 100.0 * leg.ratio_qty * qty

        # Net PnL = Exit Value - Entry Debit (or + Entry Credit) - round-trip costs
        pnl_samples[i] = scenario_val - entry_cost - total_round_trip_friction

    # Expected Value & Positive Loss Magnitude ES95
    ev = float(np.mean(pnl_samples))
    losses = np.maximum(-pnl_samples, 0.0)  # Positive loss magnitude
    var95 = float(np.percentile(losses, 95))
    tail_losses = losses[losses >= var95]
    es95 = float(np.mean(tail_losses)) if len(tail_losses) > 0 else 0.0

    # Risk Adjusted Score = EV - 0.02 * ES95 (positive EV with bounded tail penalty)
    score = ev - 0.02 * es95

    # 2D Stress Loss Matrix (Worst-Case Loss at price & IV shocks)
    stress_results = {}
    price_shocks = [-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15]
    iv_shocks = [-0.30, -0.15, 0.0, 0.15, 0.30]

    for p_pct in price_shocks:
        for v_pts in iv_shocks:
            st_spot = spot_price * (1.0 + p_pct)
            st_val = 0.0
            for leg in candidate.legs:
                base_iv = leg.implied_vol if leg.implied_vol is not None else 0.60
                leg_st_iv = max(0.05, base_iv + v_pts)
                opt_type = OptionType.CALL if leg.option_type == "call" else OptionType.PUT
                px = bsm_price(
                    spot=st_spot,
                    strike=leg.strike,
                    time_to_expiry=max(1.0 / 365.0, exit_horizon_years),
                    volatility=leg_st_iv,
                    option_type=opt_type,
                )
                if leg.side == "buy":
                    st_val += px * 100.0 * leg.ratio_qty * qty
                else:
                    st_val -= px * 100.0 * leg.ratio_qty * qty

            st_pnl = st_val - entry_cost - total_round_trip_friction
            st_loss = max(-st_pnl, 0.0)
            key = f"P_{int(p_pct*100):+03d}_IV_{int(v_pts*100):+03d}"
            stress_results[key] = float(st_loss)

    candidate.expected_pnl = round(ev, 2)
    candidate.expected_shortfall_95 = round(es95, 2)
    candidate.risk_adjusted_score = round(score, 2)
    candidate.stress_losses = stress_results

    return candidate
