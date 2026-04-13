"""
Shared helpers for schema modules.
"""

from __future__ import annotations

from flask import current_app, has_app_context

from core.db import db_execute


def create_table(kind: str, sqlite_sql: str, pg_sql: str) -> None:
    """
    Execute the SQLite or Postgres version of a CREATE TABLE statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def _is_duplicate_column_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return "duplicate column" in text or "already exists" in text or "column exists" in text


def safe_add_column(table_name: str, column_sql: str) -> bool:
    """
    Attempt to add a column to an existing table.

    Returns True when the column was added in this run and False when the
    column already existed.

    Raises the original exception for all non-duplicate-column failures so
    startup does not silently mask real schema problems.
    """
    statement = f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"

    try:
        db_execute(statement)
        if has_app_context():
            current_app.logger.info(
                "schema_upgrade_applied table=%s column=%s", table_name, column_sql
            )
        return True
    except Exception as exc:
        if _is_duplicate_column_error(exc):
            return False
        raise
