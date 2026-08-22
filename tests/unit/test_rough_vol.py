"""Unit tests for Rough Volatility, Markovian Lifting, and Path Signature library."""

import math
import numpy as np
import pytest

from volagent.quant.rough_vol import (
    compute_lifted_kernel_weights,
    compute_path_signature_2d,
    compute_rough_vol_smile,
    simulate_lifted_heston,
)


def test_lifted_kernel_weights_geometric_spacing():
    """Verify Abi Jaber et al. (2019): Geometrically spaced mean-reversion nodes and positive weights."""
    x_nodes, c_weights = compute_lifted_kernel_weights(hurst=0.10, n_factors=8, x_min=0.05, x_max=500.0)
    
    assert len(x_nodes) == 8
    assert len(c_weights) == 8
    assert x_nodes[0] == pytest.approx(0.05, rel=1e-3)
    assert x_nodes[-1] == pytest.approx(500.0, rel=1e-3)
    
    # Strictly increasing mean-reversion speeds
    for i in range(len(x_nodes) - 1):
        assert x_nodes[i + 1] > x_nodes[i]
        
    # Strictly positive weights
    assert np.all(c_weights > 0.0)


def test_simulate_lifted_heston_state_dimensions():
    """Verify Gatheral et al. (2018) & Lifted Heston simulation shapes and non-negative variances."""
    res = simulate_lifted_heston(
        spot=100.0,
        v0=0.04,
        hurst=0.10,
        n_factors=6,
        nu=0.30,
        rho=-0.70,
        time_to_expiry=0.05,
        n_steps=20,
        n_paths=500,
        random_seed=42,
    )
    
    assert len(res["terminal_spots"]) == 500
    assert len(res["terminal_vars"]) == 500
    assert np.all(res["terminal_spots"] > 0.0)
    assert np.all(res["terminal_vars"] > 0.0)
    assert res["spot_paths"].shape == (5, 21)
    assert res["vol_paths"].shape == (5, 21)


def test_compute_rough_vol_smile_structure():
    """Verify that rough volatility generates an inverted implied volatility smile across strikes."""
    res = compute_rough_vol_smile(
        spot=200.0,
        v0=0.04,
        hurst=0.10,
        n_factors=6,
        nu=0.40,
        rho=-0.70,
        time_to_expiry=0.05,
        strike_range_pct=0.10,
        n_strikes=9,
        n_paths=1000,
        random_seed=42,
    )
    
    assert len(res["strikes"]) == 9
    assert len(res["rough_ivs"]) == 9
    assert len(res["standard_ivs"]) == 9
    assert np.all(res["rough_ivs"] > 0.0)
    
    # Leverage effect (rho < 0) produces negative skew: OTM put IV (low strike) > OTM call IV (high strike)
    assert res["rough_ivs"][0] > res["rough_ivs"][-1]


def test_compute_path_signature_2d_invariants():
    """Verify Lyons (1998): Level 1 and Level 2 iterated integrals and Levy area."""
    t_series = np.linspace(0.0, 1.0, 100)
    s_series = 100.0 + 5.0 * np.sin(2.0 * math.pi * t_series)  # Oscillating closed loop
    
    sig = compute_path_signature_2d(t_series, s_series, depth=2)
    
    assert "sig_t" in sig
    assert "sig_s" in sig
    assert "sig_tt" in sig
    assert "sig_ts" in sig
    assert "sig_st" in sig
    assert "sig_ss" in sig
    assert "levy_area" in sig
    
    # Normalized time goes from 0 to 1
    assert sig["sig_t"] == pytest.approx(1.0, rel=1e-3)
    # Closed loop returns to 0
    assert abs(sig["sig_s"]) < 1e-4
    # Realized Levy area is non-zero for 2D curve
    assert abs(sig["levy_area"]) > 0.0
