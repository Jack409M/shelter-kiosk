from __future__ import annotations

import contextlib

from flask import g, request

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

from .kiosk_activity_category_defaults import KIOSK_ACTIVITY_CATEGORY_SEEDS

AA_NA_PARENT_ACTIVITY_KEY = "aa_na_meeting"
AA_NA_PARENT_ACTIVITY_LABEL = "AA or NA Meeting"

VOLUNTEER_PARENT_ACTIVITY_KEY = "volunteer_community_service"
VOLUNTEER_PARENT_ACTIVITY_LABEL = "Volunteer or Community Service"

MEDICAL_HEALTH_PARENT_ACTIVITY_KEY = "medical_health"
MEDICAL_HEALTH_PARENT_ACTIVITY_LABEL = "Medical or Health"

LEGAL_PARENT_ACTIVITY_KEY = "legal"
LEGAL_PARENT_ACTIVITY_LABEL = "Legal"

PROGRAM_PARENT_ACTIVITY_KEY = "program"
PROGRAM_PARENT_ACTIVITY_LABEL = "Program"

JOB_SEARCH_PARENT_ACTIVITY_KEY = "job_search"
JOB_SEARCH_PARENT_ACTIVITY_LABEL = "Job Search"

SOCIAL_SERVICES_PARENT_ACTIVITY_KEY = "social_services"
SOCIAL_SERVICES_PARENT_ACTIVITY_LABEL = "Social Services"

EDUCATION_PARENT_ACTIVITY_KEY = "education"
EDUCATION_PARENT_ACTIVITY_LABEL = "Education"

AA_NA_MEETING_OPTION_SEEDS = [
    "Touch of Soul",
    "Clean Air",
    "12 Steps",
    "Moss",
    "Hobbs",
    "Serenity",
    "Nothing to Fear",
    "No Matter What",
    "Top of Texas",
    "DWC House Meting",
    "Online",
    "Other",
    "None",
]

VOLUNTEER_COMMUNITY_SERVICE_OPTION_SEEDS = [
    "Thrift City",
    "Thrift City Too",
    "Office",
    "Gratitude House",
    "Food Bank",
    "Other",
    "None",
]

LOCKED_PARENT_ACTIVITY_DEFINITIONS = {
    AA_NA_PARENT_ACTIVITY_KEY: AA_NA_PARENT_ACTIVITY_LABEL,
    VOLUNTEER_PARENT_ACTIVITY_KEY: VOLUNTEER_PARENT_ACTIVITY_LABEL,
    MEDICAL_HEALTH_PARENT_ACTIVITY_KEY: MEDICAL_HEALTH_PARENT_ACTIVITY_LABEL,
    LEGAL_PARENT_ACTIVITY_KEY: LEGAL_PARENT_ACTIVITY_LABEL,
    PROGRAM_PARENT_ACTIVITY_KEY: PROGRAM_PARENT_ACTIVITY_LABEL,
    JOB_SEARCH_PARENT_ACTIVITY_KEY: JOB_SEARCH_PARENT_ACTIVITY_LABEL,
    SOCIAL_SERVICES_PARENT_ACTIVITY_KEY: SOCIAL_SERVICES_PARENT_ACTIVITY_LABEL,
    EDUCATION_PARENT_ACTIVITY_KEY: EDUCATION_PARENT_ACTIVITY_LABEL,
}

NORMALIZED_LOCKED_PARENT_LABEL_TO_KEY = {
    label.strip().lower(): key for key, label in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items()
}


def _normalized_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _child_option_seeds_for_parent(parent_activity_key: str) -> list[str]:
    if parent_activity_key == AA_NA_PARENT_ACTIVITY_KEY:
        return AA_NA_MEETING_OPTION_SEEDS

    if parent_activity_key == VOLUNTEER_PARENT_ACTIVITY_KEY:
        return VOLUNTEER_COMMUNITY_SERVICE_OPTION_SEEDS

    return []


def _canonical_activity_key_for_label(activity_label: str | None) -> str:
    label = _normalized_text(activity_label)
    return NORMALIZED_LOCKED_PARENT_LABEL_TO_KEY.get(label, "")


