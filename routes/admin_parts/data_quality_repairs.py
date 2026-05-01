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


def close_active_enrollment_for_inactive_resident_view(enrollment_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.program_status,
            r.is_active
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE pe.id = {ph}
          AND LOWER(TRIM(COALESCE(pe.program_status, ''))) = 'active'
          AND NOT (
              COALESCE(LOWER(TRIM(CAST(r.is_active AS TEXT))), '') IN ('1', 'true', 't', 'yes')
          )
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if not row:
        flash("No inactive resident with active enrollment was found. No repair was made.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        db_execute(
            f"""
            UPDATE program_enrollments
            SET program_status = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            ("inactive", now, enrollment_id),
        )

    flash("Active enrollment closed for inactive resident.", "success")
    return redirect(url_for("admin.admin_system_health_data_quality"))
