from __future__ import annotations

from datetime import UTC, datetime

from flask import flash, redirect, url_for

from core.admin_rbac import require_admin_role
from core.db import db_execute, db_fetchone, db_transaction
from routes.case_management_parts.helpers import placeholder


def fix_missing_family_baseline_view(enrollment_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ph = placeholder()

    existing = db_fetchone(
        f"SELECT id FROM family_snapshots WHERE enrollment_id = {ph} LIMIT 1",
        (enrollment_id,),
    )

    if existing:
        flash("Family baseline already exists.", "info")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        db_execute(
            f"""
            INSERT INTO family_snapshots
            (
                enrollment_id,
                kids_at_dwc,
                kids_served_outside_under_18,
                kids_ages_0_5,
                kids_ages_6_11,
                kids_ages_12_17,
                kids_reunited_while_in_program,
                healthy_babies_born_at_dwc,
                created_at,
                updated_at
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (
                enrollment_id,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                now,
                now,
            ),
        )

    flash("Family baseline created. Complete details in intake edit.", "success")
    return redirect(url_for("admin.admin_system_health_data_quality"))
