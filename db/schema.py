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
    Execute the sqlite or postgres version of a schema statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def ensure_admin_bootstrap() -> None:
    """
    Create the first admin user from environment variables if no admin exists.

    This is safe to run repeatedly. If an admin already exists, it exits.
    If the environment variables are missing, it exits.
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
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
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

    Safe to run repeatedly. Only residents missing a code are updated.
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


def init_db() -> None:
    """
    Current public schema entry point.

    For now this still forwards to the configured initializer.
    Later this module will own the full database bootstrap logic.
    """
    _run_configured_init()
