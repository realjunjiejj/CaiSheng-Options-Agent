"""Market conventions, time calculations, and Greek sign rules."""

from datetime import date, datetime, time, timezone
import zoneinfo
import numpy as np

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def year_fraction_to_expiry(current_dt: datetime, expiration_date: date) -> float:
    """Calculate annualized time to expiration T in years (ACT/365.25 convention).
    
    Standard US equity option settlement is assumed to be 16:00 America/New_York on expiry date.
    """
    if current_dt.tzinfo is None:
        raise ValueError("current_dt must be timezone-aware.")
    
    expiry_dt = datetime.combine(
        expiration_date,
        time(16, 0, 0),
        tzinfo=NY_TZ
    ).astimezone(timezone.utc)
    
    current_utc = current_dt.astimezone(timezone.utc)
    seconds_remaining = (expiry_dt - current_utc).total_seconds()
    
    if seconds_remaining <= 0:
        return 1e-6  # Minimum positive epsilon for numerical stability
    
    return seconds_remaining / (365.25 * 86400.0)


def normalize_vega_to_points(dollar_vega: float) -> float:
    """Convert 100% vol vega to 1-point (1.0%) vol change dollars."""
    return dollar_vega / 100.0
