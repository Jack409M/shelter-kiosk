from __future__ import annotations

from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from core.constants import EDUCATION_LEVEL_OPTIONS
from core.intake_service import (
    create_intake,
    duplicate_identity,
    intake_edit_form_data,
    resident_enrollment_in_scope,
    save_intake_review_decision,
    update_intake,
)
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    normalize_shelter_name,
    parse_int,
)
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_validation import (
    _find_possible_duplicate,
    _validate_intake_form,
)
from routes.case_management_parts.needs import OFFICIAL_NEEDS


def _intake_template_context(
    current_shelter: str,
    form_data: dict[str, Any] | None = None,
    review_passed: bool = False,
    is_edit_mode: bool = False,
    resident_id: int | None = None,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": form_data or {},
        "review_passed": review_passed,
        "is_edit_mode": is_edit_mode,
        "resident_id": resident_id,
        "official_needs": OFFICIAL_NEEDS,
        "shelters": [
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        "prior_living_options": [
            {"value": "street", "label": "Street"},
            {"value": "shelter", "label": "Emergency Shelter"},
            {"value": "jail", "label": "Jail"},
            {"value": "hospital", "label": "Hospital"},
            {"value": "family", "label": "Family or Friends"},
            {"value": "treatment", "label": "Treatment Program"},
            {"value": "other", "label": "Other"},
        ],
        "ethnicity_options": [
            {"value": "hispanic", "label": "Hispanic"},
            {"value": "not_hispanic", "label": "Not Hispanic"},
        ],
        "race_options": [
            {"value": "white", "label": "White"},
            {"value": "black", "label": "Black"},
            {"value": "native", "label": "Native American"},
            {"value": "asian", "label": "Asian"},
            {"value": "pacific", "label": "Pacific Islander"},
            {"value": "other", "label": "Other"},
        ],
        "gender_options": [
            {"value": "m", "label": "M"},
            {"value": "f", "label": "F"},
        ],
        "yes_no_options": [
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No"},
        ],
        "drug_options": [
            {"value": "alcohol", "label": "Alcohol"},
            {"value": "meth", "label": "Meth"},
            {"value": "opioids", "label": "Opioids"},
            {"value": "cocaine", "label": "Cocaine"},
            {"value": "multiple", "label": "Multiple"},
            {"value": "other", "label": "Other"},
        ],
        "education_options": EDUCATION_LEVEL_OPTIONS,
        "marital_status_options": [
            {"value": "single", "label": "Single"},
            {"value": "married", "label": "Married"},
            {"value": "divorced", "label": "Divorced"},
            {"value": "separated", "label": "Separated"},
            {"value": "widowed", "label": "Widowed"},
            {"value": "partnered", "label": "Partnered"},
            {"value": "other", "label": "Other"},
        ],
        "amarillo_length_options": [
            {"value": "less_than_30_days", "label": "Less than 30 days"},
            {"value": "1_to_6_months", "label": "1 to 6 months"},
            {"value": "6_to_12_months", "label": "6 to 12 months"},
            {"value": "1_to_3_years", "label": "1 to 3 years"},
            {"value": "more_than_3_years", "label": "More than 3 years"},
            {"value": "lifelong", "label": "Lifelong"},
            {"value": "unknown", "label": "Unknown"},
        ],
    }


def _form_review_passed(form_source: dict[str, Any]) -> bool:
    value = clean(form_source.get("review_passed"))
    return value in {"1", "true", "yes", "on"}


def _normalize_yes_no_value(value: object | None) -> str:
    if value is None:
        return ""

    if isinstance(value, (int, bool)):
        if value in (1, True):
            return "yes"
        if value in (0, False):
            return "no"

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "yes", "y", "on"}:
        return "yes"

    if normalized in {"0", "false", "no", "n", "off"}:
        return "no"

    return normalized
