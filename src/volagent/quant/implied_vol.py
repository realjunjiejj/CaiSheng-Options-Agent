"""Robust implied volatility inversion using Brent root-finding."""

import math
from scipy.optimize import brentq
from volagent.quant.pricing import bsm_price


def invert_implied_volatility(
    price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float = 0.045,
    dividend_yield: float = 0.0,
    option_type: str = "call",
    vol_min: float = 1e-4,
    vol_max: float = 5.0,
) -> float | None:
    """Invert Black-Scholes-Merton option price to find Implied Volatility (sigma).
    
    Returns None if market price violates arbitrage bounds or root cannot be found.
    """
    if price <= 0 or spot <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None

    # Lower bound check (intrinsic value)
    t = time_to_expiry
    df_q = math.exp(-dividend_yield * t)
    df_r = math.exp(-rate * t)

    if option_type.lower() == "call":
        intrinsic = max(0.0, spot * df_q - strike * df_r)
        upper_bound = spot * df_q
    else:
        intrinsic = max(0.0, strike * df_r - spot * df_q)
        upper_bound = strike * df_r

    if price < intrinsic or price > upper_bound:
        return None

    def objective(v: float) -> float:
        return bsm_price(spot, strike, t, v, rate, dividend_yield, option_type) - price

    f_min = objective(vol_min)
    f_max = objective(vol_max)

    if f_min * f_max > 0:
        return None

    try:
        root = brentq(objective, vol_min, vol_max, xtol=1e-6, maxiter=100)
        return float(root)
    except Exception:
        return None
