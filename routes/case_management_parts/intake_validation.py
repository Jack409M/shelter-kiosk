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


def _validate_intake_form(form: Any, shelter: str) -> tuple[dict[str, Any], list[str]]:
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
        "last_zipcode_residence": clean(form.get("last_zipcode_residence")),
        "length_of_time_in_amarillo": clean(form.get("length_of_time_in_amarillo")),
        "marital_status": clean(form.get("marital_status")),
        "sobriety_date": clean(form.get("sobriety_date")),
        "drug_of_choice": clean(form.get("drug_of_choice")),
        "income_at_entry": clean(form.get("income_at_entry")),
        "education_at_entry": clean(form.get("education_at_entry")),
        "disability": clean(form.get("disability")),
        "entry_notes": clean(form.get("entry_notes")),
        "race": clean(form.get("race")),
        "ethnicity": clean(form.get("ethnicity")),
        "pregnant": clean(form.get("pregnant")),
        "has_children": clean(form.get("has_children")),
        "children_count": clean(form.get("children_count")),
        "newborn_at_dwc": clean(form.get("newborn_at_dwc")),
        "dental_need": clean(form.get("dental_need")),
        "vision_need": clean(form.get("vision_need")),
        "employment_status": clean(form.get("employment_status")),
        "initial_snapshot_notes": clean(form.get("initial_snapshot_notes")),
        "ace_score": clean(form.get("ace_score")),
        "grit_score": clean(form.get("grit_score")),
        "sexual_survivor": clean(form.get("sexual_survivor")),
        "domestic_violence_history": clean(form.get("domestic_violence_history")),
        "human_trafficking_history": clean(form.get("human_trafficking_history")),
        "drug_court": clean(form.get("drug_court")),
        "warrants_unpaid": clean(form.get("warrants_unpaid")),
        "mh_exam_completed": clean(form.get("mh_exam_completed")),
        "med_exam_completed": clean(form.get("med_exam_completed")),
        "mental_health_need": clean(form.get("mental_health_need")),
        "medical_need": clean(form.get("medical_need")),
        "substance_use_need": clean(form.get("substance_use_need")),
        "trauma_notes": clean(form.get("trauma_notes")),
        "felony_history": clean(form.get("felony_history")),
        "probation_parole": clean(form.get("probation_parole")),
        "id_documents_status": clean(form.get("id_documents_status")),
        "barrier_notes": clean(form.get("barrier_notes")),
        "days_sober_at_entry": None,
    }

    errors: list[str] = []

    if data["first_name"]:
        data["first_name"] = data["first_name"].strip()
    if data["middle_name"]:
        data["middle_name"] = data["middle_name"].strip()
    if data["last_name"]:
        data["last_name"] = data["last_name"].strip()
    if data["city"]:
        data["city"] = data["city"].strip()
    if data["disability"]:
        data["disability"] = data["disability"].strip()
    if data["gender"]:
        data["gender"] = data["gender"].strip().lower()

    if not data["first_name"]:
        errors.append("First name is required.")

    if not data["last_name"]:
        errors.append("Last name is required.")

    if not data["entry_date"]:
        errors.append("Date Entered is required.")

    if data["shelter"] != shelter:
        errors.append("Intake shelter must match the shelter currently selected in staff navigation.")

    if data["gender"] and data["gender"] not in ALLOWED_GENDER_VALUES:
        errors.append("Gender must be M or F.")

    if data["disability"] and data["disability"] not in ALLOWED_DISABILITY_VALUES:
        errors.append(
            "Disability Type must be one of the approved values: "
            "Visual, Deaf, Mental Health, Intellectual, Acquired Brain Injury, "
            "Autism Spectrum Disorder, Physical, or Multiple."
        )

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
    if data["entry_date"] and entry_date is None:
        errors.append("Date Entered must be a valid date.")

    sobriety_date = parse_iso_date(data["sobriety_date"])
    if data["sobriety_date"] and sobriety_date is None:
        errors.append("Sobriety Date must be a valid date.")

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

    emergency_phone_digits = digits_only(data["emergency_contact_phone"])
    if data["emergency_contact_phone"] and len(emergency_phone_digits) < 10:
        errors.append("Emergency Contact Phone must contain at least 10 digits.")
    data["emergency_contact_phone"] = emergency_phone_digits or None

    if data["email"]:
        data["email"] = data["email"].strip().lower()

    if data["last_zipcode_residence"]:
        zipcode_digits = digits_only(data["last_zipcode_residence"])
        if len(zipcode_digits) not in {5, 9}:
            errors.append("Last Zipcode of Residence must be 5 or 9 digits.")
        data["last_zipcode_residence"] = zipcode_digits

    children_count = parse_int(data["children_count"])
    if data["children_count"] and children_count is None:
        errors.append("Children Count must be a whole number.")
    if children_count is not None and children_count < 0:
        errors.append("Children Count cannot be negative.")
    data["children_count"] = children_count

    ace_score = parse_int(data["ace_score"])
    if data["ace_score"] and ace_score is None:
        errors.append("ACE Score must be a whole number.")
    if ace_score is not None and not 0 <= ace_score <= 10:
        errors.append("ACE Score must be between 0 and 10.")
    data["ace_score"] = ace_score

    grit_score = parse_int(data["grit_score"])
    if data["grit_score"] and grit_score is None:
        errors.append("Grit Score must be a whole number.")
    if grit_score is not None and not 0 <= grit_score <= 100:
        errors.append("Grit Score must be between 0 and 100.")
    data["grit_score"] = grit_score

    income_at_entry = parse_money(data["income_at_entry"])
    if data["income_at_entry"] and income_at_entry is None:
        errors.append("Monthly Income at Entry must be a valid number.")
    if income_at_entry is not None and income_at_entry < 0:
        errors.append("Monthly Income at Entry cannot be negative.")
    data["income_at_entry"] = income_at_entry

    if data["newborn_at_dwc"] == "yes":
        if data["has_children"] != "yes":
            errors.append("Newborn Born at DWC cannot be Yes unless Has Children is Yes.")
        if children_count is None or children_count < 1:
            errors.append("Newborn Born at DWC requires Children Count of at least 1.")

    if data["has_children"] == "no" and children_count not in (None, 0):
        errors.append("Children Count must be 0 when Has Children is No.")

    return data, errors


