"""Timezone utilities for US Central Time conversion.

The application stores all datetimes in UTC but displays and calculates
business logic in US Central Time (America/Chicago).
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# US Central Time zone (handles CST/CDT automatically)
CENTRAL_TZ = ZoneInfo("America/Chicago")


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def to_central(dt: datetime) -> datetime:
    """Convert a UTC datetime to US Central Time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CENTRAL_TZ)


def central_now() -> datetime:
    """Return the current time in US Central Time."""
    return datetime.now(CENTRAL_TZ)


def central_today() -> date:
    """Return today's date in US Central Time."""
    return datetime.now(CENTRAL_TZ).date()
