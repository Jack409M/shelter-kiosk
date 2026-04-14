from __future__ import annotations

from flask import current_app

from core.db import db_fetchall
from core.helpers import fmt_dt
from routes.case_management_parts.helpers import placeholder


DISPLAY_EMPTY = "—"

SPECIAL_LABELS = {
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


def display_label(value: str | None) -> str:
    if not value:
        return DISPLAY_EMPTY

    raw = str(value).strip()
    normalized = raw.replace("_", " ").strip().lower()
    normalized_key = raw.strip().lower()

    if raw in SPECIAL_LABELS:
        return SPECIAL_LABELS[raw]
    if normalized_key in SPECIAL_LABELS:
        return SPECIAL_LABELS[normalized_key]

    return normalized[:1].upper() + normalized[1:] if normalized else DISPLAY_EMPTY


def display_quantity_unit(quantity, unit: str | None) -> str:
    if quantity is None and not unit:
        return DISPLAY_EMPTY
    if quantity is None:
        return display_label(unit)

    unit_clean = (unit or "").strip()
    if not unit_clean:
        return str(quantity)

    return f"{quantity} {unit_clean}"


def normalize_child_service_row(service: dict) -> dict:
    return {
        "resident_child_id": service.get("resident_child_id"),
        "service_type": service.get("service_type"),
        "service_type_display": display_label(service.get("service_type")),
        "outcome": service.get("outcome"),
        "outcome_display": display_label(service.get("outcome")),
        "quantity": service.get("quantity"),
        "unit": service.get("unit"),
        "quantity_display": display_quantity_unit(
            service.get("quantity"),
            service.get("unit"),
        ),
        "notes": service.get("notes"),
        "service_date": service.get("service_date"),
        "service_date_display": fmt_dt(service.get("service_date")),
    }


def _load_children(resident_id: int) -> list[dict]:
    ph = placeholder()

    return db_fetchall(
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


def _load_child_services(child_ids: list[int]) -> list[dict]:
    if not child_ids:
        return []

    ph = placeholder()
    child_placeholders = ",".join([ph] * len(child_ids))

    rows = db_fetchall(
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

    return [normalize_child_service_row(service) for service in rows]


def _group_services_by_child(child_services: list[dict]) -> dict[int, list[dict]]:
    services_by_child: dict[int, list[dict]] = {}

    for service in child_services:
        child_id = service["resident_child_id"]
        services_by_child.setdefault(child_id, []).append(service)

    return services_by_child


def _enrich_child(child: dict, services_by_child: dict[int, list[dict]]) -> dict:
    child_id = child["id"]

    return {
        **dict(child),
        "relationship_display": display_label(child.get("relationship")),
        "living_status_display": display_label(child.get("living_status")),
        "services": services_by_child.get(child_id, []),
    }


def load_children_with_services(resident_id: int) -> list[dict]:
    try:
        children = _load_children(resident_id)
        child_ids = [child["id"] for child in children]
        child_services = _load_child_services(child_ids)
        services_by_child = _group_services_by_child(child_services)

        return [
            _enrich_child(child, services_by_child)
            for child in children
        ]
    except Exception:
        current_app.logger.exception(
            "Failed to load child or child service data for resident_id=%s",
            resident_id,
        )
        return []
