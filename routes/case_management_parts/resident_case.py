from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.needs import get_open_enrollment_needs
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_children import load_children_with_services
from routes.case_management_parts.resident_case_notes import build_note_objects
from routes.case_management_parts.resident_case_viewmodel import build_meeting_defaults
from routes.case_management_parts.resident_case_viewmodel import build_operations_snapshot
from routes.case_management_parts.resident_case_viewmodel import build_workspace_header
from routes.inspection_v2 import build_inspection_stability_snapshot
from routes.rent_tracking import build_rent_stability_snapshot


def _normalize_exit_assessment(row):
    if not row:
        return None

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


def _is_deceased_exit(exit_assessment) -> bool:
    if not exit_assessment:
        return False
    return (
        str(exit_assessment.get("exit_category") or "").strip() == "Administrative Exit"
        and str(exit_assessment.get("exit_reason") or "").strip() == "Deceased"
    )


def _load_current_enrollment(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        """,
    )


def _load_resident_in_scope(resident_id: int, shelter: str):
    ph = placeholder()

    return db_fetchone(
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
        ORDER BY
            COALESCE(followup_date, '') DESC,
            id DESC
        LIMIT 1
        """,
        (enrollment_id, followup_type),
    )

    return row if row else None


def _load_case_history(enrollment_id: int):
    ph = placeholder()

    notes_raw = db_fetchall(
        f"""
        SELECT
            id,
            meeting_date,
            notes,
            progress_notes,
            setbacks_or_incidents,
            action_items,
            next_appointment,
            overall_summary,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            created_at
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
        ORDER BY meeting_date ASC, id ASC
        """,
        (enrollment_id,),
    )

    services_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            service_type,
            service_date,
            quantity,
            unit,
            notes
        FROM client_services
        WHERE enrollment_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (enrollment_id,),
    )

    note_ids = [note["id"] for note in notes_raw]
    summary_rows_raw = []

    if note_ids:
        note_placeholders = ",".join([ph] * len(note_ids))
        summary_rows_raw = db_fetchall(
            f"""
            SELECT
                case_manager_update_id,
                change_group,
                change_type,
                item_key,
                item_label,
                old_value,
                new_value,
                detail,
                sort_order
            FROM case_manager_update_summary
            WHERE case_manager_update_id IN ({note_placeholders})
            ORDER BY case_manager_update_id ASC, sort_order ASC, id ASC
            """,
            tuple(note_ids),
        )

    return build_note_objects(notes_raw, services_raw, summary_rows_raw)


def _load_enrollment_context(enrollment_id: int):
    ph = placeholder()

    family_snapshot = db_fetchone(
        f"""
        SELECT
            id,
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
        FROM family_snapshots
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    intake_assessment = db_fetchone(
        f"""
        SELECT
            grit_score,
            sobriety_date,
            treatment_grad_date,
            dental_need_at_entry,
            vision_need_at_entry,
            parenting_class_needed,
            warrants_unpaid,
            mental_health_need_at_entry,
            medical_need_at_entry,
            has_drivers_license,
            has_social_security_card
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
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
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    goals = db_fetchall(
        f"""
        SELECT
            goal_text,
            status,
            target_date,
            created_at
        FROM goals
        WHERE enrollment_id = {ph}
        ORDER BY created_at DESC, id DESC
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

    notes, services = _load_case_history(enrollment_id)
    exit_assessment = _normalize_exit_assessment(raw_exit_assessment)
    is_deceased_case = _is_deceased_exit(exit_assessment)

    return {
        "family_snapshot": family_snapshot,
        "intake_assessment": intake_assessment,
        "exit_assessment": exit_assessment,
        "goals": goals,
        "appointments": appointments,
        "notes": notes,
        "services": services,
        "open_needs": [] if is_deceased_case else get_open_enrollment_needs(enrollment_id),
        "followup_6_month": None if is_deceased_case else _get_latest_followup(enrollment_id, "6_month"),
        "followup_1_year": None if is_deceased_case else _get_latest_followup(enrollment_id, "1_year"),
        "is_deceased_case": is_deceased_case,
    }


def _calculate_grit_difference(intake_assessment, exit_assessment):
    intake_grit = intake_assessment.get("grit_score") if intake_assessment else None
    exit_grit = exit_assessment.get("grit_at_exit") if exit_assessment else None

    if intake_grit is None or exit_grit is None:
        return None

    return exit_grit - intake_grit


def resident_case_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    resident = _load_resident_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = _load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    children = load_children_with_services(resident_id)
    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)

    enrollment_context = {
        "family_snapshot": None,
        "intake_assessment": None,
        "exit_assessment": None,
        "goals": [],
        "appointments": [],
        "notes": [],
        "services": [],
        "open_needs": [],
        "followup_6_month": None,
        "followup_1_year": None,
        "is_deceased_case": False,
    }

    if enrollment_id:
        enrollment_context = _load_enrollment_context(enrollment_id)

    grit_difference = _calculate_grit_difference(
        enrollment_context["intake_assessment"],
        enrollment_context["exit_assessment"],
    )

    meeting_defaults = build_meeting_defaults(
        intake_assessment=enrollment_context["intake_assessment"],
        family_snapshot=enrollment_context["family_snapshot"],
        recovery_snapshot=recovery_snapshot,
        open_needs=enrollment_context["open_needs"],
        notes=enrollment_context["notes"],
        appointments=enrollment_context["appointments"],
    )

    workspace_header = build_workspace_header(
        resident=resident,
        enrollment=enrollment,
        recovery_snapshot=recovery_snapshot,
        open_needs=enrollment_context["open_needs"],
    )

    operations_snapshot = build_operations_snapshot(recovery_snapshot)
    rent_snapshot = build_rent_stability_snapshot(resident_id)
    inspection_snapshot = build_inspection_stability_snapshot(resident_id, shelter=shelter)

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        family_snapshot=enrollment_context["family_snapshot"],
        intake_assessment=enrollment_context["intake_assessment"],
        exit_assessment=enrollment_context["exit_assessment"],
        grit_difference=grit_difference,
        goals=enrollment_context["goals"],
        appointments=enrollment_context["appointments"],
        notes=enrollment_context["notes"],
        services=enrollment_context["services"],
        children=children,
        open_needs=enrollment_context["open_needs"],
        recovery_snapshot=recovery_snapshot,
        followup_6_month=enrollment_context["followup_6_month"],
        followup_1_year=enrollment_context["followup_1_year"],
        meeting_defaults=meeting_defaults,
        workspace_header=workspace_header,
        operations_snapshot=operations_snapshot,
        rent_snapshot=rent_snapshot,
        inspection_snapshot=inspection_snapshot,
        is_deceased_case=enrollment_context["is_deceased_case"],
    )
