from __future__ import annotations

from core.db import db_execute


def create_table(kind: str, sqlite_sql: str, pg_sql: str) -> None:
    sql = pg_sql if kind == "pg" else sqlite_sql
    db_execute(sql)
