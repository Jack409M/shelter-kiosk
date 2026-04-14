from datetime import datetime
from zoneinfo import ZoneInfo

CHICAGO_TZ = ZoneInfo("America/Chicago")


def to_chicago_time(value: str | None) -> str:
    if not value:
        return "—"

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt_local = dt.astimezone(CHICAGO_TZ)
        return dt_local.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return value
