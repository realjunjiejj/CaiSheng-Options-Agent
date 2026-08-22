"""Market clock, timezone handling, and exact day count convention for VolAgent Alpha."""

from datetime import date, datetime, time, timezone
import zoneinfo

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """Return the current time in UTC with timezone awareness."""
    return datetime.now(timezone.utc)


def now_ny() -> datetime:
    """Return current time in America/New_York timezone."""
    return datetime.now(NY_TZ)


def to_ny(dt: datetime) -> datetime:
    """Convert any aware datetime to America/New_York."""
    if dt.tzinfo is None:
        raise ValueError("Cannot convert naive datetime to NY timezone; must be aware.")
    return dt.astimezone(NY_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert any aware datetime to UTC."""
    if dt.tzinfo is None:
        raise ValueError("Cannot convert naive datetime to UTC; must be aware.")
    return dt.astimezone(timezone.utc)


def year_fraction_to_expiry(as_of: datetime, expiration: date) -> float:
    """Compute exact ACT/365 year fraction from as_of datetime to 16:00:00 NY market close on expiration date."""
    exp_dt = datetime.combine(expiration, time(16, 0, 0), tzinfo=NY_TZ).astimezone(timezone.utc)
    as_of_utc = as_of.astimezone(timezone.utc) if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    seconds = (exp_dt - as_of_utc).total_seconds()
    if seconds <= 0:
        return 0.0
    return seconds / (365.0 * 86400.0)