def _find_possible_duplicate(
    first_name: str | None,
    last_name: str | None,
    birth_year: int | None,
    phone: str | None,
    email: str | None,
    shelter: str,
    shelter_equals_sql,
) -> Any:
    ph = placeholder()

    normalized_first_name = clean(first_name)
    normalized_last_name = clean(last_name)
    normalized_email = clean(email)
    normalized_phone = digits_only(phone)

    if normalized_email:
        normalized_email = normalized_email.lower()

    if normalized_first_name and normalized_last_name and birth_year is not None and normalized_email:
        existing = db_fetchone(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                resident_identifier,
                shelter
            FROM residents
            WHERE LOWER(COALESCE(first_name, '')) = LOWER({ph})
              AND LOWER(COALESCE(last_name, '')) = LOWER({ph})
              AND birth_year = {ph}
              AND LOWER(COALESCE(email, '')) = LOWER({ph})
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_first_name, normalized_last_name, birth_year, normalized_email),
        )
        if existing:
            return existing

    if normalized_first_name and normalized_last_name and birth_year is not None and normalized_phone:
        existing = db_fetchone(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                resident_identifier,
                shelter
            FROM residents
            WHERE LOWER(COALESCE(first_name, '')) = LOWER({ph})
              AND LOWER(COALESCE(last_name, '')) = LOWER({ph})
              AND birth_year = {ph}
              AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(phone, ''), '-', ''), '(', ''), ')', ''), ' ', ''), '+', '') = {ph}
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_first_name, normalized_last_name, birth_year, normalized_phone),
        )
        if existing:
            return existing

    if normalized_first_name and normalized_last_name and birth_year is not None:
        existing = db_fetchone(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                resident_identifier,
                shelter
            FROM residents
            WHERE LOWER(COALESCE(first_name, '')) = LOWER({ph})
              AND LOWER(COALESCE(last_name, '')) = LOWER({ph})
              AND birth_year = {ph}
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_first_name, normalized_last_name, birth_year),
        )
        if existing:
            return existing

    if normalized_email:
        existing = db_fetchone(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                resident_identifier,
                shelter
            FROM residents
            WHERE LOWER(COALESCE(email, '')) = LOWER({ph})
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_email,),
        )
        if existing:
            return existing

    if normalized_phone:
        existing = db_fetchone(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                resident_identifier,
                shelter
            FROM residents
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(phone, ''), '-', ''), '(', ''), ')', ''), ' ', ''), '+', '') = {ph}
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_phone,),
        )
        if existing:
            return existing

    return None
