from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.db import db_fetchall
from routes.case_management_parts.helpers import placeholder

CHICAGO_TZ = ZoneInfo("America/Chicago")


def parse_date_only(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def status_is_open_for_discipline(value: str | None) -> bool:
    return str(value or "").strip().lower() == "open"


def load_active_writeup_restrictions(resident_id: int) -> list[dict]:
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            incident_date,
            category,
            severity,
            summary,
            status,
            disciplinary_outcome,
            probation_start_date,
            probation_end_date,
            pre_termination_date,
            blocks_passes
        FROM resident_writeups
        WHERE resident_id = {ph}
          AND COALESCE(blocks_passes, {("FALSE" if ph == "%s" else "0")}) = {("TRUE" if ph == "%s" else "1")}
        ORDER BY incident_date DESC, id DESC
        """,
        (resident_id,),
    )

    today = datetime.now(CHICAGO_TZ).date()
    active: list[dict] = []

    for row in rows or []:
        item = dict(row)
        outcome = str(item.get("disciplinary_outcome") or "").strip().lower()
        is_open = status_is_open_for_discipline(item.get("status"))

        if outcome == "program_probation":
            start_date = parse_date_only(item.get("probation_start_date"))
            end_date = parse_date_only(item.get("probation_end_date"))

            is_active = bool(
                is_open and start_date and end_date and start_date <= today <= end_date
            )
            if is_active:
                item["label"] = "Program Probation"
                item["detail"] = (
                    f"{item.get('probation_start_date') or '—'} to {item.get('probation_end_date') or '—'}"
                )
                active.append(item)
            continue

        if outcome == "pre_termination":
            scheduled_date = parse_date_only(item.get("pre_termination_date"))

            is_active = bool(is_open and scheduled_date and today <= scheduled_date)
            if is_active:
                item["label"] = "Pre Termination Scheduled"
                item["detail"] = f"{item.get('pre_termination_date') or '—'}"
                active.append(item)

    return active
