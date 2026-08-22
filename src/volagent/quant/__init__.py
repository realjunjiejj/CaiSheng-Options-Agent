"""Quantitative options mathematics and pricing engine."""

from volagent.quant.attribution import compute_greek_attribution
from volagent.quant.conventions import normalize_vega_to_points, year_fraction_to_expiry
from volagent.quant.expected_move import ImpliedMoveMetrics, compute_implied_move
from volagent.quant.features import build_quantitative_features
from volagent.quant.forecast import compute_shrinkage_forecast
from volagent.quant.implied_vol import invert_implied_volatility
from volagent.quant.payoff import compute_payoff_curves
from volagent.quant.pricing import bsm_greeks, bsm_price
from volagent.quant.quote_filters import filter_option_chain
from volagent.quant.repricing import reprice_strategy_monte_carlo
from volagent.quant.risk_gate import evaluate_risk_gate
from volagent.quant.strategy_factory import (
    build_long_straddle_candidate,
    build_short_iron_butterfly_candidate,
)
from volagent.quant.strategy_selector import select_best_strategy
from volagent.quant.surface import compute_surface_quality, find_atm_contracts, select_best_expiration

__all__ = [
    "bsm_price",
    "bsm_greeks",
    "invert_implied_volatility",
    "filter_option_chain",
    "year_fraction_to_expiry",
    "normalize_vega_to_points",
    "select_best_expiration",
    "find_atm_contracts",
    "compute_surface_quality",
    "compute_implied_move",
    "ImpliedMoveMetrics",
    "build_quantitative_features",
    "compute_shrinkage_forecast",
    "build_long_straddle_candidate",
    "build_short_iron_butterfly_candidate",
    "reprice_strategy_monte_carlo",
    "select_best_strategy",
    "evaluate_risk_gate",
    "compute_payoff_curves",
    "compute_greek_attribution",
]
