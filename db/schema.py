from __future__ import annotations

from flask import g

from core.db import db_execute
from . import schema_bootstrap
from . import schema_case
from . import schema_comms
from . import schema_core
from . import schema_forms
from . import schema_goals
from . import schema_outcomes
from . import schema_people
from . import schema_program
from . import schema_requests
from . import schema_shelter_operations
from . import schema_shelters


_SCHEMA_INITIALIZED = False


def _sql(kind: str, pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if kind == "pg" else sqlite_sql


def _safe_create_index(sql: str) -> None:
    try:
        db_execute(sql)
    except Exception:
        pass


def _ensure_staff_shelter_assignments_table(kind: str) -> None:
    db_execute(
        _sql(
            kind,
            """
            CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
                id SERIAL PRIMARY KEY,
                staff_user_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_user_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        )
    )


def _ensure_staff_shelter_assignments_indexes() -> None:
    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_user
        ON staff_shelter_assignments (staff_user_id)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_shelter
        ON staff_shelter_assignments (shelter)
        """
    )


def _ensure_audit_log_indexes() -> None:
    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS audit_log_resident_idx
        ON audit_log (entity_type, entity_id, created_at)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS audit_log_staff_idx
        ON audit_log (staff_user_id, created_at)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS audit_log_shelter_idx
        ON audit_log (shelter, created_at)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS audit_log_action_idx
        ON audit_log (action_type, created_at)
        """
    )


def _ensure_security_runtime_tables(kind: str) -> None:
    db_execute(
        _sql(
            kind,
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch DOUBLE PRECISION NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL,
                updated_at_epoch DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS security_runtime_state (
                state_type TEXT NOT NULL,
                state_key TEXT NOT NULL,
                expires_at_epoch REAL NOT NULL,
                created_at_epoch REAL NOT NULL,
                updated_at_epoch REAL NOT NULL,
                PRIMARY KEY (state_type, state_key)
            )
            """,
        )
    )

    db_execute(
        _sql(
            kind,
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch DOUBLE PRECISION NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS security_lock_history (
                state_key TEXT NOT NULL,
                created_at_epoch REAL NOT NULL
            )
            """,
        )
    )

    db_execute(
        _sql(
            kind,
            """
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id SERIAL PRIMARY KEY,
                k TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rate_limit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                k TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    )


def _ensure_security_runtime_indexes() -> None:
    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS security_runtime_state_type_exp_idx
        ON security_runtime_state (state_type, expires_at_epoch)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS security_runtime_state_key_exp_idx
        ON security_runtime_state (state_key, expires_at_epoch)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS security_lock_history_key_created_idx
        ON security_lock_history (state_key, created_at_epoch)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS rate_limit_events_k_created_idx
        ON rate_limit_events (k, created_at)
        """
    )

    _safe_create_index(
        """
        CREATE INDEX IF NOT EXISTS rate_limit_events_created_idx
        ON rate_limit_events (created_at)
        """
    )


def _ensure_foundation_tables(kind: str) -> None:
    schema_core.ensure_tables(kind)
    schema_shelters.ensure_tables(kind)
    schema_people.ensure_tables(kind)
    _ensure_staff_shelter_assignments_table(kind)
    _ensure_security_runtime_tables(kind)


def _ensure_domain_tables(kind: str) -> None:
    schema_program.ensure_tables(kind)
    schema_outcomes.ensure_tables(kind)
    schema_goals.ensure_tables(kind)
    schema_case.ensure_tables(kind)
    schema_shelter_operations.ensure_tables(kind)
    schema_forms.ensure_tables(kind)
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)


def _ensure_schema_upgrades(kind: str) -> None:
    schema_core.ensure_columns_and_security_upgrades(kind)
    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)


def _ensure_indexes(kind: str) -> None:
    schema_people.ensure_indexes()
    _ensure_staff_shelter_assignments_indexes()
    _ensure_audit_log_indexes()
    _ensure_security_runtime_indexes()
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    schema_goals.ensure_indexes()
    schema_case.ensure_indexes()
    schema_shelter_operations.ensure_indexes()
    schema_forms.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)


def init_db() -> None:
    global _SCHEMA_INITIALIZED

    if _SCHEMA_INITIALIZED:
        return

    kind = g.get("db_kind")
    if not kind:
        raise RuntimeError("Database kind is not set on flask.g")

    _ensure_foundation_tables(kind)
    _ensure_domain_tables(kind)
    _ensure_schema_upgrades(kind)
    _ensure_indexes(kind)

    schema_bootstrap.ensure_all(kind)

    _SCHEMA_INITIALIZED = True
