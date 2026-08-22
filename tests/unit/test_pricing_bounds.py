"""Unit tests for Black-Scholes-Merton pricing, analytical Greeks, and mathematical domain bounds."""

import pytest
from volagent.domain.enums import OptionType
from volagent.errors import PricingError
from volagent.quant.pricing import bsm_greeks, bsm_price


def test_bsm_call_put_parity():
    """Verify Put-Call Parity: C - P = S*e^(-qT) - K*e^(-rT)."""
    spot = 100.0
    strike = 100.0
    time_to_expiry = 0.5
    vol = 0.30
    rate = 0.05
    q = 0.0

    call_px = bsm_price(spot, strike, time_to_expiry, vol, rate, q, OptionType.CALL)
    put_px = bsm_price(spot, strike, time_to_expiry, vol, rate, q, OptionType.PUT)

    lhs = call_px - put_px
    rhs = spot - strike * 0.9753099  # exp(-0.05*0.5) = 0.9753099
    assert abs(lhs - (spot - strike * (2.718281828459045 ** (-rate * time_to_expiry)))) < 1e-4


def test_bsm_greeks_analytical():
    """Verify analytical Greeks match mathematical properties."""
    spot = 100.0
    strike = 100.0
    time_to_expiry = 0.25
    vol = 0.25

    c_greeks = bsm_greeks(spot, strike, time_to_expiry, vol, option_type=OptionType.CALL)
    p_greeks = bsm_greeks(spot, strike, time_to_expiry, vol, option_type=OptionType.PUT)

    assert 0.0 < c_greeks["delta"] < 1.0
    assert -1.0 < p_greeks["delta"] < 0.0
    assert c_greeks["gamma"] > 0.0
    assert abs(c_greeks["gamma"] - p_greeks["gamma"]) < 1e-6
    assert c_greeks["vega"] > 0.0
    assert abs(c_greeks["vega"] - p_greeks["vega"]) < 1e-6


def test_pricing_domain_bounds_validation():
    """Verify that non-positive spot, strike, vol, or invalid option_type raise PricingError."""
    with pytest.raises(PricingError):
        bsm_price(spot=-100.0, strike=100.0, time_to_expiry=0.5, volatility=0.30)

    with pytest.raises(PricingError):
        bsm_price(spot=100.0, strike=-100.0, time_to_expiry=0.5, volatility=0.30)

    with pytest.raises(PricingError):
        bsm_price(spot=100.0, strike=100.0, time_to_expiry=0.5, volatility=-0.30)

    with pytest.raises(PricingError):
        bsm_price(spot=100.0, strike=100.0, time_to_expiry=0.5, volatility=0.30, option_type="invalid_type")
