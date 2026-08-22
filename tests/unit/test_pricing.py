"""Unit tests for Black-Scholes pricing, Greeks, and IV inversion."""

import math
import pytest
from volagent.quant.implied_vol import invert_implied_volatility
from volagent.quant.pricing import bsm_greeks, bsm_price


def test_bsm_call_put_parity():
    spot = 100.0
    strike = 100.0
    t = 0.25
    vol = 0.30
    r = 0.05
    q = 0.0

    call_p = bsm_price(spot, strike, t, vol, r, q, "call")
    put_p = bsm_price(spot, strike, t, vol, r, q, "put")

    # Put-Call Parity: C - P = S*exp(-q*t) - K*exp(-r*t)
    lhs = call_p - put_p
    rhs = spot * math.exp(-q * t) - strike * math.exp(-r * t)
    assert pytest.approx(lhs, abs=1e-4) == rhs


def test_bsm_greeks_analytical():
    spot = 120.0
    strike = 120.0
    t = 0.1
    vol = 0.45
    r = 0.045

    call_g = bsm_greeks(spot, strike, t, vol, r, option_type="call")
    put_g = bsm_greeks(spot, strike, t, vol, r, option_type="put")

    # ATM Call Delta ~ 0.53, Put Delta ~ -0.47
    assert 0.45 < call_g["delta"] < 0.60
    assert -0.55 < put_g["delta"] < -0.40
    # Delta difference should be ~ exp(-q*t) = 1.0
    assert pytest.approx(call_g["delta"] - put_g["delta"], abs=1e-4) == 1.0

    # Gamma and Vega are identical
    assert pytest.approx(call_g["gamma"], abs=1e-6) == put_g["gamma"]
    assert pytest.approx(call_g["vega"], abs=1e-6) == put_g["vega"]
    assert call_g["gamma"] > 0
    assert call_g["vega"] > 0
    assert call_g["theta_daily"] < 0


def test_brent_iv_inversion():
    spot = 150.0
    strike = 155.0
    t = 0.15
    true_vol = 0.385
    r = 0.045

    call_p = bsm_price(spot, strike, t, true_vol, r, option_type="call")
    recovered_vol = invert_implied_volatility(call_p, spot, strike, t, r, option_type="call")

    assert recovered_vol is not None
    assert pytest.approx(recovered_vol, abs=1e-4) == true_vol
