import re
from datetime import datetime, timezone

_FRACTION = re.compile(r"\.(\d+)")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utcnow().isoformat()


def parse_ts(value):
    """Parse an ISO-8601 timestamp (as returned by PostgREST) to an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    # normalise fractional seconds to exactly 6 digits for fromisoformat
    text = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
