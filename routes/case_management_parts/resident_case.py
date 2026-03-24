from __future__ import annotations

from flask import current_app, flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.helpers import fmt_dt
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


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

    return row if row else None


def _display_label(value: str | None) -> str:
    if not value:
        return "—"
    return value.replace("_", " ").strip().title()


def _display_quantity_unit(quantity, unit: str | None) -> str:
    if quantity is None and not unit:
        return "—"
    if quantity is None:
        return _display_label(unit)

    unit_clean = (unit or "").strip()
    if not unit_clean:
        return str(quantity)

    return f"{quantity} {unit_clean}"


def _normalize_child_service_row(service):
    return {
        "resident_child_id": service.get("resident_child_id"),
        "service_type": service.get("service_type"),
        "service_type_display": _display_label(service.get("service_type")),
        "outcome": service.get("outcome"),
        "outcome_display": _display_label(service.get("outcome")),
        "quantity": service.get("quantity"),
        "unit": service.get("unit"),
        "quantity_display": _display_quantity_unit(service.get("quantity"), service.get("unit")),
        "notes": service.get("notes"),
        "service_date": service.get("service_date"),
        "service_date_display": fmt_dt(service.get("service_date")),
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

    enrollment_id = enrollment["id"] if enrollment else None

    goals = []
    appointments = []
    notes = []
    services = []
    children = []
    intake_assessment = None
    exit_assessment = None
    grit_difference = None
    followup_6_month = None
    followup_1_year = None

    try:
        children = db_fetchall(
            f"""
            SELECT
                id,
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                is_active
            FROM resident_children
            WHERE resident_id = {ph}
              AND is_active = TRUE
            ORDER BY id ASC
            """,
            (resident_id,),
        )

        child_ids = [child["id"] for child in children]

        child_services = []

        if child_ids:
            child_placeholders = ",".join([ph] * len(child_ids))
            child_services_raw = db_fetchall(
                f"""
                SELECT
                    resident_child_id,
                    service_type,
                    outcome,
                    quantity,
                    unit,
                    notes,
                    service_date
                FROM child_services
                WHERE resident_child_id IN ({child_placeholders})
                ORDER BY service_date DESC, id DESC
                """,
                tuple(child_ids),
            )
            child_services = [_normalize_child_service_row(service) for service in child_services_raw]

        services_by_child = {}

        for service in child_services:
            child_id = service["resident_child_id"]
            services_by_child.setdefault(child_id, []).append(service)

        enriched_children = []

        for child in children:
            child_id = child["id"]
            child_obj = dict(child)
            child_obj["relationship_display"] = _display_label(child.get("relationship"))
            child_obj["living_status_display"] = _display_label(child.get("living_status"))
            child_obj["services"] = services_by_child.get(child_id, [])
            enriched_children.append(child_obj)

        children = enriched_children
    except Exception:
        current_app.logger.exception(
            "Failed to load child or child service data for resident_id=%s",
            resident_id,
        )
        children = []

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

        intake_grit = intake_assessment.get("grit_score") if intake_assessment else None
        exit_grit = exit_assessment.get("grit_at_exit") if exit_assessment else None

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
                notes
            FROM client_services
            WHERE enrollment_id = {ph}
            ORDER BY service_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        services_by_note = {}

        for s in services_raw:
            note_id = s["case_manager_update_id"]
            service = {
                "service_type": s["service_type"],
                "service_date": s["service_date"],
                "notes": s["notes"],
            }
            services_by_note.setdefault(note_id, []).append(service)

        notes = []

        for n in notes_raw:
            note_id = n["id"]
            note_obj = dict(n)
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
        children=children,
        followup_6_month=followup_6_month,
        followup_1_year=followup_1_year,
    )
