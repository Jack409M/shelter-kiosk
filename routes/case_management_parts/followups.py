# routes/case_management_parts/followups.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from core.db import get_db
from core.auth import require_login

followups_bp = Blueprint("followups", __name__, url_prefix="/followups")


@followups_bp.route("/<int:enrollment_id>/<string:followup_type>", methods=["GET"])
@require_login
def load_followup(enrollment_id, followup_type):
    db = get_db()

    if followup_type not in ["6_month", "1_year"]:
        flash("Invalid follow up type", "error")
        return redirect(url_for("case_management.resident_case", enrollment_id=enrollment_id))

    existing = db.execute(
        """
        SELECT *
        FROM followups
        WHERE enrollment_id = %s AND followup_type = %s
        ORDER BY followup_date DESC
        LIMIT 1
        """,
        (enrollment_id, followup_type),
    ).fetchone()

    return render_template(
        "case_management/followup_assessment.html",
        enrollment_id=enrollment_id,
        followup_type=followup_type,
        data=existing,
    )


@followups_bp.route("/<int:enrollment_id>/<string:followup_type>/submit", methods=["POST"])
@require_login
def submit_followup(enrollment_id, followup_type):
    db = get_db()

    if followup_type not in ["6_month", "1_year"]:
        flash("Invalid follow up type", "error")
        return redirect(url_for("case_management.resident_case", enrollment_id=enrollment_id))

    income = request.form.get("income_at_followup")
    sober = request.form.get("sober_at_followup")
    notes = request.form.get("notes")

    updated_grit = request.form.get("updated_grit")
    received_counseling = request.form.get("received_counseling")
    parenting_completed = request.form.get("parenting_class_completed")
    warrants_paid = request.form.get("warrants_paid")
    mailing_address = request.form.get("mailing_address")

    db.execute(
        """
        INSERT INTO followups (
            enrollment_id,
            followup_type,
            followup_date,
            income_at_followup,
            sober_at_followup,
            updated_grit,
            received_counseling,
            parenting_class_completed,
            warrants_paid,
            mailing_address,
            notes
        )
        VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            enrollment_id,
            followup_type,
            income,
            sober,
            updated_grit,
            received_counseling,
            parenting_completed,
            warrants_paid,
            mailing_address,
            notes,
        ),
    )

    db.commit()

    flash("Follow up saved successfully", "success")

    return redirect(url_for("case_management.resident_case", enrollment_id=enrollment_id))
