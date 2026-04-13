from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol, cast

from core.db import db_fetchall
from routes.case_management_parts.helpers import (
    clean,
    digits_only,
    normalize_shelter_name,
    parse_int,
    parse_iso_date,
    parse_money,
    placeholder,
)
from routes.case_management_parts.intake_income_support import benefits_screening_needed
from routes.case_management_parts.needs import normalize_selected_need_keys

type DbRow = dict[str, Any]


class IntakeFormLike(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def getlist(self, key: str) -> list[Any]: ...


ALLOWED_GENDER_VALUES = {"m", "f"}

ALLOWED_DISABILITY_VALUES = {
    "Visual",
    "Deaf",
    "Mental Health",
    "Intellectual",
    "Acquired Brain Injury",
    "Autism Spectrum Disorder",
    "Physical",
    "Multiple",
}

INCOME_COMPONENT_FIELDS: tuple[str, ...] = (
    "employment_income_1",
    "employment_income_2",
    "employment_income_3",
    "ssi_ssdi_income",
    "tanf_income",
    "child_support_income",
    "alimony_income",
    "other_income",
)

FAMILY_COUNT_FIELDS: tuple[str, ...] = (
    "kids_at_dwc",
    "kids_served_outside_under_18",
    "kids_ages_0_5",
    "kids_ages_6_11",
    "kids_ages_12_17",
    "kids_reunited_while_in_program",
    "healthy_babies_born_at_dwc",
)


def _field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def _normalized_email_or_none(value: object) -> str | None:
    email_value = clean(value)
    return email_value.lower() if email_value else None


def _normalized_phone_or_none(value: object) -> str | None:
    phone_digits = digits_only(value)
    return phone_digits or None


def _normalize_yes_no_blank(value: object) -> str:
    normalized = clean(value).lower()

    if normalized in {"yes", "true", "1", "on", "y"}:
        return "yes"

    if normalized in {"no", "false", "0", "off", "n"}:
        return "no"

    return ""


def _rank_duplicate_match(
    row: DbRow,
    phone: str | None,
    email: str | None,
) -> tuple[int, int]:
    row_phone = digits_only(row.get("phone"))
    row_email = _normalized_email_or_none(row.get("email"))

    if phone and row_phone and row_phone == phone:
        return (1, -int(row.get("id") or 0))

    if email and row_email and row_email == email:
        return (2, -int(row.get("id") or 0))

    if row.get("birth_year") is not None:
        return (3, -int(row.get("id") or 0))

    return (4, -int(row.get("id") or 0))


def _select_best_duplicate(
    rows: Sequence[DbRow],
    phone: str | None,
    email: str | None,
) -> DbRow | None:
    if not rows:
        return None

    ranked_rows = sorted(
        rows,
        key=lambda row: _rank_duplicate_match(row, phone, email),
    )
    return ranked_rows[0]


def _find_possible_duplicate(
    first_name: str | None,
    last_name: str | None,
    birth_year: int | None,
    phone: str | None,
    email: str | None,
    shelter: str,
    shelter_equals_sql: Any,
) -> DbRow | None:
    del shelter
    del shelter_equals_sql

    ph = placeholder()

    first_name_value = clean(first_name)
    last_name_value = clean(last_name)
    phone_value = _normalized_phone_or_none(phone)
    email_value = _normalized_email_or_none(email)

    if not first_name_value or not last_name_value:
        return None

    exact_match_clauses: list[str] = []
    exact_match_params: list[Any] = []

    if phone_value:
        exact_match_clauses.append(f"(phone = {ph})")
        exact_match_params.append(phone_value)

    if email_value:
        exact_match_clauses.append(f"(LOWER(email) = LOWER({ph}))")
        exact_match_params.append(email_value)

    if birth_year is not None:
        exact_match_clauses.append(
            f"(LOWER(first_name) = LOWER({ph}) AND LOWER(last_name) = LOWER({ph}) AND birth_year = {ph})"
        )
        exact_match_params.extend([first_name_value, last_name_value, birth_year])

    if exact_match_clauses:
        exact_rows = db_fetchall(
            f"""
            SELECT
                id,
                resident_code,
                first_name,
                last_name,
                birth_year,
                phone,
                resident_identifier,
                email,
                shelter
            FROM residents
            WHERE is_active = TRUE
              AND (
                {" OR ".join(exact_match_clauses)}
              )
            ORDER BY id DESC
            """,
            tuple(exact_match_params),
        )

        best_exact_match = _select_best_duplicate(exact_rows, phone_value, email_value)
        if best_exact_match is not None:
            return best_exact_match

    weak_name_only_rows = db_fetchall(
        f"""
        SELECT
            id,
            resident_code,
            first_name,
            last_name,
            birth_year,
            phone,
            resident_identifier,
            email,
            shelter
        FROM residents
        WHERE is_active = TRUE
          AND LOWER(first_name) = LOWER({ph})
          AND LOWER(last_name) = LOWER({ph})
        ORDER BY id DESC
        """,
        (first_name_value, last_name_value),
    )

    return _select_best_duplicate(weak_name_only_rows, phone_value, email_value)


def _validate_required_identity_fields(data: dict[str, Any], errors: list[str]) -> None:
    if not data["first_name"]:
        errors.append("First name is required.")

    if not data["last_name"]:
        errors.append("Last name is required.")

    if not data["entry_date"]:
        errors.append("Date Entered is required.")


def _validate_shelter_scope(
    data: dict[str, Any],
    normalized_selected_shelter: str,
    errors: list[str],
) -> None:
    if data["shelter"] != normalized_selected_shelter:
        errors.append(
            "Intake shelter must match the shelter currently selected in staff navigation."
        )


def _validate_gender_and_disability(data: dict[str, Any], errors: list[str]) -> None:
    gender_value = clean(data.get("gender")).lower()
    disability_value = clean(data.get("disability"))

    data["gender"] = gender_value
    data["disability"] = disability_value

    if gender_value and gender_value not in ALLOWED_GENDER_VALUES:
        errors.append("Gender must be M or F.")

    if disability_value and disability_value not in ALLOWED_DISABILITY_VALUES:
        errors.append("Invalid disability type.")


def _validate_birth_year(data: dict[str, Any], errors: list[str]) -> None:
    birth_year_text = clean(data.get("birth_year"))
    birth_year_value = parse_int(birth_year_text)
    current_year = date.today().year

    if birth_year_text and birth_year_value is None:
        errors.append("Birth Year must be a whole year.")
    elif birth_year_value is not None:
        if birth_year_value < 1900:
            errors.append("Birth Year cannot be earlier than 1900.")
        if birth_year_value > current_year:
            errors.append("Birth Year cannot be in the future.")

    data["birth_year"] = birth_year_value


def _validate_date_fields(data: dict[str, Any], errors: list[str]) -> None:
    entry_date_text = clean(data.get("entry_date"))
    sobriety_date_text = clean(data.get("sobriety_date"))
    treatment_grad_date_text = clean(data.get("treatment_grad_date"))

    entry_date_value = parse_iso_date(entry_date_text)
    sobriety_date_value = parse_iso_date(sobriety_date_text)
    treatment_grad_date_value = parse_iso_date(treatment_grad_date_text)

    if entry_date_text and entry_date_value is None:
        errors.append("Date Entered must be valid.")

    if sobriety_date_text and sobriety_date_value is None:
        errors.append("Sobriety Date must be valid.")

    if treatment_grad_date_text and treatment_grad_date_value is None:
        errors.append("Treatment Graduation Date must be valid.")

    today_value = date.today()

    if entry_date_value and entry_date_value > today_value:
        errors.append("Date Entered cannot be in the future.")

    if sobriety_date_value and entry_date_value:
        raw_days_sober = (entry_date_value - sobriety_date_value).days
        data["days_sober_at_entry"] = max(raw_days_sober, 0)
    else:
        data["days_sober_at_entry"] = None


def _validate_phone_and_email(data: dict[str, Any], errors: list[str]) -> None:
    phone_value = _normalized_phone_or_none(data.get("phone"))
    if phone_value is not None and len(phone_value) < 10:
        errors.append("Phone must contain at least 10 digits.")
    data["phone"] = phone_value

    data["email"] = _normalized_email_or_none(data.get("email"))


def _validate_zipcode(data: dict[str, Any], errors: list[str]) -> None:
    zipcode_text = clean(data.get("last_zipcode_residence"))
    if not zipcode_text:
        data["last_zipcode_residence"] = ""
        return

    zipcode_digits = digits_only(zipcode_text)
    if len(zipcode_digits) not in {5, 9}:
        errors.append("Zipcode must be 5 or 9 digits.")

    data["last_zipcode_residence"] = zipcode_digits


def _validate_scored_fields(data: dict[str, Any], errors: list[str]) -> None:
    ace_score_value = parse_int(data.get("ace_score"))
    if ace_score_value is not None and not 0 <= ace_score_value <= 10:
        errors.append("ACE Score must be between 0 and 10.")
    data["ace_score"] = ace_score_value

    grit_score_value = parse_int(data.get("grit_score"))
    if grit_score_value is not None and not 0 <= grit_score_value <= 100:
        errors.append("Grit Score must be between 0 and 100.")
    data["grit_score"] = grit_score_value


def _validate_income_fields(data: dict[str, Any], errors: list[str]) -> None:
    total_cash_support = 0.0

    for field_name in INCOME_COMPONENT_FIELDS:
        parsed_value = parse_money(data.get(field_name))
        if parsed_value is not None and parsed_value < 0:
            errors.append(f"{_field_label(field_name)} cannot be negative.")
        data[field_name] = parsed_value
        if parsed_value is not None:
            total_cash_support += parsed_value

    data["income_at_entry"] = round(total_cash_support, 2)


def _validate_family_count_fields(data: dict[str, Any], errors: list[str]) -> None:
    for field_name in FAMILY_COUNT_FIELDS:
        raw_value = data.get(field_name)
        parsed_value = parse_int(raw_value)

        if raw_value not in (None, "") and parsed_value is None:
            errors.append(f"{_field_label(field_name)} must be a whole number.")

        if parsed_value is not None and parsed_value < 0:
            errors.append(f"{_field_label(field_name)} cannot be negative.")

        data[field_name] = parsed_value


def _normalize_snap_field(data: dict[str, Any]) -> None:
    data["receives_snap_at_entry"] = _normalize_yes_no_blank(data.get("receives_snap_at_entry"))


def _apply_benefits_screening_need(data: dict[str, Any]) -> None:
    if not benefits_screening_needed(data):
        return

    selected_need_keys = list(cast(list[str], data["entry_need_keys"]))
    if "benefits_screening_texas" not in selected_need_keys:
        selected_need_keys.append("benefits_screening_texas")

    data["entry_need_keys"] = selected_need_keys
    data["need_benefits_screening_texas"] = "yes"


def _build_intake_data(form: IntakeFormLike, shelter: str) -> dict[str, Any]:
    normalized_need_keys = normalize_selected_need_keys(form.getlist("entry_need"))
    normalized_shelter = normalize_shelter_name(form.get("shelter") or shelter)

    data: dict[str, Any] = {
        "first_name": clean(form.get("first_name")),
        "middle_name": clean(form.get("middle_name")),
        "last_name": clean(form.get("last_name")),
        "birth_year": clean(form.get("birth_year")),
        "phone": clean(form.get("phone")),
        "email": clean(form.get("email")),
        "gender": clean(form.get("gender")),
        "veteran": clean(form.get("veteran")),
        "emergency_contact_name": clean(form.get("emergency_contact_name")),
        "emergency_contact_relationship": clean(form.get("emergency_contact_relationship")),
        "emergency_contact_phone": clean(form.get("emergency_contact_phone")),
        "notes_basic": clean(form.get("notes_basic")),
        "entry_date": clean(form.get("entry_date")),
        "shelter": normalized_shelter,
        "program_status": clean(form.get("program_status")) or "active",
        "prior_living": clean(form.get("prior_living")),
        "city": clean(form.get("city")),
        "county": clean(form.get("county")),
        "last_zipcode_residence": clean(form.get("last_zipcode_residence")),
        "length_of_time_in_amarillo": clean(form.get("length_of_time_in_amarillo")),
        "marital_status": clean(form.get("marital_status")),
        "treatment_grad_date": clean(form.get("treatment_grad_date")),
        "sobriety_date": clean(form.get("sobriety_date")),
        "drug_of_choice": clean(form.get("drug_of_choice")),
        "income_at_entry": clean(form.get("income_at_entry")),
        "education_at_entry": clean(form.get("education_at_entry")),
        "disability": clean(form.get("disability")),
        "dwc_level_today": clean(form.get("dwc_level_today")),
        "entry_notes": clean(form.get("entry_notes")),
        "race": clean(form.get("race")),
        "ethnicity": clean(form.get("ethnicity")),
        "pregnant": clean(form.get("pregnant")),
        "employment_status": clean(form.get("employment_status")),
        "initial_snapshot_notes": clean(form.get("initial_snapshot_notes")),
        "ace_score": clean(form.get("ace_score")),
        "grit_score": clean(form.get("grit_score")),
        "sexual_survivor": clean(form.get("sexual_survivor")),
        "domestic_violence_history": clean(form.get("domestic_violence_history")),
        "human_trafficking_history": clean(form.get("human_trafficking_history")),
        "drug_court": clean(form.get("drug_court")),
        "felony_history": clean(form.get("felony_history")),
        "probation_parole": clean(form.get("probation_parole")),
        "barrier_notes": clean(form.get("barrier_notes")),
        "car_at_entry": clean(form.get("car_at_entry")),
        "car_insurance_at_entry": clean(form.get("car_insurance_at_entry")),
        "kids_at_dwc": clean(form.get("kids_at_dwc")),
        "kids_served_outside_under_18": clean(form.get("kids_served_outside_under_18")),
        "kids_ages_0_5": clean(form.get("kids_ages_0_5")),
        "kids_ages_6_11": clean(form.get("kids_ages_6_11")),
        "kids_ages_12_17": clean(form.get("kids_ages_12_17")),
        "kids_reunited_while_in_program": clean(form.get("kids_reunited_while_in_program")),
        "healthy_babies_born_at_dwc": clean(form.get("healthy_babies_born_at_dwc")),
        "employment_income_1": clean(form.get("employment_income_1")),
        "employment_income_2": clean(form.get("employment_income_2")),
        "employment_income_3": clean(form.get("employment_income_3")),
        "ssi_ssdi_income": clean(form.get("ssi_ssdi_income")),
        "tanf_income": clean(form.get("tanf_income")),
        "child_support_income": clean(form.get("child_support_income")),
        "alimony_income": clean(form.get("alimony_income")),
        "other_income": clean(form.get("other_income")),
        "other_income_description": clean(form.get("other_income_description")),
        "receives_snap_at_entry": clean(form.get("receives_snap_at_entry")),
        "entry_need_keys": normalized_need_keys,
        "days_sober_at_entry": None,
    }

    for need_key in normalized_need_keys:
        data[f"need_{need_key}"] = "yes"

    return data


def _validate_intake_form(form: IntakeFormLike, shelter: str) -> tuple[dict[str, Any], list[str]]:
    normalized_selected_shelter = normalize_shelter_name(shelter)
    data = _build_intake_data(form, shelter)

    errors: list[str] = []

    _validate_required_identity_fields(data, errors)
    _validate_shelter_scope(data, normalized_selected_shelter, errors)
    _validate_gender_and_disability(data, errors)
    _validate_birth_year(data, errors)
    _validate_date_fields(data, errors)
    _validate_phone_and_email(data, errors)
    _validate_zipcode(data, errors)
    _validate_scored_fields(data, errors)
    _validate_income_fields(data, errors)
    _normalize_snap_field(data)
    _validate_family_count_fields(data, errors)
    _apply_benefits_screening_need(data)

    return data, errors
