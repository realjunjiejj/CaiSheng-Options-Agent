"""Out-Of-Distribution (OOD) and Regime Anomaly Detector for CaiSheng Options Alpha."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OODCheckResult:
    is_out_of_distribution: bool
    reasons: list[str]


def detect_out_of_distribution(
    spot: float,
    atm_iv: float,
    implied_move_pct: float,
    expected_move_median_pct: float,
    atm_bid: float = 0.0,
    atm_ask: float = 0.0,
    historical_move_std: float | None = None,
    max_atm_iv: float = 2.00,  # 200% IV cap
    min_atm_iv: float = 0.08,  # 8% IV floor
    max_spread_pct_mid: float = 0.25,  # 25% max bid-ask spread relative to mid
) -> OODCheckResult:
    """Evaluate market and forecast inputs for extreme distribution anomalies."""
    reasons: list[str] = []

    # 1. Extreme IV boundaries
    if atm_iv > max_atm_iv:
        reasons.append(f"ATM implied volatility ({atm_iv*100:.1f}%) exceeds maximum safe ceiling ({max_atm_iv*100:.1f}%)")
    elif atm_iv < min_atm_iv:
        reasons.append(f"ATM implied volatility ({atm_iv*100:.1f}%) below minimum realistic floor ({min_atm_iv*100:.1f}%)")

    # 2. Implied vs Forecast Disconnection
    if expected_move_median_pct > 0 and implied_move_pct > 0:
        ratio = implied_move_pct / expected_move_median_pct
        if ratio > 4.0:
            reasons.append(f"Implied move ({implied_move_pct*100:.1f}%) is >4x expected move ({expected_move_median_pct*100:.1f}%)")
        elif ratio < 0.25:
            reasons.append(f"Implied move ({implied_move_pct*100:.1f}%) is <0.25x expected move ({expected_move_median_pct*100:.1f}%)")

    # 3. Severe Option Market Friction / Illiquidity
    if atm_ask > 0 and atm_bid >= 0 and (atm_ask + atm_bid) > 0:
        mid = (atm_ask + atm_bid) / 2.0
        spread = atm_ask - atm_bid
        spread_pct = spread / mid if mid > 0 else 1.0
        if spread_pct > max_spread_pct_mid:
            reasons.append(f"ATM option bid-ask spread ({spread_pct*100:.1f}% of mid) exceeds max threshold ({max_spread_pct_mid*100:.1f}%)")

    # 4. Jump Dispersion Anomaly
    if historical_move_std is not None and expected_move_median_pct > 0:
        if historical_move_std > 3.5 * expected_move_median_pct:
            reasons.append(f"Historical move dispersion ({historical_move_std*100:.1f}%) > 3.5x median ({expected_move_median_pct*100:.1f}%)")

    return OODCheckResult(
        is_out_of_distribution=len(reasons) > 0,
        reasons=reasons,
    )
