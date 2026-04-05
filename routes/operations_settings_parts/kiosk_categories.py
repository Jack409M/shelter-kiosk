from __future__ import annotations

from flask import g, request

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

from .settings_store import _placeholder


def _to_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip() or str(default))
    except Exception:
        return default


def _ensure_kiosk_activity_categories_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                activity_label TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                counts_as_work_hours BOOLEAN NOT NULL DEFAULT FALSE,
                counts_as_productive_hours BOOLEAN NOT NULL DEFAULT FALSE,
                weekly_cap_hours DOUBLE PRECISION,
                requires_approved_pass BOOLEAN NOT NULL DEFAULT FALSE,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL,
                activity_label TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                counts_as_work_hours INTEGER NOT NULL DEFAULT 0,
                counts_as_productive_hours INTEGER NOT NULL DEFAULT 0,
                weekly_cap_hours REAL,
                requires_approved_pass INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    statements = [
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS activity_label TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS counts_as_work_hours INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS counts_as_productive_hours INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS weekly_cap_hours DOUBLE PRECISION",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS requires_approved_pass INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _ensure_default_kiosk_activity_categories_for_shelter(shelter: str) -> None:
    ph = _placeholder()
    count_row = db_fetchone(
        f"""
        SELECT COUNT(*) AS row_count
        FROM kiosk_activity_categories
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        """,
        (shelter,),
    )
    row_count = int((count_row or {}).get("row_count") or 0)
    if row_count > 0:
        return

    seed_map = {
        "haven house": [
            ("Employment", True, True, None, False),
            ("RAD", True, True, None, False),
            ("Job Search", False, True, None, False),
            ("AA or NA Meeting", False, True, None, False),
            ("Church", False, True, None, False),
            ("Doctor Appointment", False, True, None, False),
            ("Counseling", False, True, None, False),
            ("Step Work", False, True, 2.0, False),
            ("Sponsor Meeting", False, True, 1.0, False),
            ("Volunteer or Community Service", False, True, None, False),
            ("School", False, True, None, False),
            ("Legal Obligation", False, True, None, False),
            ("Store", False, False, None, False),
            ("Pass", False, False, None, True),
            ("Other Approved Activity", False, False, None, False),
        ],
        "gratitude house": [
            ("Employment", True, True, None, False),
            ("Job Search", False, True, None, False),
            ("AA or NA Meeting", False, True, None, False),
            ("Church", False, True, None, False),
            ("Doctor Appointment", False, True, None, False),
            ("Counseling", False, True, None, False),
            ("Step Work", False, True, 2.0, False),
            ("Sponsor Meeting", False, True, 1.0, False),
            ("Volunteer or Community Service", False, True, None, False),
            ("School", False, True, None, False),
            ("Daycare or School Drop Off", False, False, None, False),
            ("Legal Obligation", False, True, None, False),
            ("Store", False, False, None, False),
            ("Pass", False, False, None, True),
            ("Other Approved Activity", False, False, None, False),
        ],
        "abba house": [
            ("Employment", True, True, None, False),
            ("Job Search", False, True, None, False),
            ("AA or NA Meeting", False, True, None, False),
            ("Church", False, True, None, False),
            ("Doctor Appointment", False, True, None, False),
            ("Counseling", False, True, None, False),
            ("Step Work", False, True, 2.0, False),
            ("Sponsor Meeting", False, True, 1.0, False),
            ("Volunteer or Community Service", False, True, None, False),
            ("School", False, True, None, False),
            ("Daycare or School Drop Off", False, False, None, False),
            ("Legal Obligation", False, True, None, False),
            ("Store", False, False, None, False),
            ("Pass", False, False, None, True),
            ("Free Time", False, False, None, False),
            ("Other Approved Activity", False, False, None, False),
        ],
    }

    seed_rows = seed_map.get(shelter, [])
    if not seed_rows:
        return

    now = utcnow_iso()
    for sort_order, row in enumerate(seed_rows, start=1):
        label, counts_work, counts_productive, weekly_cap_hours, requires_pass = row
        db_execute(
            (
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_label,
                    active,
                    sort_order,
                    counts_as_work_hours,
                    counts_as_productive_hours,
                    weekly_cap_hours,
                    requires_approved_pass,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                if g.get("db_kind") == "pg"
                else
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_label,
                    active,
                    sort_order,
                    counts_as_work_hours,
                    counts_as_productive_hours,
                    weekly_cap_hours,
                    requires_approved_pass,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                shelter,
                label,
                True if g.get("db_kind") == "pg" else 1,
                sort_order,
                counts_work if g.get("db_kind") == "pg" else int(bool(counts_work)),
                counts_productive if g.get("db_kind") == "pg" else int(bool(counts_productive)),
                weekly_cap_hours,
                requires_pass if g.get("db_kind") == "pg" else int(bool(requires_pass)),
                None,
                now,
                now,
            ),
        )


def _load_kiosk_activity_categories_for_shelter(shelter: str) -> list[dict]:
    _ensure_kiosk_activity_categories_table()
    _ensure_default_kiosk_activity_categories_for_shelter(shelter)
    ph = _placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            shelter,
            activity_label,
            active,
            sort_order,
            counts_as_work_hours,
            counts_as_productive_hours,
            weekly_cap_hours,
            requires_approved_pass,
            notes
        FROM kiosk_activity_categories
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        ORDER BY sort_order ASC, id ASC
        """,
        (shelter,),
    )

    categories = [dict(row) for row in (rows or [])]
    blank_rows_needed = max(0, 8 - len(categories))
    for _ in range(blank_rows_needed):
        categories.append(
            {
                "id": "",
                "activity_label": "",
                "active": True,
                "sort_order": "",
                "counts_as_work_hours": False,
                "counts_as_productive_hours": False,
                "weekly_cap_hours": "",
                "requires_approved_pass": False,
                "notes": "",
            }
        )

    return categories


def _save_kiosk_activity_categories_for_shelter(shelter: str) -> None:
    _ensure_kiosk_activity_categories_table()
    ph = _placeholder()
    now = utcnow_iso()

    row_ids = request.form.getlist("category_id[]")
    labels = request.form.getlist("activity_label[]")
    active_values = request.form.getlist("active[]")
    sort_orders = request.form.getlist("sort_order[]")
    work_values = request.form.getlist("counts_as_work_hours[]")
    productive_values = request.form.getlist("counts_as_productive_hours[]")
    cap_values = request.form.getlist("weekly_cap_hours[]")
    pass_values = request.form.getlist("requires_approved_pass[]")
    notes_values = request.form.getlist("category_notes[]")
    remove_values = request.form.getlist("remove_category[]")

    active_indexes = {int(value) for value in active_values if str(value).isdigit()}
    work_indexes = {int(value) for value in work_values if str(value).isdigit()}
    productive_indexes = {int(value) for value in productive_values if str(value).isdigit()}
    pass_indexes = {int(value) for value in pass_values if str(value).isdigit()}
    remove_indexes = {int(value) for value in remove_values if str(value).isdigit()}

    keep_ids: list[int] = []

    total_rows = max(
        len(row_ids),
        len(labels),
        len(sort_orders),
        len(cap_values),
        len(notes_values),
    )

    for idx in range(total_rows):
        raw_id = row_ids[idx].strip() if idx < len(row_ids) and row_ids[idx] else ""
        label = labels[idx].strip() if idx < len(labels) and labels[idx] else ""
        sort_order = _to_int(sort_orders[idx] if idx < len(sort_orders) else "", idx + 1)
        weekly_cap_raw = cap_values[idx].strip() if idx < len(cap_values) and cap_values[idx] else ""
        notes = notes_values[idx].strip() if idx < len(notes_values) and notes_values[idx] else ""
        is_active = idx in active_indexes
        counts_work = idx in work_indexes
        counts_productive = idx in productive_indexes
        requires_pass = idx in pass_indexes
        remove_row = idx in remove_indexes

        weekly_cap_hours = None
        if weekly_cap_raw != "":
            try:
                weekly_cap_hours = float(weekly_cap_raw)
            except Exception:
                weekly_cap_hours = None

        if remove_row or not label:
            continue

        if raw_id.isdigit():
            category_id = int(raw_id)
            keep_ids.append(category_id)
            db_execute(
                (
                    """
                    UPDATE kiosk_activity_categories
                    SET activity_label = %s,
                        active = %s,
                        sort_order = %s,
                        counts_as_work_hours = %s,
                        counts_as_productive_hours = %s,
                        weekly_cap_hours = %s,
                        requires_approved_pass = %s,
                        notes = %s,
                        updated_at = %s
                    WHERE id = %s
                      AND LOWER(COALESCE(shelter, '')) = %s
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    UPDATE kiosk_activity_categories
                    SET activity_label = ?,
                        active = ?,
                        sort_order = ?,
                        counts_as_work_hours = ?,
                        counts_as_productive_hours = ?,
                        weekly_cap_hours = ?,
                        requires_approved_pass = ?,
                        notes = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND LOWER(COALESCE(shelter, '')) = ?
                    """
                ),
                (
                    label,
                    is_active if g.get("db_kind") == "pg" else int(is_active),
                    sort_order,
                    counts_work if g.get("db_kind") == "pg" else int(counts_work),
                    counts_productive if g.get("db_kind") == "pg" else int(counts_productive),
                    weekly_cap_hours,
                    requires_pass if g.get("db_kind") == "pg" else int(requires_pass),
                    notes or None,
                    now,
                    category_id,
                    shelter,
                ),
            )
            continue

        inserted = db_fetchone(
            (
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_label,
                    active,
                    sort_order,
                    counts_as_work_hours,
                    counts_as_productive_hours,
                    weekly_cap_hours,
                    requires_approved_pass,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
                if g.get("db_kind") == "pg"
                else
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_label,
                    active,
                    sort_order,
                    counts_as_work_hours,
                    counts_as_productive_hours,
                    weekly_cap_hours,
                    requires_approved_pass,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """
            ),
            (
                shelter,
                label,
                is_active if g.get("db_kind") == "pg" else int(is_active),
                sort_order,
                counts_work if g.get("db_kind") == "pg" else int(counts_work),
                counts_productive if g.get("db_kind") == "pg" else int(counts_productive),
                weekly_cap_hours,
                requires_pass if g.get("db_kind") == "pg" else int(requires_pass),
                notes or None,
                now,
                now,
            ),
        )
        if inserted and inserted.get("id"):
            keep_ids.append(int(inserted["id"]))

    if keep_ids:
        keep_placeholders = ",".join([ph] * len(keep_ids))
        db_execute(
            f"""
            DELETE FROM kiosk_activity_categories
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND id NOT IN ({keep_placeholders})
            """,
            tuple([shelter] + keep_ids),
        )
    else:
        db_execute(
            f"""
            DELETE FROM kiosk_activity_categories
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
            """,
            (shelter,),
        )
