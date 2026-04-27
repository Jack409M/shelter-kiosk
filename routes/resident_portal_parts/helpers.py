from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import g, redirect, request, session, url_for

from core.budget_registry import is_budget_expense_key, iter_budget_line_item_definitions
from core.db import db_execute, db_fetchall, db_fetchone, get_db
from core.helpers import utcnow_iso
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    LOCKED_PARENT_ACTIVITY_DEFINITIONS,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter,
)
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import CHICAGO_TZ, pass_type_label
from routes.attendance_parts.helpers import to_local

LEGACY_ACTIVITY_LABEL_TO_PARENT_ACTIVITY_KEY = {
    "rad": "program",
    "doctor appointment": "medical_health",
    "counseling": "medical_health",
    "school": "education",
    "legal obligation": "legal",
}


def _clear_resident_session() -> None:
    session.clear()


def _resident_signin_redirect():
    return redirect(url_for("resident_requests.resident_signin", next=request.path))


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _normalized_category_row(row: dict[str, Any]) -> dict[str, Any] | None:
    item = dict(row)
    label = _clean_text(item.get("activity_label"))
    if not label:
        return None

    key = _clean_text(item.get("activity_key"))
    normalized_label = label.lower()

    legacy_parent_key = LEGACY_ACTIVITY_LABEL_TO_PARENT_ACTIVITY_KEY.get(normalized_label, "")
    if legacy_parent_key:
        item["activity_key"] = legacy_parent_key
        item["activity_label"] = LOCKED_PARENT_ACTIVITY_DEFINITIONS.get(legacy_parent_key, label)
        return item

    if key in LOCKED_PARENT_ACTIVITY_DEFINITIONS:
        item["activity_label"] = LOCKED_PARENT_ACTIVITY_DEFINITIONS[key]
        return item

    for k, v in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items():
        if normalized_label == v.lower():
            item["activity_key"] = k
            item["activity_label"] = v
            return item

    return item


def _daily_log_event_time_iso(log_date_text: str) -> str | None:
    try:
        parsed_date = datetime.strptime(log_date_text, "%Y-%m-%d")
    except ValueError:
        return None

    local_dt = parsed_date.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=CHICAGO_TZ)
    utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
    return utc_dt.isoformat(timespec="seconds")


def _load_resident_program_level(resident_id: int | None) -> int:
    if resident_id is None:
        return 0

    row = db_fetchone(
        _sql(
            "SELECT program_level FROM residents WHERE id = %s LIMIT 1",
            "SELECT program_level FROM residents WHERE id = ? LIMIT 1",
        ),
        (resident_id,),
    )
    if not row:
        return 0

    return _safe_int(row.get("program_level")) or 0


def _load_daily_log_categories(shelter: str) -> list[dict[str, Any]]:
    if not shelter:
        return []

    rows = load_kiosk_activity_categories_for_shelter(shelter)
    categories: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows or []:
        item = _normalized_category_row(row)
        if not item:
            continue

        label = _clean_text(item.get("activity_label"))
        if not label or not item.get("active"):
            continue

        token = _clean_text(item.get("activity_key")).lower() or label.lower()
        if token in seen:
            continue
        seen.add(token)
        categories.append(item)

    return categories


