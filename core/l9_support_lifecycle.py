from __future__ import annotations

from datetime import UTC, date, datetime

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder

L9_STATUS_ACTIVE = "active"
L9_PARTICIPATION_ENROLLED = "enrolled"


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _add_months(start_date: str, months: int) -> str:
    d = date.fromisoformat(start_date)
    year = d.year + ((d.month - 1 + months) // 12)
    month = ((d.month - 1 + months) % 12) + 1

    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        max_day = 29 if leap else 28
    elif month in {4, 6, 9, 11}:
        max_day = 30
    else:
        max_day = 31

    day = min(d.day, max_day)
    return date(year, month, day).isoformat()


def start_level9_lifecycle(
    *,
    resident_id: int,
    enrollment_id: int,
    shelter: str,
    case_manager_user_id: int | None = None,
    started_by_user_id: int | None = None,
    start_date: str | None = None,
    apartment_exit_reason: str | None = None,
    notes: str | None = None,
):
    ph = placeholder()

    existing = db_fetchone(
        f"SELECT id FROM level9_support_lifecycles WHERE enrollment_id = {ph}",
        (enrollment_id,),
    )
    if existing:
        return existing

    start = (start_date or _today_iso())[:10]
    end = _add_months(start, 6)
    now = utcnow_iso()

    with db_transaction():
        row = db_fetchone(
            f"""
            INSERT INTO level9_support_lifecycles (
                resident_id, enrollment_id, shelter,
                case_manager_user_id, started_by_user_id,
                status, participation_status,
                start_date, initial_end_date,
                apartment_exit_date, apartment_exit_reason,
                created_at, updated_at
            ) VALUES (
                {ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph}
            ) RETURNING id
            """,
            (
                resident_id,
                enrollment_id,
                shelter,
                case_manager_user_id,
                started_by_user_id,
                L9_STATUS_ACTIVE,
                L9_PARTICIPATION_ENROLLED,
                start,
                end,
                start,
                apartment_exit_reason,
                now,
                now,
            ),
        )

        lifecycle_id = int(row["id"])

        for m in range(1, 7):
            due = _add_months(start, m)
            db_execute(
                f"""
                INSERT INTO level9_monthly_followups (
                    level9_lifecycle_id, resident_id, enrollment_id,
                    support_month_number, due_date, status,
                    created_at, updated_at
                ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                """,
                (
                    lifecycle_id,
                    resident_id,
                    enrollment_id,
                    m,
                    due,
                    "pending",
                    now,
                    now,
                ),
            )

    return row
