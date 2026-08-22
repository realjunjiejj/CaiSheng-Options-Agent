"""Greeks P&L attribution and Taylor series decomposition."""

from typing import Any
from volagent.domain.strategies import StrategyCandidate


def compute_greek_attribution(
    candidate: StrategyCandidate,
    spot_change: float,
    iv_change_pts: float,
    dt_days: float = 1.0,
) -> dict[str, float]:
    """Decompose expected P&L change into Delta, Gamma, Vega, and Theta contributions.
    
    Taylor expansion:
    dV ~ Delta * dS + 0.5 * Gamma * (dS)^2 + Vega * d_sigma + Theta * dt + residual
    """
    delta_pnl = candidate.net_delta * spot_change
    gamma_pnl = 0.5 * candidate.net_gamma * (spot_change**2)
    vega_pnl = candidate.net_vega * iv_change_pts
    theta_pnl = candidate.net_theta * dt_days

    explained_pnl = delta_pnl + gamma_pnl + vega_pnl + theta_pnl

    return {
        "delta_contribution": float(delta_pnl),
        "gamma_contribution": float(gamma_pnl),
        "vega_contribution": float(vega_pnl),
        "theta_contribution": float(theta_pnl),
        "total_explained": float(explained_pnl),
    }