def _locked_parent_label_for_key(activity_key: str | None) -> str:
    return LOCKED_PARENT_ACTIVITY_DEFINITIONS.get((activity_key or "").strip(), "")


def _resolve_parent_definition(parent_activity_key_or_label: str | None) -> tuple[str, str]:
    raw_value = (parent_activity_key_or_label or "").strip()

    if not raw_value:
        return AA_NA_PARENT_ACTIVITY_KEY, AA_NA_PARENT_ACTIVITY_LABEL

    if raw_value in LOCKED_PARENT_ACTIVITY_DEFINITIONS:
        return raw_value, LOCKED_PARENT_ACTIVITY_DEFINITIONS[raw_value]

    inferred_key = _canonical_activity_key_for_label(raw_value)
    if inferred_key:
        return inferred_key, LOCKED_PARENT_ACTIVITY_DEFINITIONS[inferred_key]

    return "", raw_value


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _to_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip() or str(default))
    except Exception:
        return default


def _existing_activity_key_for_category_id(category_id: int, shelter: str) -> str:
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT activity_key, activity_label
        FROM kiosk_activity_categories
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        """,
        (category_id, shelter),
    )
    if not row:
        return ""

    existing_key = (row.get("activity_key") or "").strip()
    if existing_key:
        return existing_key

    return _canonical_activity_key_for_label(row.get("activity_label"))


def ensure_kiosk_activity_categories_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                activity_key TEXT,
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
                activity_key TEXT,
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
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS activity_key TEXT",
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
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_kiosk_activity_child_options_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS kiosk_activity_child_options (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                parent_activity_key TEXT,
                parent_activity_label TEXT NOT NULL,
                option_label TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS kiosk_activity_child_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL,
                parent_activity_key TEXT,
                parent_activity_label TEXT NOT NULL,
                option_label TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    statements = [
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS parent_activity_key TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS parent_activity_label TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS option_label TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]
    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def _backfill_locked_activity_keys_for_shelter(shelter: str) -> None:
    ensure_kiosk_activity_categories_table()
    now = utcnow_iso()
    ph = _placeholder()

    for activity_key, activity_label in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items():
        db_execute(
            f"""
            UPDATE kiosk_activity_categories
            SET activity_key = {ph},
                updated_at = {ph}
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(activity_label, '')) = {ph}
              AND COALESCE(activity_key, '') = ''
            """,
            (
                activity_key,
                now,
                shelter,
                activity_label.lower(),
            ),
        )


def _backfill_locked_parent_keys_for_shelter(shelter: str) -> None:
    ensure_kiosk_activity_child_options_table()
    now = utcnow_iso()
    ph = _placeholder()

    for parent_activity_key, parent_activity_label in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items():
        db_execute(
            f"""
            UPDATE kiosk_activity_child_options
            SET parent_activity_key = {ph},
                parent_activity_label = {ph},
                updated_at = {ph}
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
              AND COALESCE(parent_activity_key, '') = ''
            """,
            (
                parent_activity_key,
                parent_activity_label,
                now,
                shelter,
                parent_activity_label.lower(),
            ),
        )


def _insert_seed_rows_for_shelter(shelter: str) -> None:
    seed_rows = KIOSK_ACTIVITY_CATEGORY_SEEDS.get(shelter, [])
    if not seed_rows:
        return

    now = utcnow_iso()
    is_pg = g.get("db_kind") == "pg"

    for sort_order, row in enumerate(seed_rows, start=1):
        label, counts_work, counts_productive, weekly_cap_hours, requires_pass = row
        activity_key = _canonical_activity_key_for_label(label) or None

        db_execute(
            (
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_key,
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                if is_pg
                else """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_key,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                shelter,
                activity_key,
                label,
                True if is_pg else 1,
                sort_order,
                counts_work if is_pg else int(bool(counts_work)),
                counts_productive if is_pg else int(bool(counts_productive)),
                weekly_cap_hours,
                requires_pass if is_pg else int(bool(requires_pass)),
                None,
                now,
                now,
            ),
        )


