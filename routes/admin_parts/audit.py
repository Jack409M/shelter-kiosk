from __future__ import annotations

import csv
import io

from flask import Response, current_app, flash, g, redirect, render_template, request, url_for

from core.db import db_fetchall
from routes.admin_parts.helpers import (
    audit_where_from_request as _audit_where_from_request,
    require_admin_role as _require_admin,
)


def staff_audit_log_view():
    # Future extraction note
    # If audit grows further, split list view and export logic into:
    # audit_queries.py
    # audit_exports.py
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    sql = (
        """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT %s
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT a.*, su.username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        ORDER BY a.id DESC
        LIMIT ?
        """
    )

    rows = db_fetchall(sql, (200,))
    return render_template("staff_audit_log.html", rows=rows)


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
