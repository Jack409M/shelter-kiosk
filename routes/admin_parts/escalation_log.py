from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from core.admin_rbac import require_admin_role
from core.db import db_fetchall


def escalation_log_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    rows = db_fetchall(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            severity,
            title,
            channel,
            delivery_status,
            message,
            metadata,
            created_at
        FROM system_alert_delivery_logs
        WHERE channel = %s
        ORDER BY id DESC
        LIMIT 100
        """,
        ("escalation",),
    )

    return render_template(
        "escalation_log.html",
        title="Escalation Log",
        rows=rows or [],
    )
