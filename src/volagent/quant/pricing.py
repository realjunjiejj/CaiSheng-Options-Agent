"""Black-Scholes-Merton option pricing, analytical Greeks, and no-arbitrage bounds."""

import math
from scipy.stats import norm
from volagent.domain.enums import OptionType
from volagent.errors import PricingError


def bsm_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float = 0.045,
    dividend_yield: float = 0.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Compute Black-Scholes-Merton option price with strict domain bounds."""
    if spot <= 0 or not math.isfinite(spot):
        raise PricingError(f"Spot price must be finite and positive, got {spot}")
    if strike <= 0 or not math.isfinite(strike):
        raise PricingError(f"Strike must be finite and positive, got {strike}")
    if volatility <= 0 or not math.isfinite(volatility):
        raise PricingError(f"Volatility must be finite and positive, got {volatility}")
    if time_to_expiry < 0 or not math.isfinite(time_to_expiry):
        raise PricingError(f"Time to expiry must be non-negative and finite, got {time_to_expiry}")

    opt_str = option_type.value if isinstance(option_type, OptionType) else str(option_type).lower()
    if opt_str not in ("call", "put"):
        raise PricingError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")

    # Expired option boundary: return intrinsic
    if time_to_expiry <= 1e-7:
        if opt_str == "call":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    df_r = math.exp(-rate * time_to_expiry)
    df_q = math.exp(-dividend_yield * time_to_expiry)

    if opt_str == "call":
        price = spot * df_q * norm.cdf(d1) - strike * df_r * norm.cdf(d2)
        # Static no-arbitrage lower bound
        lower_bound = max(0.0, spot * df_q - strike * df_r)
        return max(lower_bound, price)
    else:
        price = strike * df_r * norm.cdf(-d2) - spot * df_q * norm.cdf(-d1)
        lower_bound = max(0.0, strike * df_r - spot * df_q)
        return max(lower_bound, price)


def bsm_greeks(
    spot: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    rate: float = 0.045,
    dividend_yield: float = 0.0,
    option_type: OptionType | str = OptionType.CALL,
) -> dict[str, float]:
    """Calculate exact analytical Black-Scholes Greeks."""
    if spot <= 0 or strike <= 0 or volatility <= 0 or time_to_expiry <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "theta_daily": 0.0, "vega": 0.0, "rho": 0.0}

    opt_str = option_type.value if isinstance(option_type, OptionType) else str(option_type).lower()
    if opt_str not in ("call", "put"):
        raise PricingError(f"Invalid option_type: {option_type}")

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    df_r = math.exp(-rate * time_to_expiry)
    df_q = math.exp(-dividend_yield * time_to_expiry)
    pdf_d1 = norm.pdf(d1)

    gamma = (df_q * pdf_d1) / (spot * volatility * sqrt_t)
    vega = spot * df_q * pdf_d1 * sqrt_t / 100.0  # 1% IV change per share

    if opt_str == "call":
        delta = df_q * norm.cdf(d1)
        theta_annual = (
            -(spot * df_q * pdf_d1 * volatility) / (2 * sqrt_t)
            - rate * strike * df_r * norm.cdf(d2)
            + dividend_yield * spot * df_q * norm.cdf(d1)
        )
        rho = strike * time_to_expiry * df_r * norm.cdf(d2) / 100.0
    else:
        delta = -df_q * norm.cdf(-d1)
        theta_annual = (
            -(spot * df_q * pdf_d1 * volatility) / (2 * sqrt_t)
            + rate * strike * df_r * norm.cdf(-d2)
            - dividend_yield * spot * df_q * norm.cdf(-d1)
        )
        rho = -strike * time_to_expiry * df_r * norm.cdf(-d2) / 100.0

    theta_daily = theta_annual / 365.0

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta_daily,
        "theta_daily": theta_daily,
        "vega": vega,
        "rho": rho,
    }
