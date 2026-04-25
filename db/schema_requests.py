"""
Operational workflow schema objects.
"""

from __future__ import annotations

import contextlib
import logging

from core.db import db_execute, db_fetchall, db_fetchone

from .schema_helpers import create_table


def _sqlite_column_exists(table_name: str, column_name: str) -> bool:
    try:
        rows = db_fetchall(f"PRAGMA table_info({table_name})")
    except Exception as e:
        logging.exception("_sqlite_column_exists failed")
        raise

    for row in rows or []:
        name = row["name"] if isinstance(row, dict) else row[1]
        if str(name or "").strip().lower() == column_name.strip().lower():
            return True
    return False

# rest unchanged
