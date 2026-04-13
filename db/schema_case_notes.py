from __future__ import annotations

from typing import Final

from core.db import _db_kind, db_execute, db_fetchall, db_fetchone

from .schema_helpers import create_table

_CASE_MANAGER_UPDATES_TABLE: Final[str] = "case_manager_updates"
_CASE_MANAGER_UPDATE_SUMMARY_TABLE: Final[str] = "case_manager_update_summary"
_CLIENT_SERVICES_TABLE: Final[str] = "client_services"

_CASE_MANAGER_UPDATES_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS case_manager_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL,
    staff_user_id INTEGER NOT NULL,
    meeting_date TEXT NOT NULL,
    notes TEXT,
    progress_notes TEXT,
    setbacks_or_incidents TEXT,
    action_items TEXT,
    next_appointment TEXT,
    overall_summary TEXT,
    updated_grit INTEGER,
    parenting_class_completed INTEGER,
    warrants_or_fines_paid INTEGER,
    ready_for_next_level INTEGER,
    recommended_next_level TEXT,
    blocker_reason TEXT,
    override_or_exception TEXT,
    staff_review_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
)
"""

_CASE_MANAGER_UPDATES_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS case_manager_updates (
    id SERIAL PRIMARY KEY,
    enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
    staff_user_id INTEGER NOT NULL,
    meeting_date TEXT NOT NULL,
    notes TEXT,
    progress_notes TEXT,
    setbacks_or_incidents TEXT,
    action_items TEXT,
    next_appointment TEXT,
    overall_summary TEXT,
    updated_grit INTEGER,
    parenting_class_completed INTEGER,
    warrants_or_fines_paid INTEGER,
    ready_for_next_level BOOLEAN,
    recommended_next_level TEXT,
    blocker_reason TEXT,
    override_or_exception TEXT,
    staff_review_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CASE_MANAGER_UPDATE_SUMMARY_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS case_manager_update_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_manager_update_id INTEGER NOT NULL,
    change_group TEXT NOT NULL,
    change_type TEXT,
    item_key TEXT,
    item_label TEXT,
    old_value TEXT,
    new_value TEXT,
    detail TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_manager_update_id) REFERENCES case_manager_updates(id)
)
"""

_CASE_MANAGER_UPDATE_SUMMARY_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS case_manager_update_summary (
    id SERIAL PRIMARY KEY,
    case_manager_update_id INTEGER NOT NULL REFERENCES case_manager_updates(id),
    change_group TEXT NOT NULL,
    change_type TEXT,
    item_key TEXT,
    item_label TEXT,
    old_value TEXT,
    new_value TEXT,
    detail TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
)
"""

_CLIENT_SERVICES_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS client_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL,
    case_manager_update_id INTEGER,
    service_type TEXT NOT NULL,
    service_date TEXT NOT NULL,
    quantity INTEGER,
    unit TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
    FOREIGN KEY (case_manager_update_id) REFERENCES case_manager_updates(id)
)
"""

_CLIENT_SERVICES_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS client_services (
    id SERIAL PRIMARY KEY,
    enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
    case_manager_update_id INTEGER REFERENCES case_manager_updates(id),
    service_type TEXT NOT NULL,
    service_date TEXT NOT NULL,
    quantity INTEGER,
    unit TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CASE_MANAGER_UPDATES_REQUIRED_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("next_appointment", "TEXT"),
    ("overall_summary", "TEXT"),
    ("updated_grit", "INTEGER"),
    ("parenting_class_completed", "INTEGER"),
    ("warrants_or_fines_paid", "INTEGER"),
    ("setbacks_or_incidents", "TEXT"),
    ("ready_for_next_level", "BOOLEAN"),
    ("recommended_next_level", "TEXT"),
    ("blocker_reason", "TEXT"),
    ("override_or_exception", "TEXT"),
    ("staff_review_note", "TEXT"),
)

_CASE_MANAGER_UPDATE_SUMMARY_REQUIRED_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("change_type", "TEXT"),
    ("item_key", "TEXT"),
    ("item_label", "TEXT"),
    ("old_value", "TEXT"),
    ("new_value", "TEXT"),
    ("detail", "TEXT"),
    ("sort_order", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT"),
)

_CLIENT_SERVICES_REQUIRED_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("case_manager_update_id", "INTEGER"),
    ("quantity", "INTEGER"),
    ("unit", "TEXT"),
)

