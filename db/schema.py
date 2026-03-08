"""
Database schema management helpers.
"""

from __future__ import annotations

from flask import current_app, g
from werkzeug.security import generate_password_hash

from core.db import db_execute, db_fetchall, db_fetchone


def _run_configured_init() -> None:
    """
    Run the initializer currently registered by the app.

    This remains available during the transition while schema logic
    is still being moved out of app.py.
    """
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return

    raise RuntimeError("Database initializer is not configured")


def _create(sqlite_sql: str, pg_sql: str, kind: str) -> None:
    """
    Execute the SQLite or Postgres version of a schema statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def ensure_sms_consent_columns(kind: str) -> None:
    """
    Ensure SMS consent columns exist on residents.

    Safe to run repeatedly for both Postgres and SQLite.
    """
    if kind == "pg":
        try:
            db_execute(
                "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN NOT NULL DEFAULT FALSE"
            )
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_source TEXT")
        except Exception:
            pass
    else:
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_source TEXT")
        except Exception:
            pass


def ensure_staff_users_table(kind: str) -> None:
    """
    Ensure staff_users table exists.
    """
    _create(
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        kind,
    )


def ensure_resident_code_schema(kind: str) -> None:
    """
    Ensure residents.resident_code exists and has a unique index.
    """
    try:
        if kind == "pg":
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS resident_code TEXT")
        else:
            db_execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass

    try:
        db_execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq "
            "ON residents (resident_code)"
        )
    except Exception:
        pass


def ensure_leave_request_phone_column(kind: str) -> None:
    """
    Ensure leave_requests.resident_phone exists.
    """
    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        pass


def drop_transport_dob_column_if_present(kind: str) -> None:
    """
    Remove old transport_requests.dob column on Postgres.
    """
    if kind != "pg":
        return

    try:
        db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")
    except Exception:
        pass


def ensure_admin_bootstrap() -> None:
    """
    Create the first admin user if none exists.
    """
    row = db_fetchone("SELECT COUNT(1) AS c FROM staff_users WHERE role = 'admin'")
    count = int(row["c"] if isinstance(row, dict) else row[0])

    if count > 0:
        return

    admin_user = (current_app.config.get("ADMIN_USERNAME") or "").strip()
    admin_pass = (current_app.config.get("ADMIN_PASSWORD") or "").strip()

    if not admin_user or not admin_pass:
        return

    db_execute(
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s,%s,%s,%s,%s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?,?,?,?,?)",
        (
            admin_user,
            generate_password_hash(admin_pass),
            "admin",
            True,
            current_app.config["UTCNOW_ISO_FUNC"](),
        ),
    )


def backfill_resident_codes(kind: str, make_resident_code_func) -> None:
    """
    Ensure every resident has a resident_code.
    """
    rows = db_fetchall(
        "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
    )

    for row in rows or []:
        resident_id = row["id"] if isinstance(row, dict) else row[0]
        code = make_resident_code_func()

        for _ in range(10):
            exists = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if kind == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (code,),
            )
            if not exists:
                break
            code = make_resident_code_func()

        db_execute(
            "UPDATE residents SET resident_code = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET resident_code = ? WHERE id = ?",
            (code, resident_id),
        )


def ensure_organizations_table(kind: str) -> None:
    """
    Ensure organizations table exists.
    """
    _create(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            primary_color TEXT,
            secondary_color TEXT,
            logo_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """,
        kind,
    )


def ensure_resident_transfers_table(kind: str) -> None:
    """
    Ensure resident_transfers table exists.
    """
    _create(
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
        kind,
    )


def ensure_twilio_message_status_table(kind: str) -> None:
    """
    Ensure twilio_message_status table exists.
    """
    _create(
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS twilio_message_status (
            id SERIAL PRIMARY KEY,
            message_sid TEXT NOT NULL,
            message_status TEXT NOT NULL,
            error_code TEXT,
            to_number TEXT,
            from_number TEXT,
            account_sid TEXT,
            api_version TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        kind,
    )


def ensure_audit_log_table(kind: str) -> None:
    """
    Ensure audit_log table exists.
    """
    _create(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        kind,
    )


def ensure_attendance_events_table(kind: str) -> None:
    """
    Ensure attendance_events table exists.
    """
    _create(
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
        kind,
    )


def ensure_rate_limit_events_table(kind: str) -> None:
    """
    Ensure Postgres rate_limit_events table exists.
    """
    if kind != "pg":
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id SERIAL PRIMARY KEY,
            k TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def ensure_rate_limit_event_indexes(kind: str) -> None:
    """
    Ensure indexes exist for rate_limit_events.
    """
    if kind != "pg":
        return

    db_execute(
        "CREATE INDEX IF NOT EXISTS rate_limit_events_k_idx ON rate_limit_events (k)"
    )
    db_execute(
        "CREATE INDEX IF NOT EXISTS rate_limit_events_created_at_idx ON rate_limit_events (created_at)"
    )


def ensure_twilio_message_status_indexes() -> None:
    """
    Ensure indexes exist for twilio_message_status.
    """
    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS twilio_message_status_sid_idx "
            "ON twilio_message_status (message_sid)"
        )
    except Exception:
        pass

    try:
        db_execute(
            "CREATE INDEX IF NOT EXISTS twilio_message_status_created_idx "
            "ON twilio_message_status (created_at)"
        )
    except Exception:
        pass


def ensure_common_app_indexes() -> None:
    """
    Ensure common application indexes exist.

    Safe to run repeatedly across supported databases.
    """
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
            "CREATE INDEX IF NOT EXISTS residents_shelter_active_name_idx "
            "ON residents (shelter, is_active, last_name, first_name)"
        )
    except Exception:
        pass


def init_db() -> None:
    """
    Current public schema entry point.
    """
    _run_configured_init()
