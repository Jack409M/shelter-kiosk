from __future__ import annotations

import json
from datetime import UTC, date, datetime

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder

L9_STATUS_ACTIVE = "active"
L9_STATUS_EXTENDED = "extended"
L9_STATUS_COMPLETE = "complete"

L9_PARTICIPATION_ENROLLED = "enrolled"

L9_FOLLOWUP_PENDING = "pending"
L9_FOLLOWUP_COMPLETED = "completed"

L9_INTERVIEW_PENDING = "pending"
L9_INTERVIEW_COMPLETED = "completed"
L9_INTERVIEW_DECLINED = "declined"

L9_EVENT_MONTHLY_FOLLOWUP_COMPLETED = "monthly_followup_completed"
L9_EVENT_EXTENDED = "lifecycle_extended"
L9_EVENT_COMPLETED = "lifecycle_completed"
L9_EVENT_INTERVIEW_COMPLETED = "exit_interview_completed"

INTERVIEW_EXIT = "exit"
INTERVIEW_6_MONTH = "6_month"
INTERVIEW_12_MONTH = "12_month"


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


def _create_exit_interview(
    lifecycle_id: int,
    resident_id: int,
    interview_type: str,
    target_date: str | None,
) -> None:
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM level9_exit_interviews
        WHERE level9_lifecycle_id = {ph}
          AND interview_type = {ph}
        LIMIT 1
        """,
        (lifecycle_id, interview_type),
    )
    if existing:
        return

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
            L9_INTERVIEW_PENDING,
            now,
            now,
        ),
    )


def _log_event(
    lifecycle_id: int,
    event_type: str,
    now: str,
    user_id: int | None,
    *,
    old_value: dict | None = None,
    new_value: dict | None = None,
    notes: str | None = None,
) -> None:
    ph = placeholder()

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
            lifecycle_id,
            event_type,
            now,
            user_id,
            _json_text(old_value),
            _json_text(new_value),
            notes,
            now,
        ),
    )


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
                resident_id,
                enrollment_id,
                shelter,
                case_manager_user_id,
                started_by_user_id,
                status,
                participation_status,
                start_date,
                initial_end_date,
                apartment_exit_date,
                apartment_exit_reason,
                notes,
                created_at,
                updated_at
            ) VALUES (
                {ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph}
            )
            RETURNING id
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
                (notes or "").strip() or None,
                now,
                now,
            ),
        )

        lifecycle_id = int(row["id"])

        for month_number in range(1, 7):
            due = _add_months(start, month_number)
            db_execute(
                f"""
                INSERT INTO level9_monthly_followups (
                    level9_lifecycle_id,
                    resident_id,
                    enrollment_id,
                    support_month_number,
                    due_date,
                    status,
                    created_at,
                    updated_at
                ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                """,
                (
                    lifecycle_id,
                    resident_id,
                    enrollment_id,
                    month_number,
                    due,
                    L9_FOLLOWUP_PENDING,
                    now,
                    now,
                ),
            )

        _create_exit_interview(lifecycle_id, resident_id, INTERVIEW_EXIT, start)
        _create_exit_interview(lifecycle_id, resident_id, INTERVIEW_6_MONTH, end)

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

        _log_event(
            existing.get("level9_lifecycle_id"),
            L9_EVENT_MONTHLY_FOLLOWUP_COMPLETED,
            now,
            completed_by_user_id,
            old_value={"status": existing.get("status")},
            new_value={
                "status": L9_FOLLOWUP_COMPLETED,
                "contact_result": (contact_result or "").strip() or None,
                "followup_method": (followup_method or "").strip() or None,
            },
            notes=(summary_notes or "").strip() or None,
        )

    return db_fetchone(
        f"SELECT * FROM level9_monthly_followups WHERE id = {ph} LIMIT 1",
        (followup_id,),
    )


def extend_level9_lifecycle(*, lifecycle_id: int, decided_by_user_id: int | None):
    ph = placeholder()
    now = utcnow_iso()

    lifecycle = db_fetchone(
        f"""
        SELECT *
        FROM level9_support_lifecycles
        WHERE id = {ph}
        LIMIT 1
        """,
        (lifecycle_id,),
    )
    if not lifecycle:
        return None

    current_status = str(lifecycle.get("status") or "").strip().lower()
    if current_status == L9_STATUS_COMPLETE:
        return lifecycle
    if current_status == L9_STATUS_EXTENDED:
        return lifecycle

    start = str(lifecycle.get("start_date") or "")[:10]
    extended_end = _add_months(start, 12)

    with db_transaction():
        db_execute(
            f"""
            UPDATE level9_support_lifecycles
            SET
                status = {ph},
                extended_end_date = {ph},
                extension_granted = {ph},
                extension_decided_by_user_id = {ph},
                extension_decision_date = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                L9_STATUS_EXTENDED,
                extended_end,
                1,
                decided_by_user_id,
                now[:10],
                now,
                lifecycle_id,
            ),
        )

        for month_number in range(7, 13):
            due = _add_months(start, month_number)
            db_execute(
                f"""
                INSERT INTO level9_monthly_followups (
                    level9_lifecycle_id,
                    resident_id,
                    enrollment_id,
                    support_month_number,
                    due_date,
                    status,
                    created_at,
                    updated_at
                )
                SELECT {ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph}
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM level9_monthly_followups
                    WHERE level9_lifecycle_id = {ph}
                      AND support_month_number = {ph}
                )
                """,
                (
                    lifecycle_id,
                    lifecycle["resident_id"],
                    lifecycle["enrollment_id"],
                    month_number,
                    due,
                    L9_FOLLOWUP_PENDING,
                    now,
                    now,
                    lifecycle_id,
                    month_number,
                ),
            )

        _create_exit_interview(
            lifecycle_id,
            lifecycle["resident_id"],
            INTERVIEW_12_MONTH,
            extended_end,
        )

        _log_event(
            lifecycle_id,
            L9_EVENT_EXTENDED,
            now,
            decided_by_user_id,
            old_value={
                "status": current_status,
                "extended_end_date": lifecycle.get("extended_end_date"),
            },
            new_value={
                "status": L9_STATUS_EXTENDED,
                "extended_end_date": extended_end,
            },
            notes="Level 9 lifecycle extended by case manager decision.",
        )

    return db_fetchone(
        f"SELECT * FROM level9_support_lifecycles WHERE id = {ph} LIMIT 1",
        (lifecycle_id,),
    )


