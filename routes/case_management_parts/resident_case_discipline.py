from __future__ import annotations

from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from core.db import db_fetchall
from routes.case_management_parts.helpers import placeholder


type Row = dict[str, Any]
type RowList = list[Row]

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _chicago_today() -> date:
    return datetime.now(CHICAGO_TZ).date()


def _true_sql(ph: str) -> str:
    return "TRUE" if ph == "%s" else "1"


def _false_sql(ph: str) -> str:
    return "FALSE" if ph == "%s" else "0"


def parse_date_only(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def status_is_open_for_discipline(value: str | None) -> bool:
    return str(value or "").strip().lower() == "open"


def _is_active_probation(*, item: Row, today: date) -> bool:
    start_date = parse_date_only(item.get("probation_start_date"))
    end_date = parse_date_only(item.get("probation_end_date"))

    return bool(
        status_is_open_for_discipline(item.get("status"))
        and start_date
        and end_date
        and start_date <= today <= end_date
    )


def _is_active_pre_termination(*, item: Row, today: date) -> bool:
    scheduled_date = parse_date_only(item.get("pre_termination_date"))

    return bool(
        status_is_open_for_discipline(item.get("status"))
        and scheduled_date
        and today <= scheduled_date
    )


def _decorate_probation_item(item: Row) -> Row:
    decorated = dict(item)
    decorated["label"] = "Program Probation"
    decorated["detail"] = (
        f"{item.get('probation_start_date') or '—'} to "
        f"{item.get('probation_end_date') or '—'}"
    )
    return decorated


def _decorate_pre_termination_item(item: Row) -> Row:
    decorated = dict(item)
    decorated["label"] = "Pre Termination Scheduled"
    decorated["detail"] = f"{item.get('pre_termination_date') or '—'}"
    return decorated


def load_active_writeup_restrictions(resident_id: int) -> RowList:
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
          AND COALESCE(blocks_passes, {_false_sql(ph)}) = {_true_sql(ph)}
        ORDER BY incident_date DESC, id DESC
        """,
        (resident_id,),
    )

    today = _chicago_today()
    active: RowList = []

    for row in rows or []:
        item: Row = dict(row)
        outcome = str(item.get("disciplinary_outcome") or "").strip().lower()

        if outcome == "program_probation":
            if _is_active_probation(item=item, today=today):
                active.append(_decorate_probation_item(item))
            continue

        if outcome == "pre_termination":
            if _is_active_pre_termination(item=item, today=today):
                active.append(_decorate_pre_termination_item(item))

    return active
