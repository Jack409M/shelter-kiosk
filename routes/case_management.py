from __future__ import annotations

import json
from datetime import date
from typing import Any

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier
from core.runtime import init_db


case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


def _case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _shelter_equals_sql(column_name: str) -> str:
    if g.get("db_kind") == "pg":
        return f"LOWER(COALESCE({column_name}, '')) = %s"
    return f"LOWER(COALESCE({column_name}, '')) = ?"


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _parse_iso_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_money(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _yes_no_to_int(value: str | None) -> int:
    return 1 if (value or "").strip().lower() == "yes" else 0


def _draft_display_name(form: Any) -> str:
    first_name = _clean(form.get("first_name")) or ""
    last_name = _clean(form.get("last_name")) or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Unnamed intake draft"


def _save_intake_draft(
    current_shelter: str,
    form: Any,
    draft_id: int | None = None,
) -> int:
    placeholder = _placeholder()
    resident_name = _draft_display_name(form)
    entry_date = _clean(form.get("entry_date"))
    payload = json.dumps(form.to_dict(flat=True), ensure_ascii=False)

    if g.get("db_kind") == "pg":
        if draft_id is not None:
            row = db_fetchone(
                f"""
                UPDATE intake_drafts
                SET resident_name = {placeholder},
                    entry_date = {placeholder},
                    form_payload = {placeholder},
                    updated_at = NOW()
                WHERE id = {placeholder}
                  AND status = 'draft'
                  AND LOWER(COALESCE(shelter, '')) = {placeholder}
                RETURNING id
                """,
                (resident_name, entry_date, payload, draft_id, current_shelter),
            )
            if row:
                return int(row["id"])

        row = db_fetchone(
            f"""
            INSERT INTO intake_drafts
            (
                shelter,
                status,
                resident_name,
                entry_date,
                form_payload,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES
            (
                {placeholder},
                'draft',
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                current_shelter,
                resident_name,
                entry_date,
                payload,
                session.get("user_id"),
            ),
        )
        return int(row["id"])

    if draft_id is not None:
        db_execute(
            f"""
            UPDATE intake_drafts
            SET resident_name = {placeholder},
                entry_date = {placeholder},
                form_payload = {placeholder},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {placeholder}
              AND status = 'draft'
              AND LOWER(COALESCE(shelter, '')) = {placeholder}
            """,
            (resident_name, entry_date, payload, draft_id, current_shelter),
        )
        existing = db_fetchone(
            f"""
            SELECT id
            FROM intake_drafts
            WHERE id = {placeholder}
              AND status = 'draft'
              AND LOWER(COALESCE(shelter, '')) = {placeholder}
            """,
            (draft_id, current_shelter),
        )
        if existing:
            return draft_id

    db_execute(
        f"""
        INSERT INTO intake_drafts
        (
            shelter,
            status,
            resident_name,
            entry_date,
            form_payload,
            created_by_user_id,
            created_at,
            updated_at
        )
        VALUES
        (
            {placeholder},
            'draft',
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            current_shelter,
            resident_name,
            entry_date,
            payload,
            session.get("user_id"),
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _load_intake_draft(current_shelter: str, draft_id: int) -> dict[str, Any] | None:
    placeholder = _placeholder()
    row = db_fetchone(
        f"""
        SELECT
            id,
            resident_name,
            form_payload,
            updated_at
        FROM intake_drafts
        WHERE id = {placeholder}
          AND status = 'draft'
          AND LOWER(COALESCE(shelter, '')) = {placeholder}
        """,
        (draft_id, current_shelter),
    )
    if not row:
        return None

    payload_raw = row["form_payload"] if isinstance(row, dict) else row[2]

    try:
        payload = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        payload = {}

    payload["draft_id"] = str(row["id"] if isinstance(row, dict) else row[0])
    return payload


def _complete_intake_draft(draft_id: int) -> None:
    placeholder = _placeholder()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            UPDATE intake_drafts
            SET status = 'completed',
                updated_at = NOW()
            WHERE id = {placeholder}
            """,
            (draft_id,),
        )
        return

    db_execute(
        f"""
        UPDATE intake_drafts
        SET status = 'completed',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {placeholder}
        """,
        (draft_id,),
    )


def _intake_template_context(
    current_shelter: str,
    form_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": form_data or {},
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
            {"value": "female", "label": "Female"},
            {"value": "male", "label": "Male"},
            {"value": "nonbinary", "label": "Nonbinary"},
            {"value": "other", "label": "Other"},
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
        "education_options": [
            {"value": "no_hs", "label": "No High School"},
            {"value": "hs", "label": "High School"},
            {"value": "ged", "label": "GED"},
            {"value": "college", "label": "Some College"},
            {"value": "associate", "label": "Associate"},
            {"value": "bachelor", "label": "Bachelor"},
        ],
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


def _validate_intake_form(form: Any, shelter: str) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "first_name": _clean(form.get("first_name")),
        "middle_name": _clean(form.get("middle_name")),
        "last_name": _clean(form.get("last_name")),
        "birth_year": _clean(form.get("birth_year")),
        "phone": _clean(form.get("phone")),
        "email": _clean(form.get("email")),
        "gender": _clean(form.get("gender")),
        "veteran": _clean(form.get("veteran")),
        "emergency_contact_name": _clean(form.get("emergency_contact_name")),
        "emergency_contact_relationship": _clean(form.get("emergency_contact_relationship")),
        "emergency_contact_phone": _clean(form.get("emergency_contact_phone")),
        "notes_basic": _clean(form.get("notes_basic")),
        "entry_date": _clean(form.get("entry_date")),
        "shelter": _normalize_shelter_name(form.get("shelter") or shelter),
        "program_status": _clean(form.get("program_status")) or "active",
        "prior_living": _clean(form.get("prior_living")),
        "city": _clean(form.get("city")),
        "last_zipcode_residence": _clean(form.get("last_zipcode_residence")),
        "length_of_time_in_amarillo": _clean(form.get("length_of_time_in_amarillo")),
        "marital_status": _clean(form.get("marital_status")),
        "sobriety_date": _clean(form.get("sobriety_date")),
        "drug_of_choice": _clean(form.get("drug_of_choice")),
        "income_at_entry": _clean(form.get("income_at_entry")),
        "education_at_entry": _clean(form.get("education_at_entry")),
        "disability": _clean(form.get("disability")),
        "entry_notes": _clean(form.get("entry_notes")),
        "race": _clean(form.get("race")),
        "ethnicity": _clean(form.get("ethnicity")),
        "pregnant": _clean(form.get("pregnant")),
        "has_children": _clean(form.get("has_children")),
        "children_count": _clean(form.get("children_count")),
        "newborn_at_dwc": _clean(form.get("newborn_at_dwc")),
        "dental_need": _clean(form.get("dental_need")),
        "vision_need": _clean(form.get("vision_need")),
        "employment_status": _clean(form.get("employment_status")),
        "initial_snapshot_notes": _clean(form.get("initial_snapshot_notes")),
        "ace_score": _clean(form.get("ace_score")),
        "grit_score": _clean(form.get("grit_score")),
        "sexual_survivor": _clean(form.get("sexual_survivor")),
        "domestic_violence_history": _clean(form.get("domestic_violence_history")),
        "human_trafficking_history": _clean(form.get("human_trafficking_history")),
        "drug_court": _clean(form.get("drug_court")),
        "warrants_unpaid": _clean(form.get("warrants_unpaid")),
        "mh_exam_completed": _clean(form.get("mh_exam_completed")),
        "med_exam_completed": _clean(form.get("med_exam_completed")),
        "mental_health_need": _clean(form.get("mental_health_need")),
        "medical_need": _clean(form.get("medical_need")),
        "substance_use_need": _clean(form.get("substance_use_need")),
        "car_at_entry": _clean(form.get("car_at_entry")),
        "car_insurance_at_entry": _clean(form.get("car_insurance_at_entry")),
        "trauma_notes": _clean(form.get("trauma_notes")),
        "felony_history": _clean(form.get("felony_history")),
        "probation_parole": _clean(form.get("probation_parole")),
        "id_documents_status": _clean(form.get("id_documents_status")),
        "barrier_notes": _clean(form.get("barrier_notes")),
    }

    errors: list[str] = []

    if not data["first_name"]:
        errors.append("First name is required.")

    if not data["last_name"]:
        errors.append("Last name is required.")

    if not data["entry_date"]:
        errors.append("Date Entered is required.")

    if data["shelter"] != shelter:
        errors.append("Intake shelter must match the shelter currently selected in staff navigation.")

    birth_year = _parse_int(data["birth_year"])
    current_year = date.today().year
    if data["birth_year"] and birth_year is None:
        errors.append("Birth Year must be a whole year.")
    if birth_year is not None and birth_year < 1900:
        errors.append("Birth Year cannot be earlier than 1900.")
    if birth_year is not None and birth_year > current_year:
        errors.append("Birth Year cannot be in the future.")
    data["birth_year"] = birth_year

    entry_date = _parse_iso_date(data["entry_date"])
    if data["entry_date"] and entry_date is None:
        errors.append("Date Entered must be a valid date.")

    sobriety_date = _parse_iso_date(data["sobriety_date"])
    if data["sobriety_date"] and sobriety_date is None:
        errors.append("Sobriety Date must be a valid date.")

    today = date.today()

    if entry_date and entry_date > today:
        errors.append("Date Entered cannot be in the future.")

    if sobriety_date and entry_date and sobriety_date > entry_date:
        errors.append("Sobriety Date cannot be later than Date Entered.")

    phone_digits = _digits_only(data["phone"])
    if data["phone"] and len(phone_digits) < 10:
        errors.append("Phone must contain at least 10 digits.")

    emergency_phone_digits = _digits_only(data["emergency_contact_phone"])
    if data["emergency_contact_phone"] and len(emergency_phone_digits) < 10:
        errors.append("Emergency Contact Phone must contain at least 10 digits.")

    if data["last_zipcode_residence"]:
        zipcode_digits = _digits_only(data["last_zipcode_residence"])
        if len(zipcode_digits) not in {5, 9}:
            errors.append("Last Zipcode of Residence must be 5 or 9 digits.")

    children_count = _parse_int(data["children_count"])
    if data["children_count"] and children_count is None:
        errors.append("Children Count must be a whole number.")
    if children_count is not None and children_count < 0:
        errors.append("Children Count cannot be negative.")
    data["children_count"] = children_count

    ace_score = _parse_int(data["ace_score"])
    if data["ace_score"] and ace_score is None:
        errors.append("ACE Score must be a whole number.")
    if ace_score is not None and not 0 <= ace_score <= 10:
        errors.append("ACE Score must be between 0 and 10.")
    data["ace_score"] = ace_score

    grit_score = _parse_int(data["grit_score"])
    if data["grit_score"] and grit_score is None:
        errors.append("Grit Score must be a whole number.")
    if grit_score is not None and not 0 <= grit_score <= 100:
        errors.append("Grit Score must be between 0 and 100.")
    data["grit_score"] = grit_score

    income_at_entry = _parse_money(data["income_at_entry"])
    if data["income_at_entry"] and income_at_entry is None:
        errors.append("Income at Entry must be a valid number.")
    if income_at_entry is not None and income_at_entry < 0:
        errors.append("Income at Entry cannot be negative.")
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
) -> Any:
    placeholder = _placeholder()

    if email:
        existing = db_fetchone(
            f"""
            SELECT id, first_name, last_name, birth_year, phone, email, resident_identifier
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
              AND LOWER(COALESCE(email, '')) = LOWER({placeholder})
            LIMIT 1
            """,
            (shelter, email),
        )
        if existing:
            return existing

    if phone:
        existing = db_fetchone(
            f"""
            SELECT id, first_name, last_name, birth_year, phone, email, resident_identifier
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
              AND COALESCE(phone, '') = {placeholder}
            LIMIT 1
            """,
            (shelter, phone),
        )
        if existing:
            return existing

    if first_name and last_name and birth_year is not None:
        existing = db_fetchone(
            f"""
            SELECT id, first_name, last_name, birth_year, phone, email, resident_identifier
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
              AND LOWER(COALESCE(first_name, '')) = LOWER({placeholder})
              AND LOWER(COALESCE(last_name, '')) = LOWER({placeholder})
              AND birth_year = {placeholder}
            LIMIT 1
            """,
            (shelter, first_name, last_name, birth_year),
        )
        if existing:
            return existing

    return None


def _insert_resident(data: dict[str, Any], shelter: str) -> tuple[int, str, str]:
    placeholder = _placeholder()
    resident_identifier = generate_resident_identifier()
    resident_code = generate_resident_code()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO residents
            (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                shelter,
                is_active,
                created_at
            )
            VALUES (
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                TRUE,
                NOW()
            )
            RETURNING id
            """,
            (
                resident_identifier,
                resident_code,
                data["first_name"],
                data["last_name"],
                data["birth_year"],
                data["phone"],
                data["email"],
                data["emergency_contact_name"],
                data["emergency_contact_relationship"],
                data["emergency_contact_phone"],
                shelter,
            ),
        )
        return int(row["id"]), resident_identifier, resident_code

    db_execute(
        f"""
        INSERT INTO residents
        (
            resident_identifier,
            resident_code,
            first_name,
            last_name,
            birth_year,
            phone,
            email,
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone,
            shelter,
            is_active,
            created_at
        )
        VALUES (
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            1,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_identifier,
            resident_code,
            data["first_name"],
            data["last_name"],
            data["birth_year"],
            data["phone"],
            data["email"],
            data["emergency_contact_name"],
            data["emergency_contact_relationship"],
            data["emergency_contact_phone"],
            shelter,
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"]), resident_identifier, resident_code


def _insert_program_enrollment(resident_id: int, data: dict[str, Any], shelter: str) -> int:
    placeholder = _placeholder()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO program_enrollments
            (
                resident_id,
                shelter,
                program_status,
                entry_date,
                created_at,
                updated_at
            )
            VALUES (
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                resident_id,
                shelter,
                data["program_status"] or "active",
                data["entry_date"],
            ),
        )
        return int(row["id"])

    db_execute(
        f"""
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            program_status,
            entry_date,
            created_at,
            updated_at
        )
        VALUES (
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_id,
            shelter,
            data["program_status"] or "active",
            data["entry_date"],
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _insert_intake_assessment(enrollment_id: int, data: dict[str, Any]) -> None:
    placeholder = _placeholder()
    now = utcnow_iso()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                sobriety_date,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                place_staying_before_entry,
                entry_felony_conviction,
                entry_parole_probation,
                drug_court,
                sexual_survivor,
                dv_survivor,
                human_trafficking_survivor,
                warrants_unpaid,
                mh_exam_completed,
                med_exam_completed,
                car_at_entry,
                car_insurance_at_entry,
                created_at,
                updated_at
            )
            VALUES
            (
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder}
            )
            """,
            (
                enrollment_id,
                data["city"],
                data["last_zipcode_residence"],
                data["length_of_time_in_amarillo"],
                data["income_at_entry"],
                data["education_at_entry"],
                data["sobriety_date"],
                data["drug_of_choice"],
                data["ace_score"],
                data["grit_score"],
                _yes_no_to_int(data["veteran"]),
                _yes_no_to_int(data["disability"]),
                data["marital_status"],
                data["prior_living"],
                _yes_no_to_int(data["felony_history"]),
                _yes_no_to_int(data["probation_parole"]),
                _yes_no_to_int(data["drug_court"]),
                _yes_no_to_int(data["sexual_survivor"]),
                _yes_no_to_int(data["domestic_violence_history"]),
                _yes_no_to_int(data["human_trafficking_history"]),
                _yes_no_to_int(data["warrants_unpaid"]),
                _yes_no_to_int(data["mh_exam_completed"]),
                _yes_no_to_int(data["med_exam_completed"]),
                _yes_no_to_int(data["car_at_entry"]),
                _yes_no_to_int(data["car_insurance_at_entry"]),
                now,
                now,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO intake_assessments
        (
            enrollment_id,
            city,
            last_zipcode_residence,
            length_of_time_in_amarillo,
            income_at_entry,
            education_at_entry,
            sobriety_date,
            drug_of_choice,
            ace_score,
            grit_score,
            veteran,
            disability,
            marital_status,
            place_staying_before_entry,
            entry_felony_conviction,
            entry_parole_probation,
            drug_court,
            sexual_survivor,
            dv_survivor,
            human_trafficking_survivor,
            warrants_unpaid,
            mh_exam_completed,
            med_exam_completed,
            car_at_entry,
            car_insurance_at_entry,
            created_at,
            updated_at
        )
        VALUES
        (
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder}
        )
        """,
        (
            enrollment_id,
            data["city"],
            data["last_zipcode_residence"],
            data["length_of_time_in_amarillo"],
            data["income_at_entry"],
            data["education_at_entry"],
            data["sobriety_date"],
            data["drug_of_choice"],
            data["ace_score"],
            data["grit_score"],
            _yes_no_to_int(data["veteran"]),
            _yes_no_to_int(data["disability"]),
            data["marital_status"],
            data["prior_living"],
            _yes_no_to_int(data["felony_history"]),
            _yes_no_to_int(data["probation_parole"]),
            _yes_no_to_int(data["drug_court"]),
            _yes_no_to_int(data["sexual_survivor"]),
            _yes_no_to_int(data["domestic_violence_history"]),
            _yes_no_to_int(data["human_trafficking_history"]),
            _yes_no_to_int(data["warrants_unpaid"]),
            _yes_no_to_int(data["mh_exam_completed"]),
            _yes_no_to_int(data["med_exam_completed"]),
            _yes_no_to_int(data["car_at_entry"]),
            _yes_no_to_int(data["car_insurance_at_entry"]),
            now,
            now,
        ),
    )


