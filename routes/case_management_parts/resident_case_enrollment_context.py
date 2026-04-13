from __future__ import annotations

from core.db import db_fetchall
from core.db import db_fetchone
from core.db import db_transaction
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.intake_income_support import load_intake_income_support
from routes.case_management_parts.needs import get_open_enrollment_needs
from routes.case_management_parts.resident_case_notes import build_note_objects


def get_latest_followup(enrollment_id: int, followup_type: str):
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


def load_case_history(enrollment_id: int):
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


def normalize_exit_assessment(row):
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


def is_deceased_exit(exit_assessment) -> bool:
    if not exit_assessment:
        return False

    return (
        str(exit_assessment.get("exit_category") or "").strip() == "Administrative Exit"
        and str(exit_assessment.get("exit_reason") or "").strip() == "Deceased"
    )


def load_family_snapshot(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
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


def load_intake_assessment(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
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
            has_social_security_card,
            employment_status_at_entry,
            income_at_entry
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


def load_exit_assessment(enrollment_id: int):
    ph = placeholder()
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
    return normalize_exit_assessment(raw_exit_assessment)


def load_goals(enrollment_id: int):
    ph = placeholder()
    return db_fetchall(
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


def load_appointments(enrollment_id: int):
    ph = placeholder()
    return db_fetchall(
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


def _load_deceased_filtered_context(enrollment_id: int, exit_assessment):
    is_deceased_case = is_deceased_exit(exit_assessment)

    if is_deceased_case:
        return {
            "open_needs": [],
            "followup_6_month": None,
            "followup_1_year": None,
            "is_deceased_case": True,
        }

    return {
        "open_needs": get_open_enrollment_needs(enrollment_id),
        "followup_6_month": get_latest_followup(enrollment_id, "6_month"),
        "followup_1_year": get_latest_followup(enrollment_id, "1_year"),
        "is_deceased_case": False,
    }


def load_enrollment_context(enrollment_id: int) -> dict:
    with db_transaction():
        family_snapshot = load_family_snapshot(enrollment_id)
        intake_assessment = load_intake_assessment(enrollment_id)
        intake_income_support = load_intake_income_support(enrollment_id)
        exit_assessment = load_exit_assessment(enrollment_id)
        goals = load_goals(enrollment_id)
        appointments = load_appointments(enrollment_id)
        notes, services = load_case_history(enrollment_id)
        deceased_filtered_context = _load_deceased_filtered_context(
            enrollment_id,
            exit_assessment,
        )

    return {
        "family_snapshot": family_snapshot,
        "intake_assessment": intake_assessment,
        "intake_income_support": intake_income_support,
        "exit_assessment": exit_assessment,
        "goals": goals,
        "appointments": appointments,
        "notes": notes,
        "services": services,
        "open_needs": deceased_filtered_context["open_needs"],
        "followup_6_month": deceased_filtered_context["followup_6_month"],
        "followup_1_year": deceased_filtered_context["followup_1_year"],
        "is_deceased_case": deceased_filtered_context["is_deceased_case"],
    }


def base_empty_enrollment_context() -> dict:
    return {
        "family_snapshot": None,
        "intake_assessment": None,
        "intake_income_support": None,
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


def calculate_grit_difference(intake_assessment, exit_assessment):
    intake_grit = intake_assessment.get("grit_score") if intake_assessment else None
    exit_grit = exit_assessment.get("grit_at_exit") if exit_assessment else None

    if intake_grit is None or exit_grit is None:
        return None

    return exit_grit - intake_grit
    