def _insert_child_seed_rows_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> None:
    now = utcnow_iso()
    is_pg = g.get("db_kind") == "pg"
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )
    seed_rows = _child_option_seeds_for_parent(parent_activity_key)

    for sort_order, option_label in enumerate(seed_rows, start=1):
        db_execute(
            (
                """
                INSERT INTO kiosk_activity_child_options (
                    shelter,
                    parent_activity_key,
                    parent_activity_label,
                    option_label,
                    active,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                if is_pg
                else """
                INSERT INTO kiosk_activity_child_options (
                    shelter,
                    parent_activity_key,
                    parent_activity_label,
                    option_label,
                    active,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                shelter,
                parent_activity_key or None,
                parent_activity_label,
                option_label,
                True if is_pg else 1,
                sort_order,
                now,
                now,
            ),
        )


def ensure_default_kiosk_activity_categories_for_shelter(shelter: str) -> None:
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
        _backfill_locked_activity_keys_for_shelter(shelter)
        return

    _insert_seed_rows_for_shelter(shelter)


def ensure_default_kiosk_activity_child_options_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> None:
    ensure_kiosk_activity_child_options_table()
    _backfill_locked_parent_keys_for_shelter(shelter)

    ph = _placeholder()
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )

    if parent_activity_key:
        count_row = db_fetchone(
            f"""
            SELECT COUNT(*) AS row_count
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND (
                    LOWER(COALESCE(parent_activity_key, '')) = {ph}
                 OR LOWER(COALESCE(parent_activity_label, '')) = {ph}
              )
            """,
            (shelter, parent_activity_key.lower(), parent_activity_label.lower()),
        )
    else:
        count_row = db_fetchone(
            f"""
            SELECT COUNT(*) AS row_count
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
            """,
            (shelter, parent_activity_label.lower()),
        )

    row_count = int((count_row or {}).get("row_count") or 0)
    if row_count > 0:
        return

    _insert_child_seed_rows_for_shelter(shelter, parent_activity_key or parent_activity_label)


def reset_kiosk_activity_categories_for_shelter(shelter: str) -> None:
    ensure_kiosk_activity_categories_table()
    ph = _placeholder()

    db_execute(
        f"""
        DELETE FROM kiosk_activity_categories
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        """,
        (shelter,),
    )

    _insert_seed_rows_for_shelter(shelter)


def reset_kiosk_activity_child_options_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> None:
    ensure_kiosk_activity_child_options_table()
    ph = _placeholder()
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )

    if parent_activity_key:
        db_execute(
            f"""
            DELETE FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND (
                    LOWER(COALESCE(parent_activity_key, '')) = {ph}
                 OR LOWER(COALESCE(parent_activity_label, '')) = {ph}
              )
            """,
            (shelter, parent_activity_key.lower(), parent_activity_label.lower()),
        )
    else:
        db_execute(
            f"""
            DELETE FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
            """,
            (shelter, parent_activity_label.lower()),
        )

    _insert_child_seed_rows_for_shelter(shelter, parent_activity_key or parent_activity_label)


def load_kiosk_activity_categories_for_shelter(shelter: str) -> list[dict]:
    ensure_kiosk_activity_categories_table()
    ensure_default_kiosk_activity_categories_for_shelter(shelter)
    ph = _placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            shelter,
            activity_key,
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
                "activity_key": "",
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


def load_kiosk_activity_child_options_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> list[dict]:
    ensure_kiosk_activity_child_options_table()
    ensure_default_kiosk_activity_child_options_for_shelter(shelter, parent_activity_key_or_label)
    ph = _placeholder()
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )

    if parent_activity_key:
        rows = db_fetchall(
            f"""
            SELECT
                id,
                shelter,
                parent_activity_key,
                parent_activity_label,
                option_label,
                active,
                sort_order
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND (
                    LOWER(COALESCE(parent_activity_key, '')) = {ph}
                 OR LOWER(COALESCE(parent_activity_label, '')) = {ph}
              )
            ORDER BY sort_order ASC, id ASC
            """,
            (shelter, parent_activity_key.lower(), parent_activity_label.lower()),
        )
    else:
        rows = db_fetchall(
            f"""
            SELECT
                id,
                shelter,
                parent_activity_key,
                parent_activity_label,
                option_label,
                active,
                sort_order
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
            ORDER BY sort_order ASC, id ASC
            """,
            (shelter, parent_activity_label.lower()),
        )

    options = [dict(row) for row in (rows or [])]
    blank_rows_needed = max(0, 8 - len(options))
    for _ in range(blank_rows_needed):
        options.append(
            {
                "id": "",
                "parent_activity_key": parent_activity_key,
                "parent_activity_label": parent_activity_label,
                "option_label": "",
                "active": True,
                "sort_order": "",
            }
        )

    return options


