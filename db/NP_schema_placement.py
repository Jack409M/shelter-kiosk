from __future__ import annotations

from typing import Final

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

_HOUSING_UNITS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS housing_units (
    id SERIAL PRIMARY KEY,
    shelter TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    bedroom_count INTEGER,
    max_occupancy INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (shelter, unit_label)
)
"""

_HOUSING_UNITS_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS housing_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shelter TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    bedroom_count INTEGER,
    max_occupancy INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (shelter, unit_label)
)
"""

_RESIDENT_PLACEMENTS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS resident_placements (
    id SERIAL PRIMARY KEY,
    resident_id INTEGER NOT NULL REFERENCES residents(id),
    enrollment_id INTEGER REFERENCES program_enrollments(id),
    shelter TEXT NOT NULL,
    program_level TEXT,
    housing_unit_id INTEGER REFERENCES housing_units(id),
    placement_type TEXT NOT NULL DEFAULT 'none',
    start_date TEXT NOT NULL,
    end_date TEXT,
    change_reason TEXT,
    note TEXT,
    created_by_staff_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_RESIDENT_PLACEMENTS_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS resident_placements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id INTEGER NOT NULL,
    enrollment_id INTEGER,
    shelter TEXT NOT NULL,
    program_level TEXT,
    housing_unit_id INTEGER,
    placement_type TEXT NOT NULL DEFAULT 'none',
    start_date TEXT NOT NULL,
    end_date TEXT,
    change_reason TEXT,
    note TEXT,
    created_by_staff_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (resident_id) REFERENCES residents(id),
    FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id),
    FOREIGN KEY (housing_unit_id) REFERENCES housing_units(id)
)
"""

_REQUIRED_INDEXES: Final[tuple[str, ...]] = (
    "CREATE INDEX IF NOT EXISTS housing_units_shelter_active_idx ON housing_units (shelter, is_active)",
    "CREATE INDEX IF NOT EXISTS resident_placements_resident_active_idx ON resident_placements (resident_id, end_date)",
    "CREATE INDEX IF NOT EXISTS resident_placements_shelter_active_idx ON resident_placements (shelter, end_date)",
    "CREATE INDEX IF NOT EXISTS resident_placements_unit_active_idx ON resident_placements (housing_unit_id, end_date)",
    "CREATE INDEX IF NOT EXISTS resident_placements_enrollment_idx ON resident_placements (enrollment_id)",
)

_ABBA_UNITS: Final[tuple[str, ...]] = tuple(str(number) for number in range(1, 11))

_GRATITUDE_ONE_BEDROOM_UNITS: Final[tuple[str, ...]] = (
    "3",
    "4",
    "6",
    "7",
    "9",
    "10",
    "12",
    "20",
    "21",
    "22",
    "25",
    "27",
    "28",
    "30",
    "31",
    "33",
    "34",
    "36",
)

_GRATITUDE_TWO_BEDROOM_UNITS: Final[tuple[str, ...]] = (
    "2",
    "5",
    "8",
    "11",
    "26",
    "29",
    "32",
    "35",
)

_GRATITUDE_TOWNHOME_UNITS: Final[tuple[str, ...]] = (
    "13",
    "14",
    "15",
    "16",
    "37",
    "38",
    "39",
    "40",
)


def _sql(kind: str, pg_sql: str, sqlite_sql: str) -> str:
    if kind == "pg":
        return pg_sql
    return sqlite_sql


def _bool_value(kind: str, value: bool) -> bool | int:
    if kind == "pg":
        return value
    return 1 if value else 0


def _seed_unit(
    *,
    kind: str,
    shelter: str,
    unit_label: str,
    unit_type: str,
    bedroom_count: int | None,
    max_occupancy: int,
    notes: str | None = None,
) -> None:
    now = utcnow_iso()
    db_execute(
        """
        INSERT INTO housing_units (
            shelter,
            unit_label,
            unit_type,
            bedroom_count,
            max_occupancy,
            is_active,
            notes,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (shelter, unit_label) DO NOTHING
        """
        if kind == "pg"
        else """
        INSERT OR IGNORE INTO housing_units (
            shelter,
            unit_label,
            unit_type,
            bedroom_count,
            max_occupancy,
            is_active,
            notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shelter,
            unit_label,
            unit_type,
            bedroom_count,
            max_occupancy,
            _bool_value(kind, True),
            notes,
            now,
            now,
        ),
    )


def _seed_known_units(kind: str) -> None:
    for unit in _ABBA_UNITS:
        _seed_unit(
            kind=kind,
            shelter="abba",
            unit_label=unit,
            unit_type="apartment",
            bedroom_count=1,
            max_occupancy=1,
            notes="Seeded from existing Abba apartment list.",
        )

    for unit in _GRATITUDE_ONE_BEDROOM_UNITS:
        _seed_unit(
            kind=kind,
            shelter="gratitude",
            unit_label=unit,
            unit_type="one_bedroom",
            bedroom_count=1,
            max_occupancy=1,
            notes="Seeded from existing Gratitude House apartment list.",
        )

    for unit in _GRATITUDE_TWO_BEDROOM_UNITS:
        _seed_unit(
            kind=kind,
            shelter="gratitude",
            unit_label=unit,
            unit_type="two_bedroom",
            bedroom_count=2,
            max_occupancy=2,
            notes="Seeded from existing Gratitude House two bedroom list.",
        )

    for unit in _GRATITUDE_TOWNHOME_UNITS:
        _seed_unit(
            kind=kind,
            shelter="gratitude",
            unit_label=unit,
            unit_type="townhome",
            bedroom_count=2,
            max_occupancy=2,
            notes="Seeded from existing Gratitude House townhome list.",
        )

    _seed_unit(
        kind=kind,
        shelter="haven",
        unit_label="Dorm Bed",
        unit_type="bed",
        bedroom_count=None,
        max_occupancy=1,
        notes="Placeholder housing unit for Haven dorm style placement.",
    )


def ensure_tables(kind: str) -> None:
    db_execute(_sql(kind, _HOUSING_UNITS_POSTGRES_SQL, _HOUSING_UNITS_SQLITE_SQL))
    db_execute(_sql(kind, _RESIDENT_PLACEMENTS_POSTGRES_SQL, _RESIDENT_PLACEMENTS_SQLITE_SQL))
    _seed_known_units(kind)


def ensure_indexes() -> None:
    for sql in _REQUIRED_INDEXES:
        db_execute(sql)


def known_unit_count() -> int:
    rows = db_fetchall("SELECT id FROM housing_units")
    return len(rows or [])
