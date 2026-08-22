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


def brenner_subrahmanyam_implied_volatility(
    price: float,
    spot: float,
    time_to_expiry: float,
) -> float | None:
    """Brenner-Subrahmanyam (1988) closed-form ATM implied volatility approximation:
    sigma ~ sqrt(2*pi / T) * (C_ATM / S).
    """
    if price <= 0 or spot <= 0 or time_to_expiry <= 0:
        return None
    return float(math.sqrt(2.0 * math.pi / time_to_expiry) * (price / spot))


def corrado_miller_implied_volatility(
    price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    rate: float = 0.045,
    option_type: str = "call",
) -> float | None:
    """Corrado-Miller (1996) closed-form implied volatility approximation.
    
    Academic Reference:
    - Corrado, C. J., & Miller, T. W. (1996). "A simple, accurate formula for computing
      implied volatility." Journal of Financial and Quantitative Analysis, 31(4), 623-629.
    """
    if price <= 0 or spot <= 0 or strike <= 0 or time_to_expiry <= 0:
        return None

    t = time_to_expiry
    x = strike * math.exp(-rate * t)

    # If put, convert to synthetic call via Put-Call Parity: C = P + S - X
    if option_type.lower() == "put":
        c = price + spot - x
    else:
        c = price

    if c <= max(0.0, spot - x):
        return None

    m = c - (spot - x) / 2.0
    radicand = m**2 - ((spot - x)**2) / math.pi
    if radicand < 0:
        radicand = 0.0

    numerator = math.sqrt(2.0 * math.pi) * (m + math.sqrt(radicand))
    denominator = (spot + x) * math.sqrt(t)

    if denominator <= 0:
        return None

    iv = numerator / denominator
    return float(iv)