def load_active_kiosk_activity_child_options_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> list[dict]:
    ensure_kiosk_activity_child_options_table()
    ensure_default_kiosk_activity_child_options_for_shelter(shelter, parent_activity_key_or_label)
    ph = _placeholder()
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )
    active_value = True if g.get("db_kind") == "pg" else 1

    if parent_activity_key:
        rows = db_fetchall(
            f"""
            SELECT
                id,
                shelter,
                parent_activity_key,
                parent_activity_label,
                option_label,
                active,
                sort_order
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND (
                    LOWER(COALESCE(parent_activity_key, '')) = {ph}
                 OR LOWER(COALESCE(parent_activity_label, '')) = {ph}
              )
              AND active = {ph}
            ORDER BY sort_order ASC, id ASC
            """,
            (
                shelter,
                parent_activity_key.lower(),
                parent_activity_label.lower(),
                active_value,
            ),
        )
    else:
        rows = db_fetchall(
            f"""
            SELECT
                id,
                shelter,
                parent_activity_key,
                parent_activity_label,
                option_label,
                active,
                sort_order
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
              AND active = {ph}
            ORDER BY sort_order ASC, id ASC
            """,
            (
                shelter,
                parent_activity_label.lower(),
                active_value,
            ),
        )

    return [dict(row) for row in (rows or [])]


