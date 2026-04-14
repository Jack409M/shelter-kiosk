"""
Seed and bootstrap schema tasks.
"""

from __future__ import annotations

from flask import current_app
from werkzeug.security import generate_password_hash

from core.db import db_execute, db_fetchall, db_fetchone

from . import schema_program


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


def _favorites_table_exists(kind: str) -> bool:
    row = db_fetchone(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = %s
        """
        if kind == "pg"
        else """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        ("user_dashboard_favorites",),
    )
    return bool(row)


def _favorites_fk_is_correct(kind: str) -> bool:
    if kind == "pg":
        row = db_fetchone(
            """
            SELECT ccu.table_name AS foreign_table_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = %s
              AND kcu.column_name = %s
            """,
            ("user_dashboard_favorites", "user_id"),
        )
        foreign_table_name = ""
        if row:
            foreign_table_name = (
                row["foreign_table_name"] if isinstance(row, dict) else row[0]
            ) or ""
        return foreign_table_name == "staff_users"

    row = db_fetchone(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        ("user_dashboard_favorites",),
    )
    if not row:
        return False

    create_sql = (row["sql"] if isinstance(row, dict) else row[0]) or ""
    normalized = create_sql.lower().replace('"', "").replace("`", "")
    return "references staff_users(id)" in normalized


def _load_existing_favorites() -> list[tuple]:
    try:
        rows = db_fetchall(
            """
            SELECT user_id, dashboard_key, metric_key, display_order, created_at
            FROM user_dashboard_favorites
            ORDER BY id ASC
            """
        )
    except Exception:
        return []

    preserved_rows: list[tuple] = []

    for row in rows:
        if isinstance(row, dict):
            preserved_rows.append(
                (
                    row.get("user_id"),
                    row.get("dashboard_key"),
                    row.get("metric_key"),
                    row.get("display_order"),
                    row.get("created_at"),
                )
            )
        else:
            preserved_rows.append((row[0], row[1], row[2], row[3], row[4]))

    return preserved_rows


def _restore_favorites(kind: str, rows: list[tuple]) -> None:
    if not rows:
        return

    insert_sql = (
        """
        INSERT INTO user_dashboard_favorites
        (user_id, dashboard_key, metric_key, display_order, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, dashboard_key, metric_key) DO NOTHING
        """
        if kind == "pg"
        else """
        INSERT OR IGNORE INTO user_dashboard_favorites
        (user_id, dashboard_key, metric_key, display_order, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
    )

    for user_id, dashboard_key, metric_key, display_order, created_at in rows:
        if not user_id or not dashboard_key or not metric_key:
            continue

        db_execute(
            insert_sql,
            (
                user_id,
                dashboard_key,
                metric_key,
                display_order or 0,
                created_at or current_app.config["UTCNOW_ISO_FUNC"](),
            ),
        )


def ensure_user_dashboard_favorites_schema(kind: str) -> None:
    """
    Ensure the favorites table exists and references staff_users(id).

    This safely rebuilds the table only when an older incompatible version
    exists, while preserving existing favorite rows when possible.
    """
    if not _favorites_table_exists(kind):
        schema_program.ensure_user_dashboard_favorites_table(kind)
        schema_program.ensure_indexes()
        return

    if _favorites_fk_is_correct(kind):
        schema_program.ensure_user_dashboard_favorites_table(kind)
        schema_program.ensure_indexes()
        return

    preserved_rows = _load_existing_favorites()

    db_execute("DROP TABLE IF EXISTS user_dashboard_favorites")

    schema_program.ensure_user_dashboard_favorites_table(kind)
    schema_program.ensure_indexes()
    _restore_favorites(kind, preserved_rows)


def ensure_all(kind: str) -> None:
    ensure_default_organization_seed(kind)
    ensure_admin_bootstrap(kind)
    ensure_user_dashboard_favorites_schema(kind)
