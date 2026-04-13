from __future__ import annotations

import csv
import io

from flask import Response, flash, g, redirect, render_template, request, url_for

from core.db import db_fetchall
from routes.admin_parts.helpers import (
    audit_where_from_request as _audit_where_from_request,
)
from routes.admin_parts.helpers import (
    require_admin_role as _require_admin,
)


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _load_audit_filter_options():
    _placeholder()

    shelters = db_fetchall(
        """
        SELECT DISTINCT a.shelter
        FROM audit_log a
        WHERE COALESCE(a.shelter, '') <> ''
        ORDER BY a.shelter ASC
        """
    )

    staff_rows = db_fetchall(
        """
        SELECT DISTINCT
            a.staff_user_id,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.staff_user_id IS NOT NULL
        ORDER BY staff_username ASC, a.staff_user_id ASC
        """
    )

    entity_rows = db_fetchall(
        """
        SELECT DISTINCT a.entity_type
        FROM audit_log a
        WHERE COALESCE(a.entity_type, '') <> ''
        ORDER BY a.entity_type ASC
        """
    )

    action_rows = db_fetchall(
        """
        SELECT DISTINCT a.action_type
        FROM audit_log a
        WHERE COALESCE(a.action_type, '') <> ''
        ORDER BY a.action_type ASC
        """
    )

    all_shelters = [row.get("shelter", "") for row in shelters if row.get("shelter")]
    staff_options = [
        {
            "staff_user_id": row.get("staff_user_id"),
            "staff_username": row.get("staff_username") or f"User {row.get('staff_user_id')}",
        }
        for row in staff_rows
        if row.get("staff_user_id") is not None
    ]
    entity_options = [row.get("entity_type", "") for row in entity_rows if row.get("entity_type")]
    action_options = [row.get("action_type", "") for row in action_rows if row.get("action_type")]

    return all_shelters, staff_options, entity_options, action_options


def staff_audit_log_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    where_sql, params = _audit_where_from_request(request)
    ph = _placeholder()

    sql = f"""
        SELECT
            a.*,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        {where_sql}
        ORDER BY a.id DESC
        LIMIT {ph}
        """

    rows = db_fetchall(sql, params + (200,))
    all_shelters, staff_options, entity_options, action_options = _load_audit_filter_options()

    return render_template(
        "staff_audit_log.html",
        rows=rows,
        all_shelters=all_shelters,
        staff_options=staff_options,
        entity_options=entity_options,
        action_options=action_options,
    )


def staff_audit_log_csv_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    where_sql, params = _audit_where_from_request(request)
    created_expr = "a.created_at::text" if g.get("db_kind") == "pg" else "a.created_at"

    sql = (
        f"SELECT a.id, a.entity_type, a.entity_id, a.shelter, "
        f"COALESCE(su.username, '') AS staff_username, "
        f"a.action_type, COALESCE(a.action_details, '') AS action_details, "
        f"{created_expr} AS created_at "
        f"FROM audit_log a "
        f"LEFT JOIN staff_users su ON su.id = a.staff_user_id "
        f"{where_sql} "
        f"ORDER BY a.id DESC"
    )

    rows = db_fetchall(sql, params)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "entity_type",
            "entity_id",
            "shelter",
            "staff_username",
            "action_type",
            "action_details",
            "created_at",
        ]
    )

    for row in rows:
        if isinstance(row, dict):
            writer.writerow(
                [
                    row.get("id", ""),
                    row.get("entity_type", ""),
                    row.get("entity_id", ""),
                    row.get("shelter", ""),
                    row.get("staff_username", ""),
                    row.get("action_type", ""),
                    row.get("action_details", ""),
                    row.get("created_at", ""),
                ]
            )
        else:
            writer.writerow(list(row))

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
