from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from flask import current_app, g, has_app_context

from core.db import db_execute
from routes.rent_tracking_parts import schema as rent_tracking_schema

from . import (
    NP_schema_placement,
    l9_schema_support,
    schema_admin,
    schema_bootstrap,
    schema_budget,
    schema_case,
    schema_comms,
    schema_core,
    schema_forms,
    schema_goals,
    schema_outcomes,
    schema_people,
    schema_program,
    schema_requests,
    schema_shelter_operations,
    schema_shelters,
)

_STAFF_SHELTER_ASSIGNMENTS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
    id SERIAL PRIMARY KEY,
    staff_user_id INTEGER NOT NULL,
    shelter TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_STAFF_SHELTER_ASSIGNMENTS_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_user_id INTEGER NOT NULL,
    shelter TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

_SECURITY_RUNTIME_STATE_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS security_runtime_state (
    state_type TEXT NOT NULL,
    state_key TEXT NOT NULL,
    expires_at_epoch DOUBLE PRECISION NOT NULL,
    created_at_epoch DOUBLE PRECISION NOT NULL,
    updated_at_epoch DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (state_type, state_key)
)
"""

_SECURITY_RUNTIME_STATE_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS security_runtime_state (
    state_type TEXT NOT NULL,
    state_key TEXT NOT NULL,
    expires_at_epoch REAL NOT NULL,
    created_at_epoch REAL NOT NULL,
    updated_at_epoch REAL NOT NULL,
    PRIMARY KEY (state_type, state_key)
)
"""

_SECURITY_LOCK_HISTORY_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS security_lock_history (
    state_key TEXT NOT NULL,
    created_at_epoch DOUBLE PRECISION NOT NULL
)
"""

_SECURITY_LOCK_HISTORY_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS security_lock_history (
    state_key TEXT NOT NULL,
    created_at_epoch REAL NOT NULL
)
"""

_RATE_LIMIT_EVENTS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id SERIAL PRIMARY KEY,
    k TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_RATE_LIMIT_EVENTS_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    k TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_REQUIRED_INDEXES: Final[tuple[str, ...]] = (
    """
    CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_user
    ON staff_shelter_assignments (staff_user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_shelter
    ON staff_shelter_assignments (shelter)
    """,
    """
    CREATE INDEX IF NOT EXISTS audit_log_resident_idx
    ON audit_log (entity_type, entity_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS audit_log_staff_idx
    ON audit_log (staff_user_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS audit_log_shelter_idx
    ON audit_log (shelter, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS audit_log_action_idx
    ON audit_log (action_type, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS security_runtime_state_type_exp_idx
    ON security_runtime_state (state_type, expires_at_epoch)
    """,
    """
    CREATE INDEX IF NOT EXISTS security_runtime_state_key_exp_idx
    ON security_runtime_state (state_key, expires_at_epoch)
    """,
    """
    CREATE INDEX IF NOT EXISTS security_lock_history_key_created_idx
    ON security_lock_history (state_key, created_at_epoch)
    """,
    """
    CREATE INDEX IF NOT EXISTS rate_limit_events_k_created_idx
    ON rate_limit_events (k, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS rate_limit_events_created_idx
    ON rate_limit_events (created_at)
    """,
)


@dataclass
class SchemaState:
    initialized_key: str | None = None


def _require_kind() -> str:
    kind_value = g.get("db_kind")
    if not kind_value:
        raise RuntimeError("Database kind is not set on flask.g")

    kind = str(kind_value).strip().lower()
    if kind not in {"pg", "sqlite"}:
        raise RuntimeError(f"Unsupported database kind: {kind!r}")

    return kind


def _schema_key(kind: str) -> str:
    database_url = str(current_app.config.get("DATABASE_URL") or "").strip()
    return f"{kind}:{database_url}"


def _sql(kind: str, pg_sql: str, sqlite_sql: str) -> str:
    if kind == "pg":
        return pg_sql
    return sqlite_sql


def _execute(sql: str) -> None:
    db_execute(sql)


def _safe_create_index(sql: str) -> None:
    try:
        _execute(sql)
    except Exception:
        current_app.logger.exception("Failed to create schema index.")


