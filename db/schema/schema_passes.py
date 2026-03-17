from __future__ import annotations

from core.db import db_execute


def ensure_tables(kind: str) -> None:
    _ensure_resident_passes_table(kind)


def _ensure_resident_passes_table(kind: str) -> None:
    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_passes (
                id SERIAL PRIMARY KEY,

                resident_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,

                pass_type TEXT NOT NULL,
                status TEXT NOT NULL,

                start_at TIMESTAMP,
                end_at TIMESTAMP,

                start_date DATE,
                end_date DATE,

                destination TEXT,
                reason TEXT,

                resident_notes TEXT,
                staff_notes TEXT,

                approved_by INTEGER,
                approved_at TIMESTAMP,

                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                resident_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,

                pass_type TEXT NOT NULL,
                status TEXT NOT NULL,

                start_at TEXT,
                end_at TEXT,

                start_date TEXT,
                end_date TEXT,

                destination TEXT,
                reason TEXT,

                resident_notes TEXT,
                staff_notes TEXT,

                approved_by INTEGER,
                approved_at TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
