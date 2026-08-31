"""Time rules for persisted audit timestamps and Hong Kong school dates."""
from datetime import datetime, timedelta, timezone
import os


HONG_KONG = timezone(timedelta(hours=8), "HKT")


def utc_now() -> datetime:
    """Naive UTC for the existing SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def hong_kong_now() -> datetime:
    if override := os.getenv("APP_TEST_NOW"):
        value = datetime.fromisoformat(override)
        return value.replace(tzinfo=HONG_KONG) if value.tzinfo is None else value.astimezone(HONG_KONG)
    return datetime.now(HONG_KONG)


def hong_kong_today():
    return hong_kong_now().date()
