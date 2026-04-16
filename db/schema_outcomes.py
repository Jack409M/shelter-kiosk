"""
Outcomes schema.

This module stores program intake, family impact, exit, and follow up
records tied to a program enrollment.
"""

from __future__ import annotations

import contextlib

from .schema_helpers import create_table


def ensure_intake_assessments_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS intake_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            city TEXT,
            county TEXT,
            last_zipcode_residence TEXT,
            length_of_time_in_amarillo TEXT,
            income_at_entry REAL,
            education_at_entry TEXT,
            treatment_grad_date TEXT,
            sobriety_date TEXT,
            days_sober_at_entry INTEGER,
            drug_of_choice TEXT,
            ace_score INTEGER,
            grit_score INTEGER,
            veteran INTEGER NOT NULL DEFAULT 0,
            disability TEXT,
            marital_status TEXT,
            notes_basic TEXT,
            entry_notes TEXT,
            initial_snapshot_notes TEXT,
            trauma_notes TEXT,
            barrier_notes TEXT,
            place_staying_before_entry TEXT,
            entry_felony_conviction INTEGER NOT NULL DEFAULT 0,
            entry_parole_probation INTEGER NOT NULL DEFAULT 0,
            drug_court INTEGER NOT NULL DEFAULT 0,
            sexual_survivor INTEGER NOT NULL DEFAULT 0,
            dv_survivor INTEGER NOT NULL DEFAULT 0,
            human_trafficking_survivor INTEGER NOT NULL DEFAULT 0,
            warrants_unpaid INTEGER NOT NULL DEFAULT 0,
            mh_exam_completed INTEGER NOT NULL DEFAULT 0,
            med_exam_completed INTEGER NOT NULL DEFAULT 0,
            car_at_entry INTEGER NOT NULL DEFAULT 0,
            car_insurance_at_entry INTEGER NOT NULL DEFAULT 0,
            pregnant_at_entry INTEGER NOT NULL DEFAULT 0,
            dental_need_at_entry INTEGER NOT NULL DEFAULT 0,
            vision_need_at_entry INTEGER NOT NULL DEFAULT 0,
            employment_status_at_entry TEXT,
            mental_health_need_at_entry INTEGER NOT NULL DEFAULT 0,
            medical_need_at_entry INTEGER NOT NULL DEFAULT 0,
            substance_use_need_at_entry INTEGER NOT NULL DEFAULT 0,
            id_documents_status_at_entry TEXT,
            has_drivers_license INTEGER NOT NULL DEFAULT 0,
            has_social_security_card INTEGER NOT NULL DEFAULT 0,
            parenting_class_needed INTEGER NOT NULL DEFAULT 0,
            dwc_level_today TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS intake_assessments (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            city TEXT,
            county TEXT,
            last_zipcode_residence TEXT,
            length_of_time_in_amarillo TEXT,
            income_at_entry DOUBLE PRECISION,
            education_at_entry TEXT,
            treatment_grad_date TEXT,
            sobriety_date TEXT,
            days_sober_at_entry INTEGER,
            drug_of_choice TEXT,
            ace_score INTEGER,
            grit_score INTEGER,
            veteran INTEGER NOT NULL DEFAULT 0,
            disability TEXT,
            marital_status TEXT,
            notes_basic TEXT,
            entry_notes TEXT,
            initial_snapshot_notes TEXT,
            trauma_notes TEXT,
            barrier_notes TEXT,
            place_staying_before_entry TEXT,
            entry_felony_conviction INTEGER NOT NULL DEFAULT 0,
            entry_parole_probation INTEGER NOT NULL DEFAULT 0,
            drug_court INTEGER NOT NULL DEFAULT 0,
            sexual_survivor INTEGER NOT NULL DEFAULT 0,
            dv_survivor INTEGER NOT NULL DEFAULT 0,
            human_trafficking_survivor INTEGER NOT NULL DEFAULT 0,
            warrants_unpaid INTEGER NOT NULL DEFAULT 0,
            mh_exam_completed INTEGER NOT NULL DEFAULT 0,
            med_exam_completed INTEGER NOT NULL DEFAULT 0,
            car_at_entry INTEGER NOT NULL DEFAULT 0,
            car_insurance_at_entry INTEGER NOT NULL DEFAULT 0,
            pregnant_at_entry INTEGER NOT NULL DEFAULT 0,
            dental_need_at_entry INTEGER NOT NULL DEFAULT 0,
            vision_need_at_entry INTEGER NOT NULL DEFAULT 0,
            employment_status_at_entry TEXT,
            mental_health_need_at_entry INTEGER NOT NULL DEFAULT 0,
            medical_need_at_entry INTEGER NOT NULL DEFAULT 0,
            substance_use_need_at_entry INTEGER NOT NULL DEFAULT 0,
            id_documents_status_at_entry TEXT,
            has_drivers_license INTEGER NOT NULL DEFAULT 0,
            has_social_security_card INTEGER NOT NULL DEFAULT 0,
            parenting_class_needed INTEGER NOT NULL DEFAULT 0,
            dwc_level_today TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_intake_assessment_columns(kind: str) -> None:
    try:
        from core.db import db_execute, db_fetchone

        try:
            col = db_fetchone(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'intake_assessments'
                  AND column_name = 'disability'
                """
            )

            if col and isinstance(col, dict):
                data_type = col.get("data_type")
            elif col:
                data_type = col[0]
            else:
                data_type = None

            if data_type and "int" in str(data_type).lower():
                with contextlib.suppress(Exception):
                    db_execute(
                        """
                        ALTER TABLE intake_assessments
                        ALTER COLUMN disability TYPE TEXT
                        USING disability::TEXT
                        """
                    )

        except Exception:
            pass

        statements = [
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS city TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS county TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS last_zipcode_residence TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS length_of_time_in_amarillo TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS marital_status TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS disability TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS notes_basic TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS entry_notes TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS initial_snapshot_notes TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS trauma_notes TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS barrier_notes TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS treatment_grad_date TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS drug_court INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS sexual_survivor INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS warrants_unpaid INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS mh_exam_completed INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS med_exam_completed INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS car_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS car_insurance_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS pregnant_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS dental_need_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS vision_need_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS employment_status_at_entry TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS mental_health_need_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS medical_need_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS substance_use_need_at_entry INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS id_documents_status_at_entry TEXT",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS has_drivers_license INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS has_social_security_card INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS parenting_class_needed INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE intake_assessments ADD COLUMN IF NOT EXISTS dwc_level_today TEXT",
        ]

        for sql in statements:
            with contextlib.suppress(Exception):
                db_execute(sql)

    except Exception:
        pass


def ensure_family_snapshots_table(kind: str) -> None:
    create_table(
        kind,
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
        """,
    )


def ensure_exit_assessments_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS exit_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL UNIQUE,
            date_graduated TEXT,
            date_exit_dwc TEXT,
            exit_category TEXT,
            exit_reason TEXT,
            graduate_dwc INTEGER NOT NULL DEFAULT 0,
            leave_ama INTEGER NOT NULL DEFAULT 0,
            leave_amarillo_city TEXT,
            leave_amarillo_unknown INTEGER NOT NULL DEFAULT 0,
            income_at_exit REAL,
            graduation_income_snapshot REAL,
            education_at_exit TEXT,
            grit_at_exit REAL,
            received_car INTEGER NOT NULL DEFAULT 0,
            car_insurance INTEGER NOT NULL DEFAULT 0,
            dental_needs_met INTEGER NOT NULL DEFAULT 0,
            vision_needs_met INTEGER NOT NULL DEFAULT 0,
            obtained_public_insurance INTEGER NOT NULL DEFAULT 0,
            private_insurance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exit_assessments (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL UNIQUE REFERENCES program_enrollments(id),
            date_graduated TEXT,
            date_exit_dwc TEXT,
            exit_category TEXT,
            exit_reason TEXT,
            graduate_dwc INTEGER NOT NULL DEFAULT 0,
            leave_ama INTEGER NOT NULL DEFAULT 0,
            leave_amarillo_city TEXT,
            leave_amarillo_unknown INTEGER NOT NULL DEFAULT 0,
            income_at_exit DOUBLE PRECISION,
            graduation_income_snapshot DOUBLE PRECISION,
            education_at_exit TEXT,
            grit_at_exit DOUBLE PRECISION,
            received_car INTEGER NOT NULL DEFAULT 0,
            car_insurance INTEGER NOT NULL DEFAULT 0,
            dental_needs_met INTEGER NOT NULL DEFAULT 0,
            vision_needs_met INTEGER NOT NULL DEFAULT 0,
            obtained_public_insurance INTEGER NOT NULL DEFAULT 0,
            private_insurance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_exit_assessment_columns(kind: str) -> None:
    try:
        from core.db import db_execute

        statements = [
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS exit_category TEXT",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS leave_amarillo_city TEXT",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS leave_amarillo_unknown INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS grit_at_exit DOUBLE PRECISION",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS obtained_public_insurance INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS private_insurance INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE exit_assessments ADD COLUMN IF NOT EXISTS graduation_income_snapshot DOUBLE PRECISION",
        ]

        for sql in statements:
            with contextlib.suppress(Exception):
                db_execute(sql)

    except Exception:
        pass


def ensure_followups_table(kind: str) -> None:
    create_table(
        kind,
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
        """,
    )


def _dedupe_single_row_per_enrollment(table_name: str) -> None:
    from core.db import db_execute, db_fetchall

    duplicate_rows = db_fetchall(
        f"""
        SELECT enrollment_id, COUNT(*) AS row_count
        FROM {table_name}
        GROUP BY enrollment_id
        HAVING COUNT(*) > 1
        """
    )

    for duplicate_row in duplicate_rows or []:
        enrollment_id = (
            duplicate_row["enrollment_id"]
            if isinstance(duplicate_row, dict)
            else duplicate_row[0]
        )
        rows = db_fetchall(
            f"""
            SELECT id
            FROM {table_name}
            WHERE enrollment_id = %s
            ORDER BY COALESCE(updated_at, '') DESC, COALESCE(created_at, '') DESC, id DESC
            """
            if "%s" == "%s" else ""
        )
        # placeholder-safe branch below
        if rows is None:
            rows = []

        from routes.case_management_parts.helpers import placeholder

        ph = placeholder()
        rows = db_fetchall(
            f"""
            SELECT id
            FROM {table_name}
            WHERE enrollment_id = {ph}
            ORDER BY COALESCE(updated_at, '') DESC, COALESCE(created_at, '') DESC, id DESC
            """,
            (enrollment_id,),
        )

        row_ids = [row["id"] if isinstance(row, dict) else row[0] for row in rows or []]
        keep_id = row_ids[0] if row_ids else None
        delete_ids = [row_id for row_id in row_ids[1:] if row_id != keep_id]

        for row_id in delete_ids:
            db_execute(
                f"DELETE FROM {table_name} WHERE id = {ph}",
                (row_id,),
            )


def ensure_single_row_baseline_integrity() -> None:
    with contextlib.suppress(Exception):
        _dedupe_single_row_per_enrollment("intake_assessments")

    with contextlib.suppress(Exception):
        _dedupe_single_row_per_enrollment("family_snapshots")


def ensure_indexes() -> None:
    try:
        from core.db import db_execute

        ensure_single_row_baseline_integrity()

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS intake_assessments_enrollment_idx
            ON intake_assessments (enrollment_id)
            """
        )
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS intake_assessments_enrollment_uidx
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
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS family_snapshots_enrollment_uidx
            ON family_snapshots (enrollment_id)
            """
        )
    except Exception:
        pass

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS exit_assessments_enrollment_uidx
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

    try:
        from core.db import db_execute

        db_execute(
            """
            CREATE INDEX IF NOT EXISTS followups_enrollment_type_idx
            ON followups (enrollment_id, followup_type)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_intake_assessments_table(kind)
    ensure_intake_assessment_columns(kind)
    ensure_family_snapshots_table(kind)
    ensure_exit_assessments_table(kind)
    ensure_exit_assessment_columns(kind)
    ensure_followups_table(kind)
