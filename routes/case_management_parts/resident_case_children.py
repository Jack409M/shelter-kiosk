from __future__ import annotations

from flask import current_app

from core.db import db_fetchall
from core.helpers import fmt_dt
from routes.case_management_parts.helpers import placeholder


def display_label(value: str | None) -> str:
    if not value:
        return "—"

    normalized = value.replace("_", " ").strip().lower()

    special_map = {
        "full_time": "Full time",
        "part_time": "Part time",
        "drug_of_choice": "Drug of choice",
        "vision_glasses": "Vision/Glasses",
        "state_id_drivers_license": "State ID/Driver’s License",
        "food_stamps_snap": "Food Stamps/SNAP",
        "jo_wyatt": "JO Wyatt",
        "rhn_physical": "RHN Physical",
        "pap_smear": "Pap Smear",
        "legal_assistance": "Legal assistance",
    }

    if value in special_map:
        return special_map[value]
    if normalized in special_map:
        return special_map[normalized]

    return normalized[:1].upper() + normalized[1:]


def display_quantity_unit(quantity, unit: str | None) -> str:
    if quantity is None and not unit:
        return "—"
    if quantity is None:
        return display_label(unit)
    unit_clean = (unit or "").strip()
    if not unit_clean:
        return str(quantity)
    return f"{quantity} {unit_clean}"


def normalize_child_service_row(service):
    return {
        "resident_child_id": service.get("resident_child_id"),
        "service_type": service.get("service_type"),
        "service_type_display": display_label(service.get("service_type")),
        "outcome": service.get("outcome"),
        "outcome_display": display_label(service.get("outcome")),
        "quantity": service.get("quantity"),
        "unit": service.get("unit"),
        "quantity_display": display_quantity_unit(service.get("quantity"), service.get("unit")),
        "notes": service.get("notes"),
        "service_date": service.get("service_date"),
        "service_date_display": fmt_dt(service.get("service_date")),
    }


def load_children_with_services(resident_id: int) -> list[dict]:
    ph = placeholder()

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
            child_services = [normalize_child_service_row(service) for service in child_services_raw]

        services_by_child = {}
        for service in child_services:
            child_id = service["resident_child_id"]
            services_by_child.setdefault(child_id, []).append(service)

        enriched_children = []
        for child in children:
            child_id = child["id"]
            child_obj = dict(child)
            child_obj["relationship_display"] = display_label(child.get("relationship"))
            child_obj["living_status_display"] = display_label(child.get("living_status"))
            child_obj["services"] = services_by_child.get(child_id, [])
            enriched_children.append(child_obj)

        return enriched_children
    except Exception:
        current_app.logger.exception(
            "Failed to load child or child service data for resident_id=%s",
            resident_id,
        )
        return []