_REQUIRED_INDEXES: Final[tuple[tuple[str, str], ...]] = (
    (
        "case_manager_updates_enrollment_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_updates_enrollment_idx "
        "ON case_manager_updates (enrollment_id)",
    ),
    (
        "case_manager_updates_staff_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_updates_staff_idx "
        "ON case_manager_updates (staff_user_id)",
    ),
    (
        "case_manager_updates_enrollment_meeting_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_updates_enrollment_meeting_idx "
        "ON case_manager_updates (enrollment_id, meeting_date)",
    ),
    (
        "case_manager_updates_staff_meeting_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_updates_staff_meeting_idx "
        "ON case_manager_updates (staff_user_id, meeting_date)",
    ),
    (
        "case_manager_update_summary_note_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_update_summary_note_idx "
        "ON case_manager_update_summary (case_manager_update_id)",
    ),
    (
        "case_manager_update_summary_group_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_update_summary_group_idx "
        "ON case_manager_update_summary (change_group)",
    ),
    (
        "case_manager_update_summary_note_group_idx",
        "CREATE INDEX IF NOT EXISTS case_manager_update_summary_note_group_idx "
        "ON case_manager_update_summary (case_manager_update_id, change_group, sort_order)",
    ),
    (
        "client_services_enrollment_idx",
        "CREATE INDEX IF NOT EXISTS client_services_enrollment_idx "
        "ON client_services (enrollment_id)",
    ),
    (
        "client_services_case_note_idx",
        "CREATE INDEX IF NOT EXISTS client_services_case_note_idx "
        "ON client_services (case_manager_update_id)",
    ),
    (
        "client_services_service_type_idx",
        "CREATE INDEX IF NOT EXISTS client_services_service_type_idx "
        "ON client_services (service_type)",
    ),
    (
        "client_services_service_date_idx",
        "CREATE INDEX IF NOT EXISTS client_services_service_date_idx "
        "ON client_services (service_date)",
    ),
    (
        "client_services_enrollment_date_idx",
        "CREATE INDEX IF NOT EXISTS client_services_enrollment_date_idx "
        "ON client_services (enrollment_id, service_date)",
    ),
)


def _column_exists(table_name: str, column_name: str) -> bool:
    if _db_kind() == "sqlite":
        rows = db_fetchall(f"PRAGMA table_info({table_name})")
        return any(str(row.get("name") or "") == column_name for row in rows)

    row = db_fetchone(
        """
        SELECT 1 AS present
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return row is not None


def _ensure_column(table_name: str, column_name: str, column_definition: str) -> None:
    if _column_exists(table_name, column_name):
        return

    db_execute(
        f"ALTER TABLE {table_name} "
        f"ADD COLUMN {column_name} {column_definition}"
    )


def _index_exists(index_name: str) -> bool:
    if _db_kind() == "sqlite":
        rows = db_fetchall(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND name = ?
            """,
            (index_name,),
        )
        return any(str(row.get("name") or "") == index_name for row in rows)

    row = db_fetchone(
        """
        SELECT 1 AS present
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND indexname = %s
        LIMIT 1
        """,
        (index_name,),
    )
    return row is not None


def _ensure_index(index_name: str, create_index_sql: str) -> None:
    if _index_exists(index_name):
        return

    db_execute(create_index_sql)


def _ensure_columns(
    table_name: str,
    required_columns: tuple[tuple[str, str], ...],
) -> None:
    for column_name, column_definition in required_columns:
        _ensure_column(table_name, column_name, column_definition)


def ensure_case_manager_updates_table(kind: str) -> None:
    create_table(
        kind,
        _CASE_MANAGER_UPDATES_SQLITE_SQL,
        _CASE_MANAGER_UPDATES_POSTGRES_SQL,
    )


def ensure_case_manager_update_summary_table(kind: str) -> None:
    create_table(
        kind,
        _CASE_MANAGER_UPDATE_SUMMARY_SQLITE_SQL,
        _CASE_MANAGER_UPDATE_SUMMARY_POSTGRES_SQL,
    )


def ensure_client_services_table(kind: str) -> None:
    create_table(
        kind,
        _CLIENT_SERVICES_SQLITE_SQL,
        _CLIENT_SERVICES_POSTGRES_SQL,
    )


def ensure_case_manager_updates_columns() -> None:
    _ensure_columns(
        _CASE_MANAGER_UPDATES_TABLE,
        _CASE_MANAGER_UPDATES_REQUIRED_COLUMNS,
    )


def ensure_case_manager_update_summary_columns() -> None:
    _ensure_columns(
        _CASE_MANAGER_UPDATE_SUMMARY_TABLE,
        _CASE_MANAGER_UPDATE_SUMMARY_REQUIRED_COLUMNS,
    )


def ensure_client_services_columns() -> None:
    _ensure_columns(
        _CLIENT_SERVICES_TABLE,
        _CLIENT_SERVICES_REQUIRED_COLUMNS,
    )


def ensure_case_notes_indexes() -> None:
    for index_name, create_index_sql in _REQUIRED_INDEXES:
        _ensure_index(index_name, create_index_sql)


def ensure_tables(kind: str) -> None:
    ensure_case_manager_updates_table(kind)
    ensure_case_manager_update_summary_table(kind)
    ensure_client_services_table(kind)
    ensure_case_manager_updates_columns()
    ensure_case_manager_update_summary_columns()
    ensure_client_services_columns()
    ensure_case_notes_indexes()
