"""
Core schema creation and upgrades.
"""

from __future__ import annotations

from core.db import db_engine_kind
from db.schema_helpers import create_table, safe_add_column


def ensure_core_tables() -> None:
    kind = db_engine_kind()

    # -----------------------------
    # Example table creation
    # (leave your existing tables here)
    # -----------------------------
    create_table(
        kind,
        sqlite_sql="""
        CREATE TABLE IF NOT EXISTS example_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
        """,
        pg_sql="""
        CREATE TABLE IF NOT EXISTS example_table (
            id SERIAL PRIMARY KEY
        )
        """,
    )

    # -----------------------------
    # Schema upgrades
    # -----------------------------
    ensure_example_columns(kind)


def ensure_example_columns(kind: str) -> None:
    """
    Example upgrade block.

    Replace this with your real upgrade functions,
    but keep this structure.
    """

    safe_add_column(kind, "example_table", "new_column TEXT")
