"""
Operational workflow schema objects.
"""

from __future__ import annotations

import contextlib

from core.db import db_execute

from .schema_helpers import create_table


def ensure_transport_requests_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            staff_notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            staff_notes TEXT
        )
        """,
    )


def drop_transport_dob_column_if_present(kind: str) -> None:
    if kind != "pg":
        return

    with contextlib.suppress(Exception):
        db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")


def drop_unused_transport_columns_if_present(kind: str) -> None:
    if kind != "pg":
        return

    statements = [
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS driver_name",
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS completed_at",
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS completed_by",
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS cancelled_at",
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS cancelled_by",
        "ALTER TABLE transport_requests DROP COLUMN IF EXISTS cancel_reason",
    ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_transfers_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_transfers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          resident_id INTEGER NOT NULL,
          from_shelter TEXT NOT NULL,
          to_shelter TEXT NOT NULL,
          transferred_by TEXT NOT NULL,
          transferred_at TEXT NOT NULL,
          note TEXT,
          FOREIGN KEY(resident_id) REFERENCES residents(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_transfers (
          id SERIAL PRIMARY KEY,
          resident_id INTEGER NOT NULL REFERENCES residents(id),
          from_shelter TEXT NOT NULL,
          to_shelter TEXT NOT NULL,
          transferred_by TEXT NOT NULL,
          transferred_at TIMESTAMP NOT NULL DEFAULT NOW(),
          note TEXT
        );
        """,
    )


def ensure_attendance_events_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT,
            expected_back_time TEXT,
            destination TEXT,
            obligation_start_time TEXT,
            obligation_end_time TEXT,
            actual_obligation_end_time TEXT,
            meeting_count INTEGER NOT NULL DEFAULT 0,
            meeting_1 TEXT,
            meeting_2 TEXT,
            is_recovery_meeting INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT,
            expected_back_time TEXT,
            destination TEXT,
            obligation_start_time TEXT,
            obligation_end_time TEXT,
            actual_obligation_end_time TEXT,
            meeting_count INTEGER NOT NULL DEFAULT 0,
            meeting_1 TEXT,
            meeting_2 TEXT,
            is_recovery_meeting INTEGER NOT NULL DEFAULT 0
        )
        """,
    )


def ensure_attendance_event_columns(kind: str) -> None:
    if kind == "pg":
        statements = [
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS destination TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS obligation_start_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS obligation_end_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS actual_obligation_end_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS meeting_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS meeting_1 TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS meeting_2 TEXT",
            "ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS is_recovery_meeting INTEGER NOT NULL DEFAULT 0",
        ]
    else:
        statements = [
            "ALTER TABLE attendance_events ADD COLUMN destination TEXT",
            "ALTER TABLE attendance_events ADD COLUMN obligation_start_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN obligation_end_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN actual_obligation_end_time TEXT",
            "ALTER TABLE attendance_events ADD COLUMN meeting_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE attendance_events ADD COLUMN meeting_1 TEXT",
            "ALTER TABLE attendance_events ADD COLUMN meeting_2 TEXT",
            "ALTER TABLE attendance_events ADD COLUMN is_recovery_meeting INTEGER NOT NULL DEFAULT 0",
        ]

    for statement in statements:
        with contextlib.suppress(Exception):
            db_execute(statement)


def ensure_resident_passes_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_passes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL CHECK (LENGTH(TRIM(shelter)) > 0),
            pass_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','denied','completed','expired')),
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
            delete_after_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_passes (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id) ON DELETE CASCADE,
            shelter TEXT NOT NULL CHECK (LENGTH(TRIM(shelter)) > 0),
            pass_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','denied','completed','expired')),
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
            delete_after_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_resident_passes_columns(kind: str) -> None:
    columns = [
        "delete_after_at TEXT",
    ]

    for column_def in columns:
        try:
            if kind == "pg":
                db_execute(f"ALTER TABLE resident_passes ADD COLUMN IF NOT EXISTS {column_def}")
            else:
                db_execute(f"ALTER TABLE resident_passes ADD COLUMN {column_def}")
        except Exception:
            from flask import current_app
            current_app.logger.exception("auto-logged exception")


def ensure_resident_pass_request_details_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_pass_request_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pass_id INTEGER NOT NULL,
            resident_phone TEXT,
            request_date TEXT,
            resident_level TEXT,
            requirements_acknowledged TEXT,
            requirements_not_met_explanation TEXT,
            reason_for_request TEXT,
            who_with TEXT,
            destination_address TEXT,
            destination_phone TEXT,
            companion_names TEXT,
            companion_phone_numbers TEXT,
            budgeted_amount TEXT,
            approved_amount TEXT,
            reviewed_by_user_id INTEGER,
            reviewed_by_name TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            FOREIGN KEY(pass_id) REFERENCES resident_passes(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_pass_request_details (
            id SERIAL PRIMARY KEY,
            pass_id INTEGER NOT NULL REFERENCES resident_passes(id),
            resident_phone TEXT,
            request_date TEXT,
            resident_level TEXT,
            requirements_acknowledged TEXT,
            requirements_not_met_explanation TEXT,
            reason_for_request TEXT,
            who_with TEXT,
            destination_address TEXT,
            destination_phone TEXT,
            companion_names TEXT,
            companion_phone_numbers TEXT,
            budgeted_amount TEXT,
            approved_amount TEXT,
            reviewed_by_user_id INTEGER,
            reviewed_by_name TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )


def ensure_resident_notifications_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            related_pass_id INTEGER,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            read_at TEXT,
            FOREIGN KEY(resident_id) REFERENCES residents(id),
            FOREIGN KEY(related_pass_id) REFERENCES resident_passes(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_notifications (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            shelter TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            related_pass_id INTEGER REFERENCES resident_passes(id),
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            read_at TEXT
        )
        """,
    )


