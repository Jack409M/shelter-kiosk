from __future__ import annotations

from typing import Any

from routes.case_management_parts.helpers import (
    clean,
    parse_iso_date,
    parse_money,
)

EDUCATION_LEVEL_OPTIONS = {
    "No High School",
    "Some High School",
    "High School Graduate",
    "GED",
    "Vocational",
    "Associates",
    "Bachelor",
    "Masters",
    "Doctorate",
}

EXIT_REASON_MAP = {
    "Successful Completion": {
        "Program Graduated",
    },
    "Positive Exit": {
        "Permanent Housing",
        "Family Placement",
        "Health Placement",
    },
    "Neutral Exit": {
        "Transferred to Another Program",
        "Unknown / Lost Contact",
    },
    "Negative Exit": {
        "Relapse",
        "Behavioral Conflict",
        "Rules Violation",
        "Non Compliance with Program",
        "Left Without Notice",
    },
    "Administrative Exit": {
        "Incarceration",
        "Medical Discharge",
        "Safety Removal",
        "Left by Choice",
        "Deceased",
    },
}

ALLOWED_EXIT_CATEGORIES = set(EXIT_REASON_MAP.keys())
ALLOWED_EXIT_REASONS = {
    reason for reasons in EXIT_REASON_MAP.values() for reason in reasons
}


def validate_exit_form(form: Any, entry_date: str | None) -> tuple[dict[str, Any], list[str]]:
    data = {
        "date_graduated": clean(form.get("date_graduated")),
        "date_exit_dwc": clean(form.get("date_exit_dwc")),
        "exit_category": clean(form.get("exit_category")),
        "exit_reason": clean(form.get("exit_reason")),
        "graduate_dwc": clean(form.get("graduate_dwc")),
        "leave_ama": clean(form.get("leave_ama")),
        "leave_amarillo_city": clean(form.get("leave_amarillo_city")),
        "leave_amarillo_unknown": "yes"
        if clean(form.get("leave_amarillo_unknown")) == "yes"
        else "no",
        "income_at_exit": clean(form.get("income_at_exit")),
        "education_at_exit": clean(form.get("education_at_exit")),
        "grit_at_exit": clean(form.get("grit_at_exit")),
        "received_car": clean(form.get("received_car")),
        "car_insurance": clean(form.get("car_insurance")),
        "dental_needs_met": clean(form.get("dental_needs_met")),
        "vision_needs_met": clean(form.get("vision_needs_met")),
        "obtained_public_insurance": clean(form.get("obtained_public_insurance")),
        "private_insurance": clean(form.get("private_insurance")),
    }

    errors: list[str] = []

    exit_date = parse_iso_date(data["date_exit_dwc"])
    if exit_date is None:
        errors.append("Date Exit DWC is required and must be a valid date.")
    data["date_exit_dwc"] = exit_date.isoformat() if exit_date else None

    grad_date = parse_iso_date(data["date_graduated"])
    if data["date_graduated"] and grad_date is None:
        errors.append("Date Graduated must be a valid date.")
    data["date_graduated"] = grad_date.isoformat() if grad_date else None

    if not data["exit_category"] or data["exit_category"] not in ALLOWED_EXIT_CATEGORIES:
        errors.append("Exit Category is required and must be valid.")

    if not data["exit_reason"] or data["exit_reason"] not in ALLOWED_EXIT_REASONS:
        errors.append("Exit Reason is required and must be valid.")

    if (
        data["exit_category"] in EXIT_REASON_MAP
        and data["exit_reason"]
        and data["exit_reason"] not in EXIT_REASON_MAP[data["exit_category"]]
    ):
        errors.append("Exit Reason must match the selected Exit Category.")

    is_deceased_exit = (
        data["exit_category"] == "Administrative Exit"
        and data["exit_reason"] == "Deceased"
    )

    income = parse_money(data["income_at_exit"])
    if data["income_at_exit"] and income is None:
        errors.append("Current Monthly Income must be a valid number.")
    if income is not None and income < 0:
        errors.append("Current Monthly Income cannot be negative.")
    data["income_at_exit"] = income

    grit = parse_money(data["grit_at_exit"])
    if data["grit_at_exit"] and grit is None:
        errors.append("Grit at Exit must be a valid number.")
    if grit is not None and grit < 0:
        errors.append("Grit at Exit cannot be negative.")
    data["grit_at_exit"] = grit

    if data["education_at_exit"] and data["education_at_exit"] not in EDUCATION_LEVEL_OPTIONS:
        errors.append("Education at Exit must be one of the approved education levels.")

    yes_no_fields = [
        "graduate_dwc",
        "leave_ama",
        "received_car",
        "car_insurance",
        "dental_needs_met",
        "vision_needs_met",
        "obtained_public_insurance",
        "private_insurance",
    ]

    for field_name in yes_no_fields:
        value = data[field_name]
        if value not in {None, "", "yes", "no"}:
            errors.append(f"{field_name.replace('_', ' ').title()} must be Yes or No.")

    if not is_deceased_exit:
        if data["graduate_dwc"] == "yes" and not data["date_graduated"]:
            errors.append("Date Graduated is required when Graduate DWC is Yes.")

        if data["date_graduated"] and data["graduate_dwc"] != "yes":
            errors.append("Graduate DWC must be Yes when Date Graduated is entered.")

        if data["car_insurance"] == "yes" and data["received_car"] != "yes":
            errors.append("Car Insurance cannot be Yes unless Received Car is Yes.")

        if data["leave_ama"] == "yes":
            if data["leave_amarillo_unknown"] != "yes" and not data["leave_amarillo_city"]:
                errors.append(
                    "Enter the city left for or mark it Unknown when Leave Amarillo is Yes."
                )
        else:
            data["leave_amarillo_city"] = ""
            data["leave_amarillo_unknown"] = "no"

        if data["leave_amarillo_unknown"] == "yes":
            data["leave_amarillo_city"] = ""
    else:
        data["date_graduated"] = None
        data["graduate_dwc"] = "no"
        data["leave_ama"] = "no"
        data["leave_amarillo_city"] = ""
        data["leave_amarillo_unknown"] = "no"
        data["income_at_exit"] = None
        data["education_at_exit"] = ""
        data["grit_at_exit"] = None
        data["received_car"] = ""
        data["car_insurance"] = ""
        data["dental_needs_met"] = ""
        data["vision_needs_met"] = ""
        data["obtained_public_insurance"] = ""
        data["private_insurance"] = ""

    entry_dt = parse_iso_date(entry_date)
    if entry_dt and exit_date and exit_date < entry_dt:
        errors.append("Date Exit DWC cannot be earlier than the entry date.")

    return data, errors
