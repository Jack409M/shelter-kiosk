from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

DEFAULT_SHELTER_CAPACITY: Final[dict[str, int]] = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
}

SHELTER_LABELS: Final[dict[str, str]] = {
    "abba": "Abba House",
    "haven": "Haven House",
    "gratitude": "Gratitude House",
}


@dataclass(slots=True)
class ShelterCapacityRow:
    shelter: str
    shelter_label: str
    capacity: int


def _shelter_key(value: object | None) -> str:
    text = str(value or "").strip().lower()
    if text.endswith(" house"):
        text = text.removesuffix(" house").strip()
    return text


def _ensure_capacity_table() -> None:
    db_execute(
        """
        CREATE TABLE IF NOT EXISTS shelter_capacity_settings (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL UNIQUE,
            capacity INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_default_capacity_rows() -> None:
    _ensure_capacity_table()
    now = utcnow_iso()
    for shelter, capacity in DEFAULT_SHELTER_CAPACITY.items():
        existing = db_fetchone(
            """
            SELECT id
            FROM shelter_capacity_settings
            WHERE LOWER(COALESCE(shelter, '')) = %s
            LIMIT 1
            """,
            (shelter,),
        )
        if existing:
            continue
        db_execute(
            """
            INSERT INTO shelter_capacity_settings (shelter, capacity, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (shelter, capacity, now, now),
        )


def load_shelter_capacities() -> dict[str, int]:
    ensure_default_capacity_rows()
    rows = db_fetchall(
        """
        SELECT shelter, capacity
        FROM shelter_capacity_settings
        """
    )
    values = dict(DEFAULT_SHELTER_CAPACITY)
    for row in rows or []:
        shelter = _shelter_key(row.get("shelter"))
        if shelter not in DEFAULT_SHELTER_CAPACITY:
            continue
        try:
            values[shelter] = max(int(row.get("capacity") or 0), 0)
        except (TypeError, ValueError):
            values[shelter] = DEFAULT_SHELTER_CAPACITY[shelter]
    return values


def load_capacity_rows() -> list[ShelterCapacityRow]:
    capacities = load_shelter_capacities()
    return [
        ShelterCapacityRow(
            shelter=shelter,
            shelter_label=SHELTER_LABELS.get(shelter, shelter.title()),
            capacity=capacities.get(shelter, DEFAULT_SHELTER_CAPACITY[shelter]),
        )
        for shelter in DEFAULT_SHELTER_CAPACITY
    ]


def save_shelter_capacities(form_data) -> None:
    ensure_default_capacity_rows()
    now = utcnow_iso()
    for shelter in DEFAULT_SHELTER_CAPACITY:
        raw_value = form_data.get(f"capacity_{shelter}", DEFAULT_SHELTER_CAPACITY[shelter])
        try:
            capacity = max(int(raw_value or 0), 0)
        except (TypeError, ValueError):
            capacity = DEFAULT_SHELTER_CAPACITY[shelter]

        db_execute(
            """
            UPDATE shelter_capacity_settings
            SET capacity = %s,
                updated_at = %s
            WHERE LOWER(COALESCE(shelter, '')) = %s
            """,
            (capacity, now, shelter),
        )