def _insert_family_snapshot(enrollment_id: int, data: dict[str, Any]) -> None:
    placeholder = _placeholder()

    kids_at_dwc = data["children_count"] if data["has_children"] == "yes" and data["children_count"] is not None else 0
    healthy_babies_born_at_dwc = 1 if data["newborn_at_dwc"] == "yes" else 0

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO family_snapshots
            (
                enrollment_id,
                kids_at_dwc,
                healthy_babies_born_at_dwc,
                created_at,
                updated_at
            )
            VALUES
            (
                {placeholder},
                {placeholder},
                {placeholder},
                NOW(),
                NOW()
            )
            """,
            (
                enrollment_id,
                kids_at_dwc,
                healthy_babies_born_at_dwc,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO family_snapshots
        (
            enrollment_id,
            kids_at_dwc,
            healthy_babies_born_at_dwc,
            created_at,
            updated_at
        )
        VALUES
        (
            {placeholder},
            {placeholder},
            {placeholder},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            enrollment_id,
            kids_at_dwc,
            healthy_babies_born_at_dwc,
        ),
    )


@case_management.get("")
@require_login
@require_shelter
def index():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    placeholder = _placeholder()

    residents = db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            is_active
        FROM residents
        WHERE {_shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {placeholder}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    return render_template(
        "case_management/index.html",
        residents=residents,
        drafts=drafts,
        shelter=shelter,
    )


@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_assessment():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = _normalize_shelter_name(session.get("shelter"))
    draft_id = _parse_int(request.args.get("draft_id"))
    form_data: dict[str, Any] | None = None

    if draft_id is not None:
        form_data = _load_intake_draft(current_shelter, draft_id)
        if not form_data:
            flash("Intake draft not found.", "error")
            return redirect(url_for("case_management.index"))

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
        ),
    )


@case_management.post("/intake-assessment")
@require_login
@require_shelter
def submit_intake_assessment():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = _normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "complete").strip().lower()
    draft_id = _parse_int(request.form.get("draft_id"))

    if action == "save_draft":
        first_name = _clean(request.form.get("first_name"))
        last_name = _clean(request.form.get("last_name"))

        if not first_name or not last_name:
            flash("Save Draft requires at least first name and last name.", "error")
            return render_template(
                "case_management/intake_assessment.html",
                **_intake_template_context(
                    current_shelter=current_shelter,
                    form_data=request.form.to_dict(flat=True),
                ),
            )

        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=request.form,
            draft_id=draft_id,
        )

        flash("Intake draft saved.", "success")
        return redirect(url_for("case_management.intake_assessment", draft_id=saved_draft_id))

    data, errors = _validate_intake_form(request.form, current_shelter)

    duplicate = _find_possible_duplicate(
        first_name=data["first_name"],
        last_name=data["last_name"],
        birth_year=data["birth_year"],
        phone=data["phone"],
        email=data["email"],
        shelter=current_shelter,
    )

    if duplicate:
        duplicate_id = duplicate["id"] if isinstance(duplicate, dict) else duplicate[0]
        duplicate_identifier = duplicate["resident_identifier"] if isinstance(duplicate, dict) else duplicate[6]
        if duplicate_identifier:
            flash(
                f"Possible duplicate resident found. Existing Resident ID: {duplicate_identifier}. Review that profile before creating a new one.",
                "error",
            )
        else:
            flash(
                "Possible duplicate resident found. Review the existing profile before creating a new one.",
                "error",
            )
        return redirect(url_for("case_management.resident_case", resident_id=duplicate_id))

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/intake_assessment.html",
            **_intake_template_context(
                current_shelter=current_shelter,
                form_data=request.form.to_dict(flat=True),
            ),
        )

    resident_id, resident_identifier, resident_code = _insert_resident(data, current_shelter)
    enrollment_id = _insert_program_enrollment(resident_id, data, current_shelter)
    _insert_intake_assessment(enrollment_id, data)
    _insert_family_snapshot(enrollment_id, data)

    if draft_id is not None:
        _complete_intake_draft(draft_id)

    flash(
        f"Resident created successfully. Resident ID: {resident_identifier}. Resident Code: {resident_code}",
        "success",
    )
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    placeholder = _placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {placeholder}
          AND {_shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {placeholder}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = None
    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    goals = []
    appointments = []
    notes = []

    if enrollment_id:
        goals = db_fetchall(
            f"""
            SELECT
                goal_text,
                status,
                target_date,
                created_at
            FROM goals
            WHERE enrollment_id = {placeholder}
            ORDER BY created_at DESC
            """,
            (enrollment_id,),
        )

        appointments = db_fetchall(
            f"""
            SELECT
                appointment_date,
                appointment_type,
                notes
            FROM appointments
            WHERE enrollment_id = {placeholder}
            ORDER BY appointment_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        notes = db_fetchall(
            f"""
            SELECT
                meeting_date,
                notes,
                progress_notes,
                action_items,
                created_at
            FROM case_manager_updates
            WHERE enrollment_id = {placeholder}
            ORDER BY meeting_date DESC, id DESC
            """,
            (enrollment_id,),
        )

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        goals=goals,
        appointments=appointments,
        notes=notes,
    )