def complete_level9_lifecycle(*, lifecycle_id: int, decided_by_user_id: int | None):
    ph = placeholder()
    now = utcnow_iso()

    lifecycle = db_fetchone(
        f"""
        SELECT *
        FROM level9_support_lifecycles
        WHERE id = {ph}
        LIMIT 1
        """,
        (lifecycle_id,),
    )
    if not lifecycle:
        return None

    current_status = str(lifecycle.get("status") or "").strip().lower()
    if current_status == L9_STATUS_COMPLETE:
        return lifecycle

    with db_transaction():
        db_execute(
            f"""
            UPDATE level9_support_lifecycles
            SET
                status = {ph},
                final_end_date = {ph},
                deactivation_ready = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                L9_STATUS_COMPLETE,
                now[:10],
                1,
                now,
                lifecycle_id,
            ),
        )

        _log_event(
            lifecycle_id,
            L9_EVENT_COMPLETED,
            now,
            decided_by_user_id,
            old_value={
                "status": current_status,
                "deactivation_ready": lifecycle.get("deactivation_ready"),
            },
            new_value={
                "status": L9_STATUS_COMPLETE,
                "final_end_date": now[:10],
                "deactivation_ready": True,
            },
            notes="Level 9 lifecycle completed by case manager decision.",
        )

    return db_fetchone(
        f"SELECT * FROM level9_support_lifecycles WHERE id = {ph} LIMIT 1",
        (lifecycle_id,),
    )


def complete_exit_interview(
    *,
    interview_id: int,
    completed_by_user_id: int | None,
    notes: str | None,
    declined: bool = False,
):
    ph = placeholder()
    now = utcnow_iso()

    interview = db_fetchone(
        f"""
        SELECT id, level9_lifecycle_id, status, interview_type
        FROM level9_exit_interviews
        WHERE id = {ph}
        LIMIT 1
        """,
        (interview_id,),
    )
    if not interview:
        return None

    new_status = L9_INTERVIEW_DECLINED if declined else L9_INTERVIEW_COMPLETED

    with db_transaction():
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
                new_status,
                now[:10],
                completed_by_user_id,
                1 if declined else 0,
                (notes or "").strip() or None,
                now,
                interview_id,
            ),
        )

        _log_event(
            interview.get("level9_lifecycle_id"),
            L9_EVENT_INTERVIEW_COMPLETED,
            now,
            completed_by_user_id,
            old_value={"status": interview.get("status")},
            new_value={
                "status": new_status,
                "interview_type": interview.get("interview_type"),
            },
            notes=(notes or "").strip() or None,
        )

    return db_fetchone(
        f"SELECT * FROM level9_exit_interviews WHERE id = {ph} LIMIT 1",
        (interview_id,),
    )
