"""Shared Beijing time semantics for logs and stored local timestamps."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    SHANGHAI = ZoneInfo('Asia/Shanghai')
except ZoneInfoNotFoundError:
    SHANGHAI = timezone(timedelta(hours=8))
BEIJING = SHANGHAI


def now():
    return datetime.now(SHANGHAI).replace(tzinfo=None, microsecond=0)
