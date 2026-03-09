"""
Seed and bootstrap schema tasks.
"""

from __future__ import annotations

from flask import current_app

from werkzeug.security import generate_password_hash

from core.db import db_execute, db_fetchone
from . import schema_people


def ensure_default_organization_seed(kind: str) -> None:
    """
    Seed the default organization if it is missing.
    """
    row = db_fetchone(
        "SELECT id FROM organizations WHERE slug = %s"
        if kind == "pg"
        else "SELECT id FROM organizations WHERE slug = ?",
        ("dwc",),
    )
    if row:
        return

    db_execute(
        """
        INSERT INTO organizations
        (name, slug, public_name, primary_color, secondary_color, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        if kind == "pg"
        else """
        INSERT INTO organizations
        (name, slug, public_name, primary_color, secondary_color, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "Downtown Womens Center",
            "dwc",
            "Downtown Womens Center",
            "#4f8fbe",
            "#3f79a5",
            current_app.config["UTCNOW_ISO_FUNC"](),
        ),
    )


def ensure_admin_bootstrap(kind: str) -> None:
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
        if kind == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?,?,?,?,?)",
        (
            admin_user,
            generate_password_hash(admin_pass),
            "admin",
            True,
            current_app.config["UTCNOW_ISO_FUNC"](),
        ),
    )


def ensure_all(kind: str) -> None:
    ensure_default_organization_seed(kind)
    schema_people.backfill_resident_codes(kind)
    ensure_admin_bootstrap(kind)