def _load_child_options_by_parent(
    shelter: str,
    checkout_categories: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if not shelter:
        return {}

    parent_keys = {
        _clean_text(item.get("activity_key"))
        for item in checkout_categories
        if _clean_text(item.get("activity_key"))
    }

    child_options_by_parent: dict[str, list[dict[str, Any]]] = {}
    for parent_key in sorted(parent_keys):
        rows = load_active_kiosk_activity_child_options_for_shelter(shelter, parent_key)
        options: list[dict[str, Any]] = []

        for row in rows or []:
            item = dict(row)
            if _clean_text(item.get("option_label")):
                options.append(item)

        if options:
            child_options_by_parent[parent_key] = options

    return child_options_by_parent


def _daily_log_template_context(
    *,
    shelter: str,
    resident_level: int,
    checkout_categories: list[dict[str, Any]],
    child_options_by_parent: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    aa_na_child_options = child_options_by_parent.get(AA_NA_PARENT_ACTIVITY_KEY, [])
    child_option_labels_by_parent = {
        parent_key: [
            _clean_text(item.get("option_label"))
            for item in rows
            if _clean_text(item.get("option_label"))
        ]
        for parent_key, rows in child_options_by_parent.items()
    }

    return {
        "shelter": shelter,
        "resident_level": resident_level,
        "checkout_categories": checkout_categories,
        "aa_na_parent_activity_key": AA_NA_PARENT_ACTIVITY_KEY,
        "aa_na_child_options": aa_na_child_options,
        "volunteer_parent_activity_key": VOLUNTEER_PARENT_ACTIVITY_KEY,
        "child_option_labels_by_parent": child_option_labels_by_parent,
    }


def _hydrate_pass_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["pass_type_label"] = pass_type_label(item.get("pass_type"))
    item["start_at_local"] = to_local(item.get("start_at"))
    item["end_at_local"] = to_local(item.get("end_at"))
    item["created_at_local"] = to_local(item.get("created_at"))
    item["approved_at_local"] = to_local(item.get("approved_at"))
    item["is_active"] = _pass_item_is_active(item)
    return item


def _pass_item_is_active(item: dict[str, Any]) -> bool:
    if _clean_text(item.get("status")).lower() != "approved":
        return False

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]
    start_at = _clean_text(item.get("start_at"))
    end_at = _clean_text(item.get("end_at"))
    start_date = _clean_text(item.get("start_date"))
    end_date = _clean_text(item.get("end_date"))

    if start_at and end_at:
        return start_at <= now_iso <= end_at
    if start_date and end_date:
        return start_date <= today_iso <= end_date
    return False


def _load_recent_pass_items(resident_id: int | None, shelter: str) -> list[dict[str, Any]]:
    if resident_id is None or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT rp.id, rp.pass_type, rp.status, rp.start_at, rp.end_at, rp.start_date, rp.end_date,
                   rp.destination, rp.reason, rp.resident_notes, rp.staff_notes, rp.created_at, rp.approved_at,
                   rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd ON rprd.pass_id = rp.id
            WHERE rp.resident_id = %s AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
            """
            SELECT rp.id, rp.pass_type, rp.status, rp.start_at, rp.end_at, rp.start_date, rp.end_date,
                   rp.destination, rp.reason, rp.resident_notes, rp.staff_notes, rp.created_at, rp.approved_at,
                   rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd ON rprd.pass_id = rp.id
            WHERE rp.resident_id = ? AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
        ),
        (resident_id, shelter),
    )
    return [_hydrate_pass_item(row) for row in rows]


def _load_active_pass_item(resident_id: int | None, shelter: str) -> dict[str, Any] | None:
    if resident_id is None or not shelter:
        return None

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]
    rows = db_fetchall(
        _sql(
            """
            SELECT rp.id, rp.pass_type, rp.status, rp.start_at, rp.end_at, rp.start_date, rp.end_date,
                   rp.destination, rp.reason, rp.resident_notes, rp.staff_notes, rp.created_at, rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= %s AND rp.end_at >= %s)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= %s AND rp.end_date >= %s)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
            """
            SELECT rp.id, rp.pass_type, rp.status, rp.start_at, rp.end_at, rp.start_date, rp.end_date,
                   rp.destination, rp.reason, rp.resident_notes, rp.staff_notes, rp.created_at, rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= ? AND rp.end_at >= ?)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= ? AND rp.end_date >= ?)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter, now_iso, now_iso, today_iso, today_iso),
    )
    if not rows:
        return None

    return _hydrate_pass_item(rows[0])


def _load_recent_notification_items(resident_id: int | None, shelter: str) -> list[dict[str, Any]]:
    if resident_id is None or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            "SELECT id, title, message, is_read, created_at, related_pass_id, notification_type FROM resident_notifications WHERE resident_id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s)) ORDER BY created_at DESC, id DESC LIMIT 5",
            "SELECT id, title, message, is_read, created_at, related_pass_id, notification_type FROM resident_notifications WHERE resident_id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?)) ORDER BY created_at DESC, id DESC LIMIT 5",
        ),
        (resident_id, shelter),
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["created_at_local"] = to_local(item.get("created_at"))
        item["is_unread"] = str(item.get("is_read") or "0").strip() in {"0", "False", "false", ""}
        items.append(item)
    return items


def _load_recent_transport_items(resident_identifier: str, shelter: str) -> list[dict[str, Any]]:
    if not resident_identifier or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            "SELECT id, needed_at, destination, status, reason, resident_notes, submitted_at, scheduled_at, staff_notes FROM transport_requests WHERE resident_identifier = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s)) ORDER BY submitted_at DESC, id DESC LIMIT 5",
            "SELECT id, needed_at, destination, status, reason, resident_notes, submitted_at, scheduled_at, staff_notes FROM transport_requests WHERE resident_identifier = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?)) ORDER BY submitted_at DESC, id DESC LIMIT 5",
        ),
        (resident_identifier, shelter),
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["needed_at_local"] = to_local(item.get("needed_at"))
        item["submitted_at_local"] = to_local(item.get("submitted_at"))
        item["scheduled_at_local"] = to_local(item.get("scheduled_at"))
        items.append(item)
    return items


def _ensure_budget_session_active_column() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            "ALTER TABLE resident_budget_sessions ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE"
        )
        return

    columns = db_fetchall("PRAGMA table_info(resident_budget_sessions)")
    if any(str(col.get("name") or "").strip().lower() == "is_active" for col in columns):
        return

    db_execute("ALTER TABLE resident_budget_sessions ADD COLUMN is_active INTEGER DEFAULT 0")


def _load_current_budget_session(resident_id: int | None) -> dict[str, Any] | None:
    if resident_id is None:
        return None

    _ensure_budget_session_active_column()

    active_row = db_fetchone(
        _sql(
            "SELECT * FROM resident_budget_sessions WHERE resident_id = %s AND COALESCE(is_active, FALSE) = TRUE ORDER BY COALESCE(session_date, '') DESC, id DESC LIMIT 1",
            "SELECT * FROM resident_budget_sessions WHERE resident_id = ? AND COALESCE(is_active, 0) = 1 ORDER BY COALESCE(session_date, '') DESC, id DESC LIMIT 1",
        ),
        (resident_id,),
    )
    if active_row:
        return dict(active_row)

    latest_row = db_fetchone(
        _sql(
            "SELECT * FROM resident_budget_sessions WHERE resident_id = %s ORDER BY COALESCE(session_date, '') DESC, id DESC LIMIT 1",
            "SELECT * FROM resident_budget_sessions WHERE resident_id = ? ORDER BY COALESCE(session_date, '') DESC, id DESC LIMIT 1",
        ),
        (resident_id,),
    )
    return dict(latest_row) if latest_row else None


def _ensure_budget_line_items_exist(budget_id: int | None) -> None:
    if budget_id is None:
        return

    existing = db_fetchone(
        _sql(
            "SELECT id FROM resident_budget_line_items WHERE budget_session_id = %s LIMIT 1",
            "SELECT id FROM resident_budget_line_items WHERE budget_session_id = ? LIMIT 1",
        ),
        (budget_id,),
    )
    if existing:
        return

    now = utcnow_iso()
    for sort_order, item in enumerate(iter_budget_line_item_definitions(), start=1):
        db_execute(
            _sql(
                """
                INSERT INTO resident_budget_line_items (
                    budget_session_id, line_group, line_key, line_label, sort_order,
                    is_resident_visible, is_active, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                """
                INSERT INTO resident_budget_line_items (
                    budget_session_id, line_group, line_key, line_label, sort_order,
                    is_resident_visible, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            ),
            (
                budget_id,
                item["line_group"],
                item["line_key"],
                item["line_label"],
                sort_order,
                bool(item.get("is_resident_visible", True)),
                True,
                now,
                now,
            ),
        )


def _load_budget_line_items_with_status(
    budget_id: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if budget_id is None:
        return [], []

    rows = db_fetchall(
        _sql(
            """
            SELECT li.id, li.line_group, li.line_key, li.line_label, li.projected_amount, li.actual_amount, li.sort_order,
                   COALESCE(SUM(CASE WHEN COALESCE(t.is_deleted, FALSE) = FALSE THEN t.amount ELSE 0 END), 0) AS transaction_total
            FROM resident_budget_line_items li
            LEFT JOIN resident_budget_transactions t ON t.line_item_id = li.id
            WHERE li.budget_session_id = %s AND COALESCE(li.is_active, TRUE) = TRUE
            GROUP BY li.id, li.line_group, li.line_key, li.line_label, li.projected_amount, li.actual_amount, li.sort_order
            ORDER BY li.line_group ASC, li.sort_order ASC, li.id ASC
            """,
            """
            SELECT li.id, li.line_group, li.line_key, li.line_label, li.projected_amount, li.actual_amount, li.sort_order,
                   COALESCE(SUM(CASE WHEN COALESCE(t.is_deleted, 0) = 0 THEN t.amount ELSE 0 END), 0) AS transaction_total
            FROM resident_budget_line_items li
            LEFT JOIN resident_budget_transactions t ON t.line_item_id = li.id
            WHERE li.budget_session_id = ? AND COALESCE(li.is_active, 1) = 1
            GROUP BY li.id, li.line_group, li.line_key, li.line_label, li.projected_amount, li.actual_amount, li.sort_order
            ORDER BY li.line_group ASC, li.sort_order ASC, li.id ASC
            """,
        ),
        (budget_id,),
    )

    income_items: list[dict[str, Any]] = []
    expense_items: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        projected_value = float(item.get("projected_amount") or 0)
        transaction_value = float(item.get("transaction_total") or 0)
        stored_actual_value = float(item.get("actual_amount") or 0)

        if is_budget_expense_key(item.get("line_key")):
            actual_value = transaction_value
        else:
            actual_value = stored_actual_value

        remaining = projected_value - actual_value
        if projected_value <= 0:
            status = "neutral"
        elif remaining < 0:
            status = "red"
        elif projected_value > 0 and (actual_value / projected_value) >= 0.8:
            status = "yellow"
        else:
            status = "green"

        item["projected_value"] = round(projected_value, 2)
        item["actual_value"] = round(actual_value, 2)
        item["remaining"] = round(remaining, 2)
        item["status"] = status

        if str(item.get("line_group") or "").strip().lower() == "income":
            income_items.append(item)
        else:
            expense_items.append(item)

    return income_items, expense_items


def _load_recent_budget_transactions(
    budget_id: int | None, limit: int = 10
) -> list[dict[str, Any]]:
    if budget_id is None:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT t.id, t.transaction_date, t.amount, t.merchant_or_note, t.line_item_id, li.line_label,
                   t.edited_at, t.deleted_at
            FROM resident_budget_transactions t
            LEFT JOIN resident_budget_line_items li ON li.id = t.line_item_id
            WHERE t.budget_session_id = %s AND COALESCE(t.is_deleted, FALSE) = FALSE
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT %s
            """,
            """
            SELECT t.id, t.transaction_date, t.amount, t.merchant_or_note, t.line_item_id, li.line_label,
                   t.edited_at, t.deleted_at
            FROM resident_budget_transactions t
            LEFT JOIN resident_budget_line_items li ON li.id = t.line_item_id
            WHERE t.budget_session_id = ? AND COALESCE(t.is_deleted, 0) = 0
            ORDER BY t.transaction_date DESC, t.id DESC
            LIMIT ?
            """,
        ),
        (budget_id, limit),
    )
    return [dict(row) for row in rows]


def _load_budget_line_item_lookup(budget_id: int | None) -> dict[int, dict[str, Any]]:
    if budget_id is None:
        return {}

    rows = db_fetchall(
        _sql(
            "SELECT id, budget_session_id, line_group, line_key, line_label FROM resident_budget_line_items WHERE budget_session_id = %s AND COALESCE(is_active, TRUE) = TRUE",
            "SELECT id, budget_session_id, line_group, line_key, line_label FROM resident_budget_line_items WHERE budget_session_id = ? AND COALESCE(is_active, 1) = 1",
        ),
        (budget_id,),
    )
    return {int(row["id"]): dict(row) for row in rows}


def _load_resident_session_context() -> tuple[int | None, str, str]:
    resident_id_raw = session.get("resident_id")
    resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
    shelter = str(session.get("resident_shelter") or "").strip()
    resident_identifier = str(session.get("resident_identifier") or "").strip()
    return resident_id, shelter, resident_identifier


def _prepare_resident_request_context() -> tuple[int | None, str, str]:
    resident_id, shelter, resident_identifier = _load_resident_session_context()

    get_db()
    if shelter:
        run_pass_retention_cleanup_for_shelter(shelter)

    return resident_id, shelter, resident_identifier
