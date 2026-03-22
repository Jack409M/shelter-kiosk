from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _normalize_exit_assessment(row):
    if not row:
        return None

    if isinstance(row, dict):
        leave_ama = row.get("leave_ama")
        leave_amarillo_city = row.get("leave_amarillo_city")
        leave_amarillo_unknown = row.get("leave_amarillo_unknown")

        destination = None
        if leave_ama:
            if leave_amarillo_city:
                destination = leave_amarillo_city
            elif leave_amarillo_unknown:
                destination = "Unknown"

        normalized = dict(row)
        normalized["leave_ama_destination"] = destination
        return normalized

    leave_ama = row[5]
    leave_amarillo_city = row[6]
    leave_amarillo_unknown = row[7]

    destination = None
    if leave_ama:
        if leave_amarillo_city:
            destination = leave_amarillo_city
        elif leave_amarillo_unknown:
            destination = "Unknown"

    return {
        "date_graduated": row[0],
        "date_exit_dwc": row[1],
        "exit_category": row[2],
        "exit_reason": row[3],
        "graduate_dwc": row[4],
        "leave_ama": row[5],
        "leave_amarillo_city": row[6],
        "leave_amarillo_unknown": row[7],
        "leave_ama_destination": destination,
        "income_at_exit": row[8],
        "education_at_exit": row[9],
        "grit_at_exit": row[10],
        "received_car": row[11],
        "car_insurance": row[12],
        "dental_needs_met": row[13],
        "vision_needs_met": row[14],
        "obtained_public_insurance": row[15],
        "private_insurance": row[16],
    }


def _get_latest_followup(enrollment_id: int, followup_type: str):
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            followup_date,
            income_at_followup,
            sober_at_followup,
            notes
        FROM followups
        WHERE enrollment_id = {ph}
          AND followup_type = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id, followup_type),
    )

    if not row:
        return None

    if isinstance(row, dict):
        return row

    return {
        "followup_date": row[0],
        "income_at_followup": row[1],
        "sober_at_followup": row[2],
        "notes": row[3],
    }


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
    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    goals = []
    appointments = []
    notes = []
    services = []
    intake_assessment = None
    exit_assessment = None
    grit_difference = None
    followup_6_month = None
    followup_1_year = None

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

        raw_exit_assessment = db_fetchone(
            f"""
            SELECT
                date_graduated,
                date_exit_dwc,
                exit_category,
                exit_reason,
                graduate_dwc,
                leave_ama,
                leave_amarillo_city,
                leave_amarillo_unknown,
                income_at_exit,
                education_at_exit,
                grit_at_exit,
                received_car,
                car_insurance,
                dental_needs_met,
                vision_needs_met,
                obtained_public_insurance,
                private_insurance
            FROM exit_assessments
            WHERE enrollment_id = {ph}
            LIMIT 1
            """,
            (enrollment_id,),
        )

        exit_assessment = _normalize_exit_assessment(raw_exit_assessment)

        intake_grit = None
        exit_grit = None

        if intake_assessment:
            intake_grit = (
                intake_assessment["grit_score"]
                if isinstance(intake_assessment, dict)
                else intake_assessment[0]
            )

        if exit_assessment:
            exit_grit = exit_assessment.get("grit_at_exit")

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

        notes_raw = db_fetchall(
            f"""
            SELECT
                id,
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

        services_raw = db_fetchall(
            f"""
            SELECT
                case_manager_update_id,
                service_type,
                service_date,
                notes
            FROM client_services
            WHERE enrollment_id = {ph}
            ORDER BY service_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        services_by_note = {}

        for s in services_raw:
            if isinstance(s, dict):
                note_id = s["case_manager_update_id"]
                service = {
                    "service_type": s["service_type"],
                    "service_date": s["service_date"],
                    "notes": s["notes"],
                }
            else:
                note_id = s[0]
                service = {
                    "service_type": s[1],
                    "service_date": s[2],
                    "notes": s[3],
                }

            services_by_note.setdefault(note_id, []).append(service)

        notes = []

        for n in notes_raw:
            if isinstance(n, dict):
                note_id = n["id"]
                note_obj = dict(n)
            else:
                note_id = n[0]
                note_obj = {
                    "id": n[0],
                    "meeting_date": n[1],
                    "notes": n[2],
                    "progress_notes": n[3],
                    "action_items": n[4],
                    "created_at": n[5],
                }

            note_obj["services"] = services_by_note.get(note_id, [])
            notes.append(note_obj)

        services = services_raw

        followup_6_month = _get_latest_followup(enrollment_id, "6_month")
        followup_1_year = _get_latest_followup(enrollment_id, "1_year")

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
        services=services,
        followup_6_month=followup_6_month,
        followup_1_year=followup_1_year,
    )
