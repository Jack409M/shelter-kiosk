from __future__ import annotations

from flask import current_app, flash, redirect, render_template, session, url_for

from core.db import db_fetchall, db_fetchone
from core.helpers import fmt_dt
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.needs import get_open_enrollment_needs
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot


SUMMARY_GROUP_ORDER = [
    "child",
    "medication",
    "service",
    "need_addressed",
    "need_outstanding",
    "employment",
    "sobriety",
]

SUMMARY_GROUP_LABELS = {
    "child": "Children Changes",
    "medication": "Medication Changes",
    "service": "Services Provided",
    "need_addressed": "Needs Taken Care Of",
    "need_outstanding": "Needs Still Outstanding",
    "employment": "Employment Changes",
    "sobriety": "Sobriety Changes",
}


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


def _load_current_enrollment(resident_id: int):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY
            CASE
                WHEN COALESCE(program_status, '') = 'active' THEN 0
                ELSE 1
            END,
            COALESCE(entry_date, '') DESC,
            id DESC
        LIMIT 1
        """,
        (resident_id,),
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


def _normalize_summary_row(row):
    return {
        "change_group": row.get("change_group"),
        "change_group_label": SUMMARY_GROUP_LABELS.get(
            row.get("change_group"),
            _display_label(row.get("change_group")),
        ),
        "change_type": row.get("change_type"),
        "change_type_display": _display_label(row.get("change_type")),
        "item_key": row.get("item_key"),
        "item_label": row.get("item_label") or "—",
        "old_value": row.get("old_value"),
        "new_value": row.get("new_value"),
        "detail": row.get("detail"),
        "sort_order": row.get("sort_order") or 0,
    }


def _group_summary_rows(rows: list[dict]) -> list[dict]:
    grouped = {group_key: [] for group_key in SUMMARY_GROUP_ORDER}
    extra_groups: dict[str, list[dict]] = {}

    for row in rows:
        group_key = row.get("change_group") or ""
        if group_key in grouped:
            grouped[group_key].append(row)
        else:
            extra_groups.setdefault(group_key, []).append(row)

    result = []

    for group_key in SUMMARY_GROUP_ORDER:
        items = grouped.get(group_key, [])
        display_items = [item for item in items if item.get("change_type") != "snapshot"]
        if not display_items:
            continue
        result.append(
            {
                "group_key": group_key,
                "group_label": SUMMARY_GROUP_LABELS.get(group_key, _display_label(group_key)),
                "items": display_items,
            }
        )

    for group_key in sorted(extra_groups.keys()):
        items = [item for item in extra_groups[group_key] if item.get("change_type") != "snapshot"]
        if not items:
            continue
        result.append(
            {
                "group_key": group_key,
                "group_label": SUMMARY_GROUP_LABELS.get(group_key, _display_label(group_key)),
                "items": items,
            }
        )

    return result


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

    enrollment = _load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    goals = []
    appointments = []
    notes = []
    services = []
    children = []
    family_snapshot = None
    intake_assessment = None
    exit_assessment = None
    grit_difference = None
    followup_6_month = None
    followup_1_year = None
    open_needs = []
    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)

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
                  AND COALESCE(is_deleted, FALSE) = FALSE
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

        open_needs = get_open_enrollment_needs(enrollment_id)

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

        notes_raw = db_fetchall(
            f"""
            SELECT
                id,
                meeting_date,
                notes,
                progress_notes,
                action_items,
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

        services_by_note = {}
        for s in services_raw:
            note_id = s["case_manager_update_id"]
            service = {
                "service_type": s["service_type"],
                "service_date": s["service_date"],
                "quantity": s["quantity"],
                "unit": s["unit"],
                "quantity_display": _display_quantity_unit(s["quantity"], s["unit"]),
                "notes": s["notes"],
            }
            services_by_note.setdefault(note_id, []).append(service)

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

        summary_by_note = {}
        for row in summary_rows_raw:
            note_id = row["case_manager_update_id"]
            summary_by_note.setdefault(note_id, []).append(_normalize_summary_row(row))

        notes = []
        for n in notes_raw:
            note_id = n["id"]
            note_obj = dict(n)
            note_obj["services"] = services_by_note.get(note_id, [])
            note_obj["summary_rows"] = summary_by_note.get(note_id, [])
            note_obj["summary_groups"] = _group_summary_rows(note_obj["summary_rows"])
            notes.append(note_obj)

        services = services_raw
        followup_6_month = _get_latest_followup(enrollment_id, "6_month")
        followup_1_year = _get_latest_followup(enrollment_id, "1_year")

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        family_snapshot=family_snapshot,
        intake_assessment=intake_assessment,
        exit_assessment=exit_assessment,
        grit_difference=grit_difference,
        goals=goals,
        appointments=appointments,
        notes=notes,
        services=services,
        children=children,
        open_needs=open_needs,
        recovery_snapshot=recovery_snapshot,
        followup_6_month=followup_6_month,
        followup_1_year=followup_1_year,
    )