def ensure_resident_pass_request_details_columns(kind: str) -> None:
    columns = [
        "resident_phone TEXT",
        "request_date TEXT",
        "resident_level TEXT",
        "requirements_acknowledged TEXT",
        "requirements_not_met_explanation TEXT",
        "reason_for_request TEXT",
        "who_with TEXT",
        "destination_address TEXT",
        "destination_phone TEXT",
        "companion_names TEXT",
        "companion_phone_numbers TEXT",
        "budgeted_amount TEXT",
        "approved_amount TEXT",
        "reviewed_by_user_id INTEGER",
        "reviewed_by_name TEXT",
        "reviewed_at TEXT",
        "created_at TEXT",
        "updated_at TEXT",
    ]

    for column_def in columns:
        try:
            if kind == "pg":
                db_execute(
                    f"ALTER TABLE resident_pass_request_details ADD COLUMN IF NOT EXISTS {column_def}"
                )
            else:
                db_execute(f"ALTER TABLE resident_pass_request_details ADD COLUMN {column_def}")
        except Exception:
            from flask import current_app
            current_app.logger.exception("auto-logged exception")


def ensure_tables(kind: str) -> None:
    ensure_transport_requests_table(kind)
    ensure_resident_transfers_table(kind)
    ensure_attendance_events_table(kind)
    ensure_resident_passes_table(kind)
    ensure_resident_pass_request_details_table(kind)
    ensure_resident_notifications_table(kind)


def ensure_columns_and_constraints(kind: str) -> None:
    drop_transport_dob_column_if_present(kind)
    drop_unused_transport_columns_if_present(kind)
    ensure_attendance_event_columns(kind)
    ensure_resident_passes_columns(kind)
    ensure_resident_pass_request_details_columns(kind)


def ensure_indexes() -> None:
    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS transport_requests_shelter_status_pickup_idx "
            "ON transport_requests (shelter, status, needed_at)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS attendance_events_shelter_occurred_idx "
            "ON attendance_events (shelter, event_time)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS attendance_events_resident_time_idx "
            "ON attendance_events (resident_id, event_time)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_transfers_resident_time_idx "
            "ON resident_transfers (resident_id, transferred_at)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_passes_resident_status_idx "
            "ON resident_passes (resident_id, status)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_passes_shelter_status_idx "
            "ON resident_passes (shelter, status)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_passes_shelter_delete_after_idx "
            "ON resident_passes (shelter, delete_after_at)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS resident_passes_one_active_idx "
            "ON resident_passes (resident_id) "
            "WHERE status IN ('pending','approved')"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_pass_request_details_pass_idx "
            "ON resident_pass_request_details (pass_id)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_notifications_resident_created_idx "
            "ON resident_notifications (resident_id, created_at)"
        )

    with contextlib.suppress(Exception):
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_notifications_resident_read_created_idx "
            "ON resident_notifications (resident_id, is_read, created_at)"
        )
