from __future__ import annotations


ALLOWED_SERVICE_TYPES = {
    "Counseling",
    "Dental",
    "Vision",
    "Legal Assistance",
    "Transportation",
    "Daycare",
    "Other",
}


EMPLOYMENT_FIELD_LABELS = {
    "employment_status_current": "employment status",
    "employment_type_current": "employment type",
    "employer_name": "employer",
    "supervisor_name": "supervisor",
    "supervisor_phone": "supervisor phone",
    "monthly_income": "monthly income",
    "unemployment_reason": "unemployment reason",
    "employment_notes": "employment notes",
}


SOBRIETY_FIELD_LABELS = {
    "sobriety_date": "sobriety date",
    "drug_of_choice": "drug of choice",
    "treatment_graduation_date": "treatment graduation date",
}


ADVANCEMENT_BOOL_FIELD_LABELS = {
    "ready_for_next_level": "readiness for next level",
}


ADVANCEMENT_TEXT_FIELD_LABELS = {
    "recommended_next_level": "recommended next level",
    "blocker_reason": "barrier to advancement",
    "override_or_exception": "override or exception",
    "staff_review_note": "staff review note",
}


MEETING_TEXT_FIELD_LABELS = {
    "setbacks_or_incidents": "setbacks or incidents",
}


def clean_service_types(raw_values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        service_type = (value or "").strip()
        if not service_type:
            continue
        if service_type not in ALLOWED_SERVICE_TYPES:
            continue
        if service_type in seen:
            continue
        seen.add(service_type)
        cleaned.append(service_type)

    return cleaned


def yes_no_to_int(value: str | None):
    value = (value or "").strip().lower()
    if value == "yes":
        return 1
    if value == "no":
        return 0
    return None


def parse_quantity(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_grit(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    try:
        grit_value = int(value)
    except ValueError:
        return None
    if grit_value < 0 or grit_value > 100:
        return None
    return grit_value


def display_label(value: str | None) -> str:
    if not value:
        return "—"

    normalized = value.replace("_", " ").strip().lower()

    special_map = {
        "yes": "Yes",
        "no": "No",
        "not applicable": "Not applicable",
        "all resolved": "All resolved",
        "need addressed": "Need addressed",
        "need outstanding": "Need outstanding",
        "legal assistance": "Legal assistance",
        "drug of choice": "Drug of choice",
        "staff review note": "Staff review note",
        "override or exception": "Override or exception",
        "blocker reason": "Barrier to advancement",
        "ready for next level": "Ready for next level",
        "recommended next level": "Recommended next level",
        "setbacks or incidents": "Setbacks or incidents",
        "sobriety date": "Sobriety date",
        "treatment graduation date": "Treatment graduation date",
        "monthly income": "Monthly income",
        "employment status": "Employment status",
        "employment type": "Employment type",
        "supervisor phone": "Supervisor phone",
    }

    if normalized in special_map:
        return special_map[normalized]

    return normalized[:1].upper() + normalized[1:]


def display_quantity_unit(quantity, unit: str | None) -> str:
    if quantity is None and not unit:
        return "—"
    if quantity is None:
        return (unit or "").strip() or "—"

    unit_clean = (unit or "").strip()
    if not unit_clean:
        return str(quantity)

    return f"{quantity} {unit_clean}"


def clean_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()
