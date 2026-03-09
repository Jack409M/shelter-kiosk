"""
Shared helpers for schema modules.
"""

from __future__ import annotations

from core.db import db_execute


def create_table(kind: str, sqlite_sql: str, pg_sql: str) -> None:
    """
    Execute the SQLite or Postgres version of a CREATE TABLE statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)
