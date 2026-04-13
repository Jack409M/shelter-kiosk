from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from core.auth import require_login
from core.db import DbRow, db_fetchall

staff_sms = Blueprint("staff_sms", __name__)


def _normalize_sms_consent_rows(rows_raw: list[DbRow]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for row in rows_raw or []:
        rows.append(
            {
                "id": row.get("id"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "phone": row.get("phone"),
                "sms_opt_in": row.get("sms_opt_in"),
                "sms_opt_out_at": row.get("sms_opt_out_at"),
            }
        )

    return rows


@staff_sms.route("/staff/sms-consent")
@require_login
def staff_sms_consent():
    try:
        rows_raw = db_fetchall(
            """
            SELECT id, first_name, last_name, phone, sms_opt_in, sms_opt_out_at
            FROM residents
            WHERE COALESCE(phone, '') <> ''
            ORDER BY last_name ASC, first_name ASC, id DESC
            LIMIT 500
            """
        )
    except Exception:
        current_app.logger.exception("Failed to load SMS consent resident list.")
        flash(
            "Unable to load SMS consent data. Please try again or contact an administrator.",
            "error",
        )
        return redirect(url_for("attendance.staff_attendance"))

    rows = _normalize_sms_consent_rows(rows_raw)

    return render_template(
        "staff_sms_consent.html",
        rows=rows,
        title="SMS Consent",
    )
