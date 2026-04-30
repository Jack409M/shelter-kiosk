from __future__ import annotations

import csv
import io

from flask import Response, flash, g, redirect, render_template, request, url_for

from core.admin_rbac import require_admin_role as _require_admin
from core.db import db_fetchall


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _like_operator() -> str:
    return "ILIKE" if g.get("db_kind") == "pg" else "LIKE"


def _unified_audit_cte() -> str:
    return """
        WITH unified_audit_events AS (
            SELECT
                id,
                'action' AS event_source,
                entity_type,
                entity_id,
                shelter,
                staff_user_id,
                action_type AS event_type,
                action_details AS detail,
                '' AS old_value,
                action_details AS new_value,
                created_at
            FROM audit_log

            UNION ALL

            SELECT
                id,
                'field_change' AS event_source,
                entity_type,
                entity_id,
                shelter,
                changed_by_user_id AS staff_user_id,
                field_name AS event_type,
                change_reason AS detail,
                old_value,
                new_value,
                created_at
            FROM field_change_audit
        )
    """


def _audit_where_from_request():
    where = []
    params = []
    ph = _placeholder()

    def add_eq(field: str, key: str) -> None:
        value = (request.args.get(key) or "").strip()
        if value:
            where.append(f"{field} = {ph}")
            params.append(value)

    add_eq("u.shelter", "shelter")
    add_eq("u.entity_type", "entity_type")
    add_eq("u.event_type", "action_type")
    add_eq("u.event_source", "event_source")

    staff_user_id = (request.args.get("staff_user_id") or "").strip()
    if staff_user_id.isdigit():
        where.append(f"u.staff_user_id = {ph}")
        params.append(int(staff_user_id))

    q = (request.args.get("q") or "").strip()
    if q:
        like_op = _like_operator()
        where.append(
            "("
            f"CAST(u.id AS TEXT) {like_op} {ph} OR "
            f"COALESCE(u.detail, '') {like_op} {ph} OR "
            f"COALESCE(u.event_type, '') {like_op} {ph} OR "
            f"COALESCE(u.entity_type, '') {like_op} {ph} OR "
            f"COALESCE(u.old_value, '') {like_op} {ph} OR "
            f"COALESCE(u.new_value, '') {like_op} {ph} OR "
            f"COALESCE(su.username, '') {like_op} {ph}"
            ")"
        )
        pattern = f"%{q}%"
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, tuple(params)


def _load_audit_filter_options():
    cte = _unified_audit_cte()

    shelters = db_fetchall(
        cte
        + """
        SELECT DISTINCT u.shelter
        FROM unified_audit_events u
        WHERE COALESCE(u.shelter, '') <> ''
        ORDER BY u.shelter ASC
        """
    )

    staff_rows = db_fetchall(
        cte
        + """
        SELECT DISTINCT
            u.staff_user_id,
            COALESCE(su.username, '') AS staff_username
        FROM unified_audit_events u
        LEFT JOIN staff_users su ON su.id = u.staff_user_id
        WHERE u.staff_user_id IS NOT NULL
        ORDER BY staff_username ASC, u.staff_user_id ASC
        """
    )

    entity_rows = db_fetchall(
        cte
        + """
        SELECT DISTINCT u.entity_type
        FROM unified_audit_events u
        WHERE COALESCE(u.entity_type, '') <> ''
        ORDER BY u.entity_type ASC
        """
    )

    action_rows = db_fetchall(
        cte
        + """
        SELECT DISTINCT u.event_type AS action_type
        FROM unified_audit_events u
        WHERE COALESCE(u.event_type, '') <> ''
        ORDER BY u.event_type ASC
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


def _load_audit_rows(limit: int | None = 200):
    where_sql, params = _audit_where_from_request()
    ph = _placeholder()
    limit_sql = f" LIMIT {ph}" if limit else ""
    limit_params = (limit,) if limit else ()

    sql = (
        _unified_audit_cte()
        + f"""
        SELECT
            u.*,
            COALESCE(su.username, '') AS staff_username
        FROM unified_audit_events u
        LEFT JOIN staff_users su ON su.id = u.staff_user_id
        {where_sql}
        ORDER BY u.created_at DESC, u.id DESC
        {limit_sql}
        """
    )

    return db_fetchall(sql, params + limit_params)


def staff_audit_log_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    rows = _load_audit_rows(limit=200)
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

    rows = _load_audit_rows(limit=None)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "event_source",
            "entity_type",
            "entity_id",
            "shelter",
            "staff_username",
            "event_type",
            "detail",
            "old_value",
            "new_value",
            "created_at",
        ]
    )

    for row in rows:
        writer.writerow(
            [
                row.get("id", ""),
                row.get("event_source", ""),
                row.get("entity_type", ""),
                row.get("entity_id", ""),
                row.get("shelter", ""),
                row.get("staff_username", ""),
                row.get("event_type", ""),
                row.get("detail", ""),
                row.get("old_value", ""),
                row.get("new_value", ""),
                row.get("created_at", ""),
            ]
        )

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
