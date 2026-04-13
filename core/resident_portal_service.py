from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from datetime import date as date_cls
from typing import Any, Final
from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

CHICAGO_TZ: Final[ZoneInfo] = ZoneInfo("America/Chicago")
UTC: Final[timezone] = UTC


@dataclass(frozen=True, slots=True)
class ChoreCompletionResult:
    found: bool
    already_completed: bool
    completed: bool


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _to_chicago(value: object) -> datetime | None:
    raw_value = _clean_text(value)
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None

    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    return parsed.astimezone(CHICAGO_TZ)


def _today_chicago() -> date_cls:
    return datetime.now(CHICAGO_TZ).date()


def chi_now() -> datetime:
    return datetime.now(CHICAGO_TZ)


def chi_today_str() -> str:
    return _today_chicago().isoformat()


def _status_rank(status: object) -> int:
    normalized_status = _clean_text(status).lower()
    order = {
        "approved": 0,
        "pending": 1,
        "denied": 2,
        "completed": 3,
    }
    return order.get(normalized_status, 9)


def process_pass_items(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    now_local = chi_now()
    today_local = now_local.date()

    processed_rows: list[dict[str, Any]] = []
    active_pass: dict[str, Any] | None = None

    for source_row in rows:
        row = dict(source_row)

        start_at_local = _to_chicago(row.get("start_at"))
        end_at_local = _to_chicago(row.get("end_at"))
        created_at_local = _to_chicago(row.get("created_at"))

        row["start_at_local"] = start_at_local
        row["end_at_local"] = end_at_local
        row["created_at_local"] = created_at_local

        status = _clean_text(row.get("status")).lower()
        pass_type = _clean_text(row.get("pass_type")).lower()

        is_active = False

        if status == "approved":
            if pass_type in {"pass", "overnight"}:
                if start_at_local is not None and end_at_local is not None:
                    is_active = start_at_local <= now_local <= end_at_local
            elif pass_type == "special":
                start_date_text = _clean_text(row.get("start_date"))
                end_date_text = _clean_text(row.get("end_date"))

                if start_date_text and end_date_text:
                    try:
                        start_date = date_cls.fromisoformat(start_date_text)
                        end_date = date_cls.fromisoformat(end_date_text)
                        is_active = start_date <= today_local <= end_date
                    except ValueError:
                        is_active = False

        row["is_active"] = is_active

        if is_active and active_pass is None:
            active_pass = row

        processed_rows.append(row)

    processed_rows.sort(
        key=lambda item: (
            0 if bool(item.get("is_active")) else 1,
            _status_rank(item.get("status")),
            -item["created_at_local"].timestamp()
            if isinstance(item.get("created_at_local"), datetime)
            else float("inf"),
        )
    )

    return processed_rows, active_pass


def process_notifications(
    rows: list[dict[str, Any]],
    resident_id: int,
    shelter: str,
) -> list[dict[str, Any]]:
    processed_rows: list[dict[str, Any]] = []
    unread_ids: list[int] = []

    for source_row in rows:
        row = dict(source_row)

        row["created_at_local"] = _to_chicago(row.get("created_at"))
        row["read_at_local"] = _to_chicago(row.get("read_at"))

        is_unread = not bool(row.get("is_read"))
        row["is_unread"] = is_unread

        if is_unread:
            notification_id = row.get("id")
            if notification_id is not None:
                unread_ids.append(int(notification_id))

        processed_rows.append(row)

    if unread_ids:
        db_execute(
            """
            UPDATE resident_notifications
            SET is_read = TRUE,
                read_at = %s
            WHERE resident_id = %s
              AND shelter = %s
              AND id = ANY(%s)
            """,
            (utcnow_iso(), resident_id, shelter, unread_ids),
        )

    return processed_rows


def process_transport(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processed_rows: list[dict[str, Any]] = []

    for source_row in rows:
        row = dict(source_row)
        row["needed_at_local"] = _to_chicago(row.get("needed_at"))
        row["submitted_at_local"] = _to_chicago(row.get("submitted_at"))
        processed_rows.append(row)

    return processed_rows


def get_today_chores(resident_id: int) -> list[dict[str, Any]]:
    return db_fetchall(
        """
        SELECT
            ca.id,
            ca.status,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE ca.resident_id = %s
          AND ca.assigned_date = %s
        ORDER BY ct.name
        """,
        (resident_id, chi_today_str()),
    )


def complete_chore(resident_id: int, assignment_id: str) -> ChoreCompletionResult:
    assignment_id_value = _clean_text(assignment_id)
    if not assignment_id_value:
        return ChoreCompletionResult(
            found=False,
            already_completed=False,
            completed=False,
        )

    existing_rows = db_fetchall(
        """
        SELECT status
        FROM chore_assignments
        WHERE id = %s
          AND resident_id = %s
        """,
        (assignment_id_value, resident_id),
    )

    if not existing_rows:
        return ChoreCompletionResult(
            found=False,
            already_completed=False,
            completed=False,
        )

    current_status = _clean_text(existing_rows[0].get("status")).lower()
    if current_status == "completed":
        return ChoreCompletionResult(
            found=True,
            already_completed=True,
            completed=False,
        )

    db_execute(
        """
        UPDATE chore_assignments
        SET status = 'completed',
            updated_at = %s
        WHERE id = %s
          AND resident_id = %s
        """,
        (utcnow_iso(), assignment_id_value, resident_id),
    )

    return ChoreCompletionResult(
        found=True,
        already_completed=False,
        completed=True,
    )