def _ensure_staff_shelter_assignments_table(kind: str) -> None:
    _execute(
        _sql(
            kind,
            _STAFF_SHELTER_ASSIGNMENTS_POSTGRES_SQL,
            _STAFF_SHELTER_ASSIGNMENTS_SQLITE_SQL,
        )
    )


def _ensure_security_runtime_tables(kind: str) -> None:
    _execute(
        _sql(
            kind,
            _SECURITY_RUNTIME_STATE_POSTGRES_SQL,
            _SECURITY_RUNTIME_STATE_SQLITE_SQL,
        )
    )
    _execute(
        _sql(
            kind,
            _SECURITY_LOCK_HISTORY_POSTGRES_SQL,
            _SECURITY_LOCK_HISTORY_SQLITE_SQL,
        )
    )
    _execute(
        _sql(
            kind,
            _RATE_LIMIT_EVENTS_POSTGRES_SQL,
            _RATE_LIMIT_EVENTS_SQLITE_SQL,
        )
    )


def _ensure_foundation_tables(kind: str) -> None:
    schema_core.ensure_tables(kind)
    schema_shelters.ensure_tables(kind)
    schema_people.ensure_tables(kind)
    _ensure_staff_shelter_assignments_table(kind)
    _ensure_security_runtime_tables(kind)


def _ensure_program_anchor_tables(kind: str) -> None:
    schema_program.ensure_tables(kind)


def _ensure_dependent_domain_tables(kind: str) -> None:
    schema_outcomes.ensure_tables(kind)
    l9_schema_support.ensure_tables(kind)
    schema_goals.ensure_tables(kind)
    schema_case.ensure_tables(kind)
    schema_budget.ensure_tables(kind)
    schema_shelter_operations.ensure_tables(kind)
    schema_forms.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)
    NP_schema_placement.ensure_tables(kind)
    schema_admin.ensure_tables(kind)
    rent_tracking_schema._ensure_tables()


def _ensure_schema_upgrades(kind: str) -> None:
    schema_core.ensure_columns_and_security_upgrades(kind)
    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)


def _ensure_integrity_pre_index_tasks() -> None:
    schema_outcomes.ensure_single_row_baseline_integrity()


def _ensure_shared_indexes() -> None:
    for index_sql in _REQUIRED_INDEXES:
        _safe_create_index(index_sql)


def _ensure_indexes(kind: str) -> None:
    schema_people.ensure_indexes()
    _ensure_shared_indexes()
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    l9_schema_support.ensure_indexes()
    schema_goals.ensure_indexes()
    schema_case.ensure_indexes()
    schema_budget.ensure_indexes()
    schema_shelter_operations.ensure_indexes()
    schema_forms.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)
    NP_schema_placement.ensure_indexes()
    schema_admin.ensure_indexes()


def _ensure_bootstrap_tasks(kind: str) -> None:
    schema_bootstrap.ensure_all(kind)


def _run_schema_initialization(kind: str) -> None:
    # Phase 1: foundational tables required by all later modules.
    _ensure_foundation_tables(kind)

    # Phase 2: program anchor tables that downstream domains reference.
    _ensure_program_anchor_tables(kind)

    # Phase 3: dependent domain tables that rely on prior foundations.
    _ensure_dependent_domain_tables(kind)

    # Phase 4: additive column and security upgrades.
    _ensure_schema_upgrades(kind)

    # Phase 5: data integrity preparation that must run before constraints and indexes.
    _ensure_integrity_pre_index_tasks()

    # Phase 6: indexes and uniqueness enforcement.
    _ensure_indexes(kind)

    # Phase 7: bootstrap seed and compatibility tasks.
    _ensure_bootstrap_tasks(kind)


def _schema_state() -> SchemaState:
    if not has_app_context():
        raise RuntimeError("Schema state requires an active Flask app context.")

    state = current_app.extensions.get("shelter_kiosk_schema_state")
    if isinstance(state, SchemaState):
        return state

    state = SchemaState()
    current_app.extensions["shelter_kiosk_schema_state"] = state
    return state


def init_db() -> None:
    kind = _require_kind()
    current_key = _schema_key(kind)

    state = _schema_state()
    if state.initialized_key == current_key:
        return

    _run_schema_initialization(kind)
    state.initialized_key = current_key
