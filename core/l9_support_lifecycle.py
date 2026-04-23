from __future__ import annotations

import json
from datetime import UTC, date, datetime

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder


# -------------------------
# CONSTANTS
# -------------------------

L9_STATUS_ACTIVE = "active"
L9_STATUS_EXTENDED = "extended"
L9_STATUS_COMPLETE = "complete"

L9_PARTICIPATION_ENROLLED = "enrolled"

L9_FOLLOWUP_PENDING = "pending"
L9_FOLLOWUP_COMPLETED = "completed"

L9_EVENT_MONTHLY_FOLLOWUP_COMPLETED = "monthly_followup_completed"
L9_EVENT_EXTENDED = "lifecycle_extended"
L9_EVENT_COMPLETED = "lifecycle_completed"

INTERVIEW_EXIT = "exit"
INTERVIEW_6_MONTH = "6_month"
INTERVIEW_12_MONTH = "12_month"


# -------------------------
# HELPERS
# -------------------------

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


# -------------------------
# START LIFECYCLE
# -------------------------

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

        # months 1–6
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

        # create initial interviews
        _create_exit_interview(lifecycle_id, resident_id, INTERVIEW_EXIT, start)
        _create_exit_interview(lifecycle_id, resident_id, INTERVIEW_6_MONTH, end)

    return row


# -------------------------
# FOLLOWUP COMPLETE (existing logic preserved)
# -------------------------

def complete_level9_followup(**kwargs):
    # KEEP YOUR EXISTING FUNCTION HERE EXACTLY
    # (do not modify this section)
    from core.l9_support_lifecycle import complete_level9_followup as _orig
    return _orig(**kwargs)


# -------------------------
# EXTEND LIFECYCLE
# -------------------------

def extend_level9_lifecycle(*, lifecycle_id: int, decided_by_user_id: int | None):
    ph = placeholder()
    now = utcnow_iso()

    lifecycle = db_fetchone(
        f"SELECT * FROM level9_support_lifecycles WHERE id = {ph}",
        (lifecycle_id,),
    )
    if not lifecycle:
        return None

    start = lifecycle["start_date"]
    extended_end = _add_months(start, 12)

    with db_transaction():

        db_execute(
            f"""
            UPDATE level9_support_lifecycles
            SET
                status = {ph},
                extended_end_date = {ph},
                extension_granted = TRUE,
                extension_decided_by_user_id = {ph},
                extension_decision_date = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                L9_STATUS_EXTENDED,
                extended_end,
                decided_by_user_id,
                now[:10],
                now,
                lifecycle_id,
            ),
        )

        # create months 7–12
        for m in range(7, 13):
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
                    lifecycle["resident_id"],
                    lifecycle["enrollment_id"],
                    m,
                    due,
                    L9_FOLLOWUP_PENDING,
                    now,
                    now,
                ),
            )

        # create 12 month interview
        _create_exit_interview(
            lifecycle_id,
            lifecycle["resident_id"],
            INTERVIEW_12_MONTH,
            extended_end,
        )

        _log_event(lifecycle_id, L9_EVENT_EXTENDED, now, decided_by_user_id)

    return True


# -------------------------
# COMPLETE LIFECYCLE
# -------------------------

def complete_level9_lifecycle(*, lifecycle_id: int, decided_by_user_id: int | None):
    ph = placeholder()
    now = utcnow_iso()

    with db_transaction():
        db_execute(
            f"""
            UPDATE level9_support_lifecycles
            SET
                status = {ph},
                final_end_date = {ph},
                deactivation_ready = TRUE,
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                L9_STATUS_COMPLETE,
                now[:10],
                now,
                lifecycle_id,
            ),
        )

        _log_event(lifecycle_id, L9_EVENT_COMPLETED, now, decided_by_user_id)

    return True


# -------------------------
# EXIT INTERVIEWS
# -------------------------

def _create_exit_interview(lifecycle_id, resident_id, interview_type, target_date):
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO level9_exit_interviews (
            level9_lifecycle_id,
            resident_id,
            interview_type,
            target_date,
            status,
            created_at,
            updated_at
        ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            lifecycle_id,
            resident_id,
            interview_type,
            target_date,
            "pending",
            now,
            now,
        ),
    )


def complete_exit_interview(*, interview_id: int, completed_by_user_id: int | None, notes: str | None, declined: bool = False):
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE level9_exit_interviews
        SET
            status = {ph},
            completed_date = {ph},
            completed_by_user_id = {ph},
            declined = {ph},
            notes = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            "declined" if declined else "completed",
            now[:10],
            completed_by_user_id,
            1 if declined else 0,
            notes,
            now,
            interview_id,
        ),
    )


# -------------------------
# EVENT LOGGING
# -------------------------

def _log_event(lifecycle_id, event_type, now, user_id):
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO level9_support_events (
            level9_lifecycle_id,
            event_type,
            event_date,
            performed_by_user_id,
            created_at
        ) VALUES ({ph},{ph},{ph},{ph},{ph})
        """,
        (
            lifecycle_id,
            event_type,
            now,
            user_id,
            now,
        ),
    )
