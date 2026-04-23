from __future__ import annotations

import json
from datetime import UTC, date, datetime

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder

L9_STATUS_ACTIVE = "active"
L9_STATUS_EXTENDED_ACTIVE = "extended_active"
L9_PARTICIPATION_ENROLLED = "enrolled"
L9_FOLLOWUP_PENDING = "pending"
L9_FOLLOWUP_COMPLETED = "completed"
L9_EVENT_MONTHLY_FOLLOWUP_COMPLETED = "monthly_followup_completed"


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


def _json_text(value: dict | None) -> str | None:
    if not value:
        return None
    return json.dumps(value, sort_keys=True)


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
                    L9_FOLLOWUP_PENDING,
                    now,
                    now,
                ),
            )

    return row


def complete_level9_followup(
    *,
    followup_id: int,
    shelter: str,
    completed_by_user_id: int | None,
    contact_result: str | None,
    followup_method: str | None,
    summary_notes: str | None,
    next_steps: str | None = None,
    housing_status: str | None = None,
    employment_status: str | None = None,
    income_status: str | None = None,
    sobriety_status: str | None = None,
    needs_assistance: bool = False,
    risk_flag: bool = False,
):
    ph = placeholder()
    existing = db_fetchone(
        f"""
        SELECT
            f.id,
            f.level9_lifecycle_id,
            f.status,
            l9.shelter
        FROM level9_monthly_followups f
        JOIN level9_support_lifecycles l9
          ON l9.id = f.level9_lifecycle_id
        WHERE f.id = {ph}
          AND LOWER(COALESCE(l9.shelter, '')) = LOWER({ph})
        LIMIT 1
        """,
        (followup_id, shelter),
    )
    if not existing:
        return None

    if str(existing.get("status") or "").strip().lower() == L9_FOLLOWUP_COMPLETED:
        return db_fetchone(
            f"SELECT * FROM level9_monthly_followups WHERE id = {ph} LIMIT 1",
            (followup_id,),
        )

    now = utcnow_iso()
    completed_date = now[:10]

    with db_transaction():
        db_execute(
            f"""
            UPDATE level9_monthly_followups
            SET
                completed_date = {ph},
                status = {ph},
                contact_result = {ph},
                followup_method = {ph},
                completed_by_user_id = {ph},
                summary_notes = {ph},
                housing_status = {ph},
                employment_status = {ph},
                income_status = {ph},
                sobriety_status = {ph},
                needs_assistance = {ph},
                risk_flag = {ph},
                next_steps = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                completed_date,
                L9_FOLLOWUP_COMPLETED,
                (contact_result or "").strip() or None,
                (followup_method or "").strip() or None,
                completed_by_user_id,
                (summary_notes or "").strip() or None,
                (housing_status or "").strip() or None,
                (employment_status or "").strip() or None,
                (income_status or "").strip() or None,
                (sobriety_status or "").strip() or None,
                1 if needs_assistance else 0,
                1 if risk_flag else 0,
                (next_steps or "").strip() or None,
                now,
                followup_id,
            ),
        )
        db_execute(
            f"""
            INSERT INTO level9_support_events (
                level9_lifecycle_id,
                event_type,
                event_date,
                performed_by_user_id,
                old_value,
                new_value,
                notes,
                created_at
            ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (
                existing.get("level9_lifecycle_id"),
                L9_EVENT_MONTHLY_FOLLOWUP_COMPLETED,
                now,
                completed_by_user_id,
                _json_text({"status": existing.get("status")}),
                _json_text(
                    {
                        "status": L9_FOLLOWUP_COMPLETED,
                        "contact_result": (contact_result or "").strip() or None,
                        "followup_method": (followup_method or "").strip() or None,
                    }
                ),
                (summary_notes or "").strip() or None,
                now,
            ),
        )

    return db_fetchone(
        f"SELECT * FROM level9_monthly_followups WHERE id = {ph} LIMIT 1",
        (followup_id,),
    )
