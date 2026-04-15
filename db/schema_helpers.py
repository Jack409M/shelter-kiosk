"""
Shared helpers for schema modules.
"""

from __future__ import annotations

from flask import current_app, has_app_context

from core.db import db_execute, db_fetchall


def create_table(kind: str, sqlite_sql: str, pg_sql: str) -> None:
    """
    Execute the SQLite or Postgres version of a CREATE TABLE statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def _log_info(message: str, *args) -> None:
    if has_app_context():
        current_app.logger.info(message, *args)


def _log_warning(message: str, *args) -> None:
    if has_app_context():
        current_app.logger.warning(message, *args)


def _is_duplicate_column_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return (
        "duplicate column" in text
        or "already exists" in text
        or "column exists" in text
        or "duplicate_column" in text
    )


def _is_transaction_aborted_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return (
        "current transaction is aborted" in text
        or "infailedsqltransaction" in text
    )


def _column_name_from_sql(column_sql: str) -> str:
    cleaned = str(column_sql).strip()
    if not cleaned:
        raise RuntimeError("column_sql must not be empty.")

    first_token = cleaned.split(None, 1)[0].strip().strip('"')
    if not first_token:
        raise RuntimeError(f"Could not determine column name from: {column_sql!r}")

    return first_token


def _sqlite_column_exists(table_name: str, column_name: str) -> bool:
    rows = db_fetchall(f"PRAGMA table_info({table_name})")
    for row in rows:
        if str(row.get("name") or "").strip().lower() == column_name.lower():
            return True
    return False


def _pg_column_exists(table_name: str, column_name: str) -> bool:
    rows = db_fetchall(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    return bool(rows)


def column_exists(kind: str, table_name: str, column_name: str) -> bool:
    """
    Return True when the target column already exists.
    """
    if kind == "pg":
        return _pg_column_exists(table_name, column_name)
    return _sqlite_column_exists(table_name, column_name)


def safe_add_column(kind: str, table_name: str, column_sql: str) -> bool:
    """
    Attempt to add a column to an existing table.

    Returns True when the column was added in this run and False when the
    column already existed.

    This helper is defensive against concurrent startup races by checking
    whether the column already exists before issuing ALTER TABLE, and for
    Postgres it uses IF NOT EXISTS as an extra guard.
    """
    column_name = _column_name_from_sql(column_sql)

    if column_exists(kind, table_name, column_name):
        _log_info(
            "schema_upgrade_skipped_existing table=%s column=%s",
            table_name,
            column_name,
        )
        return False

    if kind == "pg":
        statement = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_sql}"
    else:
        statement = f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"

    try:
        db_execute(statement)
        _log_info(
            "schema_upgrade_applied table=%s column=%s",
            table_name,
            column_sql,
        )
        return True
    except Exception as exc:
        if _is_duplicate_column_error(exc):
            _log_info(
                "schema_upgrade_skipped_duplicate table=%s column=%s",
                table_name,
                column_name,
            )
            return False

        if _is_transaction_aborted_error(exc):
            _log_warning(
                "schema_upgrade_transaction_aborted table=%s column=%s error=%s",
                table_name,
                column_name,
                type(exc).__name__,
            )
            raise

        raise
