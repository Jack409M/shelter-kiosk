from flask import g


def is_postgres():
    return g.get("db_kind") == "pg"

def db_placeholder():
    if g.get("db_kind") == "pg":
        return "%s"
    return "?"

from datetime import datetime, timezone

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def fmt_date(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%m/%d/%Y")
    except Exception:
        return dt_iso
