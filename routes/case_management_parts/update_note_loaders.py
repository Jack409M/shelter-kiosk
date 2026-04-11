from __future__ import annotations

from core.db import db_fetchall
from core.db import db_fetchone
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def get_resident_and_enrollment_in_scope(resident_id: int, shelter: str):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT id, resident_identifier
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        return None, None

    enrollment = fetch_current_enrollment_for_resident(resident_id, columns="id")
    return resident, enrollment


def load_note_for_edit(update_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT cmu.*, pe.resident_id
        FROM case_manager_updates cmu
        JOIN program_enrollments pe ON pe.id = cmu.enrollment_id
        WHERE cmu.id = {ph}
        """,
        (update_id,),
    )


def load_services_for_note(update_id: int):
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT service_type, quantity, unit, notes
        FROM client_services
        WHERE case_manager_update_id = {ph}
        """,
        (update_id,),
    )


def build_edit_service_maps(services: list[dict]):
    selected_services = []
    service_notes_map = {}
    service_quantity_map = {}
    service_unit_map = {}

    for service in services:
        service_type = service["service_type"]
        quantity = service["quantity"]
        unit = service["unit"]
        service_note = service["notes"]

        selected_services.append(service_type)
        service_notes_map[service_type] = service_note or ""
        service_quantity_map[service_type] = quantity if quantity is not None else ""
        service_unit_map[service_type] = unit or ""

    return {
        "selected_services": selected_services,
        "service_notes_map": service_notes_map,
        "service_quantity_map": service_quantity_map,
        "service_unit_map": service_unit_map,
    }
