from __future__ import annotations

import contextlib

from core.db import db_execute
from .schema_helpers import create_table


def ensure_level9_support_lifecycles_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS level9_support_lifecycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            apartment_id INTEGER,
            apartment_assignment_id INTEGER,
            case_manager_user_id INTEGER,
            started_by_user_id INTEGER,
            status TEXT NOT NULL,
            participation_status TEXT NOT NULL,
            start_date TEXT NOT NULL,
            initial_end_date TEXT NOT NULL,
            extended_end_date TEXT,
            final_end_date TEXT,
            extension_granted INTEGER NOT NULL DEFAULT 0,
            extension_decided_by_user_id INTEGER,
            extension_decision_date TEXT,
            opt_out_date TEXT,
            opt_out_reason TEXT,
            apartment_exit_date TEXT,
            apartment_exit_reason TEXT,
            program_exit_snapshot_level INTEGER NOT NULL DEFAULT 9,
            deactivation_ready INTEGER NOT NULL DEFAULT 0,
            deactivated_at TEXT,
            deactivated_by_user_id INTEGER,
            closure_reason TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS level9_support_lifecycles (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            shelter TEXT NOT NULL,
            apartment_id INTEGER,
            apartment_assignment_id INTEGER,
            case_manager_user_id INTEGER,
            started_by_user_id INTEGER,
            status TEXT NOT NULL,
            participation_status TEXT NOT NULL,
            start_date TEXT NOT NULL,
            initial_end_date TEXT NOT NULL,
            extended_end_date TEXT,
            final_end_date TEXT,
            extension_granted BOOLEAN NOT NULL DEFAULT FALSE,
            extension_decided_by_user_id INTEGER,
            extension_decision_date TEXT,
            opt_out_date TEXT,
            opt_out_reason TEXT,
            apartment_exit_date TEXT,
            apartment_exit_reason TEXT,
            program_exit_snapshot_level INTEGER NOT NULL DEFAULT 9,
            deactivation_ready BOOLEAN NOT NULL DEFAULT FALSE,
            deactivated_at TEXT,
            deactivated_by_user_id INTEGER,
            closure_reason TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_level9_monthly_followups_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS level9_monthly_followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level9_lifecycle_id INTEGER NOT NULL,
            resident_id INTEGER NOT NULL,
            enrollment_id INTEGER NOT NULL,
            support_month_number INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            completed_date TEXT,
            status TEXT NOT NULL,
            contact_result TEXT,
            followup_method TEXT,
            completed_by_user_id INTEGER,
            summary_notes TEXT,
            housing_status TEXT,
            employment_status TEXT,
            income_status TEXT,
            sobriety_status TEXT,
            needs_assistance INTEGER NOT NULL DEFAULT 0,
            risk_flag INTEGER NOT NULL DEFAULT 0,
            next_steps TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (level9_lifecycle_id) REFERENCES level9_support_lifecycles(id),
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (enrollment_id) REFERENCES program_enrollments(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS level9_monthly_followups (
            id SERIAL PRIMARY KEY,
            level9_lifecycle_id INTEGER NOT NULL REFERENCES level9_support_lifecycles(id),
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            enrollment_id INTEGER NOT NULL REFERENCES program_enrollments(id),
            support_month_number INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            completed_date TEXT,
            status TEXT NOT NULL,
            contact_result TEXT,
            followup_method TEXT,
            completed_by_user_id INTEGER,
            summary_notes TEXT,
            housing_status TEXT,
            employment_status TEXT,
            income_status TEXT,
            sobriety_status TEXT,
            needs_assistance INTEGER NOT NULL DEFAULT 0,
            risk_flag INTEGER NOT NULL DEFAULT 0,
            next_steps TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_level9_exit_interviews_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS level9_exit_interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level9_lifecycle_id INTEGER NOT NULL,
            resident_id INTEGER NOT NULL,
            interview_type TEXT NOT NULL,
            target_date TEXT,
            completed_date TEXT,
            status TEXT NOT NULL,
            completed_by_user_id INTEGER,
            declined INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (level9_lifecycle_id) REFERENCES level9_support_lifecycles(id),
            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS level9_exit_interviews (
            id SERIAL PRIMARY KEY,
            level9_lifecycle_id INTEGER NOT NULL REFERENCES level9_support_lifecycles(id),
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            interview_type TEXT NOT NULL,
            target_date TEXT,
            completed_date TEXT,
            status TEXT NOT NULL,
            completed_by_user_id INTEGER,
            declined INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_level9_support_events_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS level9_support_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level9_lifecycle_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            performed_by_user_id INTEGER,
            old_value TEXT,
            new_value TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (level9_lifecycle_id) REFERENCES level9_support_lifecycles(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS level9_support_events (
            id SERIAL PRIMARY KEY,
            level9_lifecycle_id INTEGER NOT NULL REFERENCES level9_support_lifecycles(id),
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            performed_by_user_id INTEGER,
            old_value JSONB,
            new_value JSONB,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """,
    )


def ensure_indexes() -> None:
    statements = (
        """
        CREATE UNIQUE INDEX IF NOT EXISTS level9_support_lifecycles_enrollment_uidx
        ON level9_support_lifecycles (enrollment_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_support_lifecycles_resident_idx
        ON level9_support_lifecycles (resident_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_support_lifecycles_status_idx
        ON level9_support_lifecycles (status, participation_status)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_support_lifecycles_ready_idx
        ON level9_support_lifecycles (deactivation_ready, status)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS level9_monthly_followups_month_uidx
        ON level9_monthly_followups (level9_lifecycle_id, support_month_number)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_monthly_followups_due_idx
        ON level9_monthly_followups (status, due_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_monthly_followups_resident_idx
        ON level9_monthly_followups (resident_id, due_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_exit_interviews_lifecycle_idx
        ON level9_exit_interviews (level9_lifecycle_id, interview_type)
        """,
        """
        CREATE INDEX IF NOT EXISTS level9_support_events_lifecycle_idx
        ON level9_support_events (level9_lifecycle_id, event_date)
        """,
    )

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_tables(kind: str) -> None:
    ensure_level9_support_lifecycles_table(kind)
    ensure_level9_monthly_followups_table(kind)
    ensure_level9_exit_interviews_table(kind)
    ensure_level9_support_events_table(kind)
