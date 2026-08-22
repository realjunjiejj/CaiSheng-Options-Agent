"""Payoff matrix generation for Plotly visualization with strict signed cash-flow conventions."""

from typing import Any
import numpy as np

from volagent.domain.strategies import StrategyCandidate
from volagent.quant.pricing import bsm_price


def compute_payoff_curves(
    candidate: StrategyCandidate,
    spot_price: float,
    implied_move_dollars: float,
    exit_t_years: float = 0.035,
    post_event_iv_drop_pts: float = -15.0,
    rate: float = 0.045,
    n_points: int = 150,
) -> dict[str, Any]:
    """Generate high-resolution payoff curves at expiration and at post-earnings exit.
    
    Signed Cash-flow Convention:
    Entry cash flow (entry_debit_credit):
      - Positive for debit paid (e.g. +$1000 for Long Straddle)
      - Negative for credit received (e.g. -$600 for Short Iron Butterfly)
    
    PnL(S) = Position_Value(S) - Entry_Cash_Flow
    """
    span = max(spot_price * 0.25, implied_move_dollars * 2.5)
    spot_range = np.linspace(spot_price - span, spot_price + span, n_points)

    entry_cash_flow = candidate.entry_debit_credit
    pnl_at_expiry = np.zeros(n_points)
    pnl_at_exit = np.zeros(n_points)

    for i, s in enumerate(spot_range):
        # 1. At expiration payoff (intrinsic value)
        unit_val_expiry = 0.0
        for leg in candidate.legs:
            if leg.option_type == "call":
                intrinsic = max(0.0, s - leg.strike)
            else:
                intrinsic = max(0.0, leg.strike - s)

            if leg.side == "buy":
                unit_val_expiry += 100.0 * intrinsic * leg.ratio_qty
            else:
                unit_val_expiry -= 100.0 * intrinsic * leg.ratio_qty

        # PnL = Liquidation Value - Net Entry Debit (or + Net Entry Credit)
        pnl_at_expiry[i] = (unit_val_expiry * candidate.quantity) - entry_cash_flow

        # 2. At exit payoff (with post-event IV crush)
        unit_val_exit = 0.0
        for leg in candidate.legs:
            iv = max(0.05, 0.60 + (post_event_iv_drop_pts / 100.0))
            p = bsm_price(s, leg.strike, exit_t_years, iv, rate, option_type=leg.option_type)
            if leg.side == "buy":
                unit_val_exit += 100.0 * p * leg.ratio_qty
            else:
                unit_val_exit -= 100.0 * p * leg.ratio_qty

        pnl_at_exit[i] = (unit_val_exit * candidate.quantity) - entry_cash_flow

    return {
        "spot_range": spot_range.tolist(),
        "pnl_at_expiry": pnl_at_expiry.tolist(),
        "pnl_at_exit": pnl_at_exit.tolist(),
        "spot_price": spot_price,
        "break_evens": candidate.break_evens,
    }
