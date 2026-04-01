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
    "employment_status_current": "Employment Status",
    "employment_type_current": "Employment Type",
    "employer_name": "Employer",
    "supervisor_name": "Supervisor Name",
    "supervisor_phone": "Supervisor Phone",
    "monthly_income": "Monthly Income",
    "unemployment_reason": "Unemployment Reason",
}


SOBRIETY_FIELD_LABELS = {
    "sobriety_date": "Sobriety Date",
    "drug_of_choice": "Drug Of Choice",
    "treatment_graduation_date": "Treatment Graduation Date",
}


ADVANCEMENT_BOOL_FIELD_LABELS = {
    "ready_for_next_level": "Ready For Next Level",
}


ADVANCEMENT_TEXT_FIELD_LABELS = {
    "recommended_next_level": "Recommended Next Level",
    "blocker_reason": "Blocker Reason",
    "override_or_exception": "Override Or Exception",
    "staff_review_note": "Staff Review Note",
}


MEETING_TEXT_FIELD_LABELS = {
    "setbacks_or_incidents": "Setbacks Or Incidents",
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
    return value.replace("_", " ").strip().title()


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
