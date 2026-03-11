"""
Outcomes schema.

This module stores program intake, family impact, exit, and follow up
records tied to a program enrollment.
"""

from __future__ import annotations

from .schema_helpers import create_table


def ensure_intake_assessments_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS intake_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            city TEXT,
            last_zipcode_residence TEXT,
            income_at_entry REAL,
            education_at_entry TEXT,
            sobriety_date TEXT,
            days_sober_at_entry INTEGER,
            drug_of_choice TEXT,
            ace_score INTEGER,
            grit_score INTEGER,
            veteran INTEGER NOT NULL DEFAULT 0,
            disability INTEGER NOT NULL DEFAULT 0,
            marital_status TEXT,
            place_staying_before_entry TEXT,
            entry_felony_conviction INTEGER NOT NULL DEFAULT 0,
            entry_parole_probation INTEGER NOT NULL DEFAULT 0,
            drug_court INTEGER NOT NULL DEFAULT 0,
            sexual_survivor INTEGER NOT NULL DEFAULT 0,
            dv_survivor INTEGER NOT NULL DEFAULT 0,
            human_trafficking_survivor INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS intake_assessments (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            city TEXT,
            last_zipcode_residence TEXT,
            income_at_entry DOUBLE PRECISION,
            education_at_entry TEXT,
            sobriety_date TEXT,
            days_sober_at_entry INTEGER,
            drug_of_choice TEXT,
            ace_score INTEGER,
            grit_score INTEGER,
            veteran INTEGER NOT NULL DEFAULT 0,
            disability INTEGER NOT NULL DEFAULT 0,
            marital_status TEXT,
            place_staying_before_entry TEXT,
            entry_felony_conviction INTEGER NOT NULL DEFAULT 0,
            entry_parole_probation INTEGER NOT NULL DEFAULT 0,
            drug_court INTEGER NOT NULL DEFAULT 0,
            sexual_survivor INTEGER NOT NULL DEFAULT 0,
            dv_survivor INTEGER NOT NULL DEFAULT 0,
            human_trafficking_survivor INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_family_snapshots_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS family_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            kids_at_dwc INTEGER NOT NULL DEFAULT 0,
            kids_served_outside_under_18 INTEGER NOT NULL DEFAULT 0,
            kids_ages_0_5 INTEGER NOT NULL DEFAULT 0,
            kids_ages_6_11 INTEGER NOT NULL DEFAULT 0,
            kids_ages_12_17 INTEGER NOT NULL DEFAULT 0,
            kids_reunited_while_in_program INTEGER NOT NULL DEFAULT 0,
            healthy_babies_born_at_dwc INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS family_snapshots (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            kids_at_dwc INTEGER NOT NULL DEFAULT 0,
            kids_served_outside_under_18 INTEGER NOT NULL DEFAULT 0,
            kids_ages_0_5 INTEGER NOT NULL DEFAULT 0,
            kids_ages_6_11 INTEGER NOT NULL DEFAULT 0,
            kids_ages_12_17 INTEGER NOT NULL DEFAULT 0,
            kids_reunited_while_in_program INTEGER NOT NULL DEFAULT 0,
            healthy_babies_born_at_dwc INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_exit_assessments_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS exit_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            date_graduated TEXT,
            date_exit_dwc TEXT,
            exit_reason TEXT,
            graduate_dwc INTEGER NOT NULL DEFAULT 0,
            leave_ama INTEGER NOT NULL DEFAULT 0,
            income_at_exit REAL,
            education_at_exit TEXT,
            received_car INTEGER NOT NULL DEFAULT 0,
            car_insurance INTEGER NOT NULL DEFAULT 0,
            dental_needs_met INTEGER NOT NULL DEFAULT 0,
            vision_needs_met INTEGER NOT NULL DEFAULT 0,
            obtained_insurance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS exit_assessments (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            date_graduated TEXT,
            date_exit_dwc TEXT,
            exit_reason TEXT,
            graduate_dwc INTEGER NOT NULL DEFAULT 0,
            leave_ama INTEGER NOT NULL DEFAULT 0,
            income_at_exit DOUBLE PRECISION,
            education_at_exit TEXT,
            received_car INTEGER NOT NULL DEFAULT 0,
            car_insurance INTEGER NOT NULL DEFAULT 0,
            dental_needs_met INTEGER NOT NULL DEFAULT 0,
            vision_needs_met INTEGER NOT NULL DEFAULT 0,
            obtained_insurance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_followups_table(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            followup_date TEXT NOT NULL,
            followup_type TEXT NOT NULL,
            income_at_followup REAL,
            sober_at_followup INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS followups (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            followup_date TEXT NOT NULL,
            followup_type TEXT NOT NULL,
            income_at_followup DOUBLE PRECISION,
            sober_at_followup INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def ensure_indexes() -> None:
    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_assessments_enrollment_idx
            ON intake_assessments (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS family_snapshots_enrollment_idx
            ON family_snapshots (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS exit_assessments_enrollment_idx
            ON exit_assessments (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS followups_enrollment_idx
            ON followups (enrollment_id)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_intake_assessments_table(kind)
    ensure_family_snapshots_table(kind)
    ensure_exit_assessments_table(kind)
    ensure_followups_table(kind)
