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
    "setbacks_or_incidents": "barriers and concerns",
}


DISPLAY_LABEL_MAP = {
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
    "readiness for next level": "Ready for next level",
    "recommended next level": "Recommended next level",
    "setbacks or incidents": "Barriers and concerns",
    "barriers and concerns": "Barriers and concerns",
    "sobriety date": "Sobriety date",
    "treatment graduation date": "Treatment graduation date",
    "monthly income": "Monthly income",
    "employment status": "Employment status",
    "employment type": "Employment type",
    "supervisor phone": "Supervisor phone",
}


def clean_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_text(value: str | None) -> str:
    return clean_value(value)


def clean_service_types(raw_values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        service_type = _normalize_text(value)
        if not service_type:
            continue
        if service_type not in ALLOWED_SERVICE_TYPES:
            continue
        if service_type in seen:
            continue

        seen.add(service_type)
        cleaned.append(service_type)

    return cleaned


def yes_no_to_int(value: str | None) -> int | None:
    normalized = _normalize_text(value).lower()
    if normalized == "yes":
        return 1
    if normalized == "no":
        return 0
    return None


def parse_quantity(value: str | None) -> int | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    try:
        return int(normalized)
    except ValueError:
        return None


def parse_grit(value: str | None) -> int | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    try:
        grit_value = int(normalized)
    except ValueError:
        return None

    if grit_value < 0 or grit_value > 100:
        return None

    return grit_value


def display_label(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return "—"

    normalized = normalized.replace("_", " ").strip().lower()

    if normalized in DISPLAY_LABEL_MAP:
        return DISPLAY_LABEL_MAP[normalized]

    return normalized[:1].upper() + normalized[1:]


def display_quantity_unit(quantity, unit: str | None) -> str:
    unit_clean = _normalize_text(unit)

    if quantity is None and not unit_clean:
        return "—"
    if quantity is None:
        return unit_clean or "—"
    if not unit_clean:
        return str(quantity)

    return f"{quantity} {unit_clean}"
