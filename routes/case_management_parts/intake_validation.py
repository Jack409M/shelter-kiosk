from __future__ import annotations

from datetime import date
from typing import Any

from core.db import db_fetchone
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import digits_only
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.needs import normalize_selected_need_keys


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


def _find_possible_duplicate(
    first_name: str | None,
    last_name: str | None,
    birth_year: int | None,
    phone: str | None,
    email: str | None,
    shelter: str,
    shelter_equals_sql,
):
    ph = placeholder()

    first_name = clean(first_name)
    last_name = clean(last_name)
    phone = digits_only(phone)
    email = clean(email)
    shelter = normalize_shelter_name(shelter)

    if email:
        email = email.lower()

    if not first_name or not last_name:
        return None

    match_clauses: list[str] = []
    params: list[Any] = []

    match_clauses.append(
        "(LOWER(first_name) = LOWER(" + ph + ") AND LOWER(last_name) = LOWER(" + ph + "))"
    )
    params.extend([first_name, last_name])

    if birth_year is not None:
        match_clauses.append(
            "(LOWER(first_name) = LOWER(" + ph + ") AND LOWER(last_name) = LOWER(" + ph + ") AND birth_year = " + ph + ")"
        )
        params.extend([first_name, last_name, birth_year])

    if phone:
        match_clauses.append("(phone = " + ph + ")")
        params.append(phone)

    if email:
        match_clauses.append("(LOWER(email) = LOWER(" + ph + "))")
        params.append(email)

    if not match_clauses:
        return None

    shelter_sql = shelter_equals_sql("shelter")

    sql = f"""
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
          AND ({shelter_sql})
          AND (
            {" OR ".join(match_clauses)}
          )
        ORDER BY id DESC
        LIMIT 1
    """

    return db_fetchone(sql, tuple([shelter] + params))


def _validate_intake_form(form: Any, shelter: str) -> tuple[dict[str, Any], list[str]]:
    normalized_selected_shelter = normalize_shelter_name(shelter)
    selected_need_keys = normalize_selected_need_keys(form.getlist("entry_need"))

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
        "shelter": normalize_shelter_name(form.get("shelter") or shelter),
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
        "entry_need_keys": selected_need_keys,
        "days_sober_at_entry": None,
    }

    for need_key in selected_need_keys:
        data[f"need_{need_key}"] = "yes"

    errors: list[str] = []

    if not data["first_name"]:
        errors.append("First name is required.")

    if not data["last_name"]:
        errors.append("Last name is required.")

    if not data["entry_date"]:
        errors.append("Date Entered is required.")

    if data["shelter"] != normalized_selected_shelter:
        errors.append("Intake shelter must match the shelter currently selected in staff navigation.")

    if data["gender"]:
        data["gender"] = data["gender"].strip().lower()

    if data["disability"]:
        data["disability"] = data["disability"].strip()

    if data["gender"] and data["gender"] not in ALLOWED_GENDER_VALUES:
        errors.append("Gender must be M or F.")

    if data["disability"] and data["disability"] not in ALLOWED_DISABILITY_VALUES:
        errors.append("Invalid disability type.")

    birth_year = parse_int(data["birth_year"])
    current_year = date.today().year

    if data["birth_year"] and birth_year is None:
        errors.append("Birth Year must be a whole year.")
    if birth_year is not None and birth_year < 1900:
        errors.append("Birth Year cannot be earlier than 1900.")
    if birth_year is not None and birth_year > current_year:
        errors.append("Birth Year cannot be in the future.")

    data["birth_year"] = birth_year

    entry_date = parse_iso_date(data["entry_date"])
    sobriety_date = parse_iso_date(data["sobriety_date"])
    treatment_grad_date = parse_iso_date(data["treatment_grad_date"])

    if data["entry_date"] and entry_date is None:
        errors.append("Date Entered must be valid.")

    if data["sobriety_date"] and sobriety_date is None:
        errors.append("Sobriety Date must be valid.")

    if data["treatment_grad_date"] and treatment_grad_date is None:
        errors.append("Treatment Graduation Date must be valid.")

    today = date.today()

    if entry_date and entry_date > today:
        errors.append("Date Entered cannot be in the future.")

    if sobriety_date and entry_date:
        raw_days = (entry_date - sobriety_date).days
        data["days_sober_at_entry"] = max(raw_days, 0)

    phone_digits = digits_only(data["phone"])
    if data["phone"] and len(phone_digits) < 10:
        errors.append("Phone must contain at least 10 digits.")
    data["phone"] = phone_digits or None

    if data["email"]:
        data["email"] = data["email"].strip().lower()

    if data["last_zipcode_residence"]:
        zipcode_digits = digits_only(data["last_zipcode_residence"])
        if len(zipcode_digits) not in {5, 9}:
            errors.append("Zipcode must be 5 or 9 digits.")
        data["last_zipcode_residence"] = zipcode_digits

    ace_score = parse_int(data["ace_score"])
    if ace_score is not None and not 0 <= ace_score <= 10:
        errors.append("ACE Score must be between 0 and 10.")
    data["ace_score"] = ace_score

    grit_score = parse_int(data["grit_score"])
    if grit_score is not None and not 0 <= grit_score <= 100:
        errors.append("Grit Score must be between 0 and 100.")
    data["grit_score"] = grit_score

    income_at_entry = parse_money(data["income_at_entry"])
    if income_at_entry is not None and income_at_entry < 0:
        errors.append("Monthly Income cannot be negative.")
    data["income_at_entry"] = income_at_entry

    return data, errors
