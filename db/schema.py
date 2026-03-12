from __future__ import annotations

from flask import g

from core.db import db_execute
from . import schema_bootstrap
from . import schema_case_management
from . import schema_comms
from . import schema_core
from . import schema_forms
from . import schema_goals
from . import schema_outcomes
from . import schema_people
from . import schema_program
from . import schema_requests
from . import schema_shelters


def _ensure_staff_shelter_assignments_table(kind: str) -> None:
    if kind == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
                id SERIAL PRIMARY KEY,
                staff_user_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS staff_shelter_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_user_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _ensure_staff_shelter_assignments_indexes() -> None:
    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_user
        ON staff_shelter_assignments (staff_user_id)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_staff_shelter_assignments_shelter
        ON staff_shelter_assignments (shelter)
        """
    )


def init_db() -> None:
    kind = g.get("db_kind")
    if not kind:
        raise RuntimeError("Database kind is not set on flask.g")

    # Core system tables
    schema_core.ensure_tables(kind)
    schema_shelters.ensure_tables(kind)
    schema_people.ensure_tables(kind)

    # Staff to shelter assignments
    _ensure_staff_shelter_assignments_table(kind)

    # Program participation
    schema_program.ensure_tables(kind)

    # Outcomes tracking
    schema_outcomes.ensure_tables(kind)

    # Goals and appointments
    schema_goals.ensure_tables(kind)

    # Case manager updates
    schema_case_management.ensure_tables(kind)

    # Flexible resident form storage
    schema_forms.ensure_tables(kind)

    # Existing system modules
    schema_requests.ensure_tables(kind)
    schema_comms.ensure_tables(kind)

    # Schema upgrades
    schema_core.ensure_columns_and_security_upgrades(kind)
    schema_people.ensure_columns_and_constraints(kind)
    schema_requests.ensure_columns_and_constraints(kind)

    # Indexes
    schema_people.ensure_indexes()
    _ensure_staff_shelter_assignments_indexes()
    schema_program.ensure_indexes()
    schema_outcomes.ensure_indexes()
    schema_goals.ensure_indexes()
    schema_case_management.ensure_indexes()
    schema_forms.ensure_indexes()
    schema_requests.ensure_indexes()
    schema_comms.ensure_indexes(kind)

    # Bootstrap tasks
    schema_bootstrap.ensure_all(kind)
