from __future__ import annotations

from datetime import datetime
from typing import Any

from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

CHI = ZoneInfo("America/Chicago")


# ------------------------------------------------------------
# Datetime helpers (single source of truth for portal)
# ------------------------------------------------------------

def _to_chi(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(CHI)

    return dt.astimezone(CHI)


def chi_now() -> datetime:
    return datetime.now(CHI)


def chi_today_str() -> str:
    return str(chi_now().date())


# ------------------------------------------------------------
# Pass logic
# ------------------------------------------------------------

def _status_rank(status: str) -> int:
    order = {
        "approved": 0,
        "pending": 1,
        "denied": 2,
        "completed": 3,
    }
    return order.get((status or "").strip().lower(), 9)


def process_pass_items(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    now = chi_now()
    processed: list[dict[str, Any]] = []
    active_pass = None

    for row in rows:
        row["start_at_local"] = _to_chi(row.get("start_at"))
        row["end_at_local"] = _to_chi(row.get("end_at"))
        row["created_at_local"] = _to_chi(row.get("created_at"))

        status = (row.get("status") or "").lower()
        pass_type = (row.get("pass_type") or "").lower()

        is_active = False

        if status == "approved":
            if pass_type in {"pass", "overnight"}:
                if row["start_at_local"] and row["end_at_local"]:
                    is_active = row["start_at_local"] <= now <= row["end_at_local"]

            elif pass_type == "special":
                try:
                    start = row.get("start_date")
                    end = row.get("end_date")
                    if start and end:
                        today = now.date()
                        is_active = start <= str(today) <= end
                except Exception:
                    is_active = False

        row["is_active"] = is_active

        if is_active and active_pass is None:
            active_pass = row

        processed.append(row)

    processed.sort(
        key=lambda item: (
            0 if item.get("is_active") else 1,
            _status_rank(item.get("status", "")),
            -item["created_at_local"].timestamp()
            if item.get("created_at_local")
            else float("inf"),
        )
    )

    return processed, active_pass


# ------------------------------------------------------------
# Notifications
# ------------------------------------------------------------

def process_notifications(rows: list[dict[str, Any]], resident_id: int, shelter: str) -> list[dict[str, Any]]:
    unread_ids: list[int] = []
    processed: list[dict[str, Any]] = []

    for row in rows:
        row["created_at_local"] = _to_chi(row.get("created_at"))
        row["read_at_local"] = _to_chi(row.get("read_at"))
        row["is_unread"] = not bool(row.get("is_read"))

        if row["is_unread"]:
            unread_ids.append(int(row["id"]))

        processed.append(row)

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

    return processed


# ------------------------------------------------------------
# Transport
# ------------------------------------------------------------

def process_transport(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["needed_at_local"] = _to_chi(row.get("needed_at"))
        row["submitted_at_local"] = _to_chi(row.get("submitted_at"))
    return rows


# ------------------------------------------------------------
# Chores
# ------------------------------------------------------------

def get_today_chores(resident_id: int) -> list[dict[str, Any]]:
    today = chi_today_str()

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
        (resident_id, today),
    )


def complete_chore(resident_id: int, assignment_id: str) -> bool:
    existing = db_fetchall(
        """
        SELECT status
        FROM chore_assignments
        WHERE id = %s AND resident_id = %s
        """,
        (assignment_id, resident_id),
    )

    if not existing:
        return False

    status = existing[0]["status"]

    if status == "completed":
        return False

    db_execute(
        """
        UPDATE chore_assignments
        SET status = 'completed',
            updated_at = %s
        WHERE id = %s AND resident_id = %s
        """,
        (utcnow_iso(), assignment_id, resident_id),
    )

    return True