def save_kiosk_activity_categories_for_shelter(shelter: str) -> None:
    ensure_kiosk_activity_categories_table()
    ph = _placeholder()
    now = utcnow_iso()
    is_pg = g.get("db_kind") == "pg"

    row_ids = request.form.getlist("category_id[]")
    row_keys = request.form.getlist("activity_key[]")
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
        len(row_keys),
        len(labels),
        len(sort_orders),
        len(cap_values),
        len(notes_values),
    )

    for idx in range(total_rows):
        raw_id = row_ids[idx].strip() if idx < len(row_ids) and row_ids[idx] else ""
        posted_key = row_keys[idx].strip() if idx < len(row_keys) and row_keys[idx] else ""
        label = labels[idx].strip() if idx < len(labels) and labels[idx] else ""
        sort_order = _to_int(sort_orders[idx] if idx < len(sort_orders) else "", idx + 1)
        weekly_cap_raw = (
            cap_values[idx].strip() if idx < len(cap_values) and cap_values[idx] else ""
        )
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
            existing_key = _existing_activity_key_for_category_id(category_id, shelter)
            activity_key = (
                existing_key or posted_key or _canonical_activity_key_for_label(label) or None
            )

            keep_ids.append(category_id)
            db_execute(
                (
                    """
                    UPDATE kiosk_activity_categories
                    SET activity_key = %s,
                        activity_label = %s,
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
                    if is_pg
                    else """
                    UPDATE kiosk_activity_categories
                    SET activity_key = ?,
                        activity_label = ?,
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
                    activity_key,
                    label,
                    is_active if is_pg else int(is_active),
                    sort_order,
                    counts_work if is_pg else int(counts_work),
                    counts_productive if is_pg else int(counts_productive),
                    weekly_cap_hours,
                    requires_pass if is_pg else int(bool(requires_pass)),
                    notes or None,
                    now,
                    category_id,
                    shelter,
                ),
            )
            continue

        activity_key = posted_key or _canonical_activity_key_for_label(label) or None

        inserted = db_fetchone(
            (
                """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_key,
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
                if is_pg
                else """
                INSERT INTO kiosk_activity_categories (
                    shelter,
                    activity_key,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """
            ),
            (
                shelter,
                activity_key,
                label,
                is_active if is_pg else int(is_active),
                sort_order,
                counts_work if is_pg else int(counts_work),
                counts_productive if is_pg else int(counts_productive),
                weekly_cap_hours,
                requires_pass if is_pg else int(bool(requires_pass)),
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


def save_kiosk_activity_child_options_for_shelter(
    shelter: str,
    parent_activity_key_or_label: str = AA_NA_PARENT_ACTIVITY_KEY,
) -> None:
    ensure_kiosk_activity_child_options_table()
    ph = _placeholder()
    now = utcnow_iso()
    is_pg = g.get("db_kind") == "pg"
    parent_activity_key, parent_activity_label = _resolve_parent_definition(
        parent_activity_key_or_label
    )

    row_ids = request.form.getlist("child_option_id[]")
    option_labels = request.form.getlist("child_option_label[]")
    active_values = request.form.getlist("child_option_active[]")
    sort_orders = request.form.getlist("child_option_sort_order[]")
    remove_values = request.form.getlist("remove_child_option[]")

    active_indexes = {int(value) for value in active_values if str(value).isdigit()}
    remove_indexes = {int(value) for value in remove_values if str(value).isdigit()}

    keep_ids: list[int] = []

    total_rows = max(
        len(row_ids),
        len(option_labels),
        len(sort_orders),
    )

    for idx in range(total_rows):
        raw_id = row_ids[idx].strip() if idx < len(row_ids) and row_ids[idx] else ""
        option_label = (
            option_labels[idx].strip() if idx < len(option_labels) and option_labels[idx] else ""
        )
        sort_order = _to_int(sort_orders[idx] if idx < len(sort_orders) else "", idx + 1)
        is_active = idx in active_indexes
        remove_row = idx in remove_indexes

        if remove_row or not option_label:
            continue

        if raw_id.isdigit():
            option_id = int(raw_id)
            keep_ids.append(option_id)
            db_execute(
                (
                    """
                    UPDATE kiosk_activity_child_options
                    SET parent_activity_key = %s,
                        parent_activity_label = %s,
                        option_label = %s,
                        active = %s,
                        sort_order = %s,
                        updated_at = %s
                    WHERE id = %s
                      AND LOWER(COALESCE(shelter, '')) = %s
                    """
                    if is_pg
                    else """
                    UPDATE kiosk_activity_child_options
                    SET parent_activity_key = ?,
                        parent_activity_label = ?,
                        option_label = ?,
                        active = ?,
                        sort_order = ?,
                        updated_at = ?
                    WHERE id = ?
                      AND LOWER(COALESCE(shelter, '')) = ?
                    """
                ),
                (
                    parent_activity_key or None,
                    parent_activity_label,
                    option_label,
                    is_active if is_pg else int(is_active),
                    sort_order,
                    now,
                    option_id,
                    shelter,
                ),
            )
            continue

        inserted = db_fetchone(
            (
                """
                INSERT INTO kiosk_activity_child_options (
                    shelter,
                    parent_activity_key,
                    parent_activity_label,
                    option_label,
                    active,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
                if is_pg
                else """
                INSERT INTO kiosk_activity_child_options (
                    shelter,
                    parent_activity_key,
                    parent_activity_label,
                    option_label,
                    active,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """
            ),
            (
                shelter,
                parent_activity_key or None,
                parent_activity_label,
                option_label,
                is_active if is_pg else int(is_active),
                sort_order,
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
            DELETE FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND id NOT IN ({keep_placeholders})
            """,
            tuple([shelter] + keep_ids),
        )
    else:
        if parent_activity_key:
            db_execute(
                f"""
                DELETE FROM kiosk_activity_child_options
                WHERE LOWER(COALESCE(shelter, '')) = {ph}
                  AND (
                        LOWER(COALESCE(parent_activity_key, '')) = {ph}
                     OR LOWER(COALESCE(parent_activity_label, '')) = {ph}
                  )
                """,
                (shelter, parent_activity_key.lower(), parent_activity_label.lower()),
            )
        else:
            db_execute(
                f"""
                DELETE FROM kiosk_activity_child_options
                WHERE LOWER(COALESCE(shelter, '')) = {ph}
                  AND LOWER(COALESCE(parent_activity_label, '')) = {ph}
                """,
                (shelter, parent_activity_label.lower()),
            )
