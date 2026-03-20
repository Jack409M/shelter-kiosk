from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def resident_case_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = None
    intake_assessment = None
    exit_assessment = None
    grit_difference = None

    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    goals = []
    appointments = []
    notes = []

    if enrollment_id:
        intake_assessment = db_fetchone(
            f"""
            SELECT
                grit_score
            FROM intake_assessments
            WHERE enrollment_id = {ph}
            LIMIT 1
            """,
            (enrollment_id,),
        )

        exit_assessment = db_fetchone(
            f"""
            SELECT
                date_graduated,
                date_exit_dwc,
                exit_reason,
                graduate_dwc,
                leave_ama,
                income_at_exit,
                education_at_exit,
                grit_at_exit,
                received_car,
                car_insurance,
                dental_needs_met,
                vision_needs_met,
                obtained_insurance
            FROM exit_assessments
            WHERE enrollment_id = {ph}
            LIMIT 1
            """,
            (enrollment_id,),
        )

        intake_grit = None
        exit_grit = None

        if intake_assessment:
            intake_grit = (
                intake_assessment.get("grit_score")
                if isinstance(intake_assessment, dict)
                else intake_assessment[0]
            )

        if exit_assessment:
            exit_grit = (
                exit_assessment.get("grit_at_exit")
                if isinstance(exit_assessment, dict)
                else exit_assessment[7]
            )

        if intake_grit is not None and exit_grit is not None:
            grit_difference = exit_grit - intake_grit

        goals = db_fetchall(
            f"""
            SELECT
                goal_text,
                status,
                target_date,
                created_at
            FROM goals
            WHERE enrollment_id = {ph}
            ORDER BY created_at DESC
            """,
            (enrollment_id,),
        )

        appointments = db_fetchall(
            f"""
            SELECT
                appointment_date,
                appointment_type,
                notes
            FROM appointments
            WHERE enrollment_id = {ph}
            ORDER BY appointment_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        notes = db_fetchall(
            f"""
            SELECT
                meeting_date,
                notes,
                progress_notes,
                action_items,
                created_at
            FROM case_manager_updates
            WHERE enrollment_id = {ph}
            ORDER BY meeting_date DESC, id DESC
            """,
            (enrollment_id,),
        )

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        intake_assessment=intake_assessment,
        exit_assessment=exit_assessment,
        grit_difference=grit_difference,
        goals=goals,
        appointments=appointments,
        notes=notes,
    )
