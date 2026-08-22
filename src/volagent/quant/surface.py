"""Option surface diagnostics, ATM selection, and expiration ranking."""

from datetime import date, datetime
import math
from typing import Any
import numpy as np

from volagent.clock import year_fraction_to_expiry
from volagent.config import ContractFiltersConfig
from volagent.domain.market import OptionContractSnapshot


def select_best_expiration(
    available_expirations: list[date],
    event_date: date,
    config: ContractFiltersConfig,
    chain: list[OptionContractSnapshot],
) -> date | None:
    """Select the optimal expiration date following earnings event based on liquidity and DTE."""
    eligible = []
    for exp in available_expirations:
        dte = (exp - event_date).days
        if config.min_dte_days <= dte <= config.max_dte_days:
            # Score by ATM volume & open interest
            exp_contracts = [c for c in chain if c.expiration == exp]
            total_oi = sum(c.open_interest for c in exp_contracts)
            total_vol = sum(c.volume for c in exp_contracts)
            eligible.append((dte, total_oi, total_vol, exp))

    if not eligible:
        return None

    # Rank by shortest DTE, then highest open interest
    eligible.sort(key=lambda x: (x[0], -x[1], -x[2]))
    return eligible[0][3]


def find_atm_contracts(
    chain: list[OptionContractSnapshot],
    spot_price: float,
    rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> tuple[OptionContractSnapshot | None, OptionContractSnapshot | None, float]:
    """Find ATM Call and Put matching the closest forward price strike."""
    if not chain or spot_price <= 0:
        return None, None, 0.0

    # Group contracts by strike
    calls_by_strike = {c.strike: c for c in chain if c.option_type == "call"}
    puts_by_strike = {p.strike: p for p in chain if p.option_type == "put"}

    # Common strikes with both call and put available
    common_strikes = list(set(calls_by_strike.keys()) & set(puts_by_strike.keys()))
    if not common_strikes:
        return None, None, 0.0

    # Pick strike closest to spot price
    atm_strike = min(common_strikes, key=lambda k: abs(k - spot_price))
    return calls_by_strike[atm_strike], puts_by_strike[atm_strike], atm_strike


def compute_surface_quality(
    chain: list[OptionContractSnapshot],
    spot_price: float,
) -> float:
    """Calculate normalized option surface liquidity and quality score [0.0, 1.0]."""
    if not chain or spot_price <= 0:
        return 0.0

    scores = []
    for c in chain:
        mid = (c.bid + c.ask) / 2.0
        if mid <= 0:
            continue
        rel_spread = (c.ask - c.bid) / mid
        spread_score = max(0.0, 1.0 - (rel_spread / 0.20))
        oi_score = min(1.0, c.open_interest / 1000.0)
        vol_score = min(1.0, c.volume / 500.0)
        scores.append(0.5 * spread_score + 0.3 * oi_score + 0.2 * vol_score)

    if not scores:
        return 0.0
    return float(np.mean(scores))
