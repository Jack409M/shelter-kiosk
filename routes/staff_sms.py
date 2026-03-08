from __future__ import annotations

from flask import Blueprint, render_template

from core.auth import require_login
from core.db import db_fetchall

staff_sms = Blueprint("staff_sms", __name__)


@staff_sms.route("/staff/sms-consent")
@require_login
def staff_sms_consent():
    try:
        rows_raw = db_fetchall(
            """
            SELECT id, first_name, last_name, phone, sms_opt_in, sms_opt_out_at
            FROM residents
            WHERE phone IS NOT NULL AND phone != ''
            ORDER BY last_name ASC, first_name ASC, id DESC
            LIMIT 500
            """
        )

        rows = []
        for r in rows_raw or []:
            if isinstance(r, dict):
                rows.append(r)
            else:
                rows.append(
                    {
                        "id": r[0],
                        "first_name": r[1],
                        "last_name": r[2],
                        "phone": r[3],
                        "sms_opt_in": r[4],
                        "sms_opt_out_at": r[5],
                    }
                )

        return render_template(
            "staff_sms_consent.html",
            rows=rows,
            title="SMS Consent",
        )
    except Exception as e:
        return "SMS consent error: " + str(e), 500
