"""
Operational workflow schema objects.
"""

from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


def ensure_leave_requests_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
    )


def ensure_leave_request_phone_column(kind: str) -> None:
    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        pass


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
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
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
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
        )
        """,
    )


def drop_transport_dob_column_if_present(kind: str) -> None:
    if kind != "pg":
        return

    try:
        db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")
    except Exception:
        pass


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
            expected_back_time TEXT
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
            expected_back_time TEXT
        )
        """,
    )


def ensure_resident_passes_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS resident_passes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            pass_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
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
        """,
        """
        CREATE TABLE IF NOT EXISTS resident_passes (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            pass_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
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
        """,
    )


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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_indexes() -> None:
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS leave_requests_shelter_status_return_idx "
            "ON leave_requests (shelter, status, return_at)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS transport_requests_shelter_status_pickup_idx "
            "ON transport_requests (shelter, status, needed_at)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS attendance_events_shelter_occurred_idx "
            "ON attendance_events (shelter, event_time)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS attendance_events_resident_time_idx "
            "ON attendance_events (resident_id, event_time)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_transfers_resident_time_idx "
            "ON resident_transfers (resident_id, transferred_at)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_passes_resident_status_idx "
            "ON resident_passes (resident_id, status)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_passes_shelter_status_idx "
            "ON resident_passes (shelter, status)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS resident_pass_request_details_pass_idx "
            "ON resident_pass_request_details (pass_id)"
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_leave_requests_table(kind)
    ensure_transport_requests_table(kind)
    ensure_resident_transfers_table(kind)
    ensure_attendance_events_table(kind)
    ensure_resident_passes_table(kind)
    ensure_resident_pass_request_details_table(kind)


def ensure_columns_and_constraints(kind: str) -> None:
    ensure_leave_request_phone_column(kind)
    drop_transport_dob_column_if_present(kind)
