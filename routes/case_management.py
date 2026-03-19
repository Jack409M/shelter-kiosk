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


def _save_assessment_draft(
    current_shelter: str,
    form_data: dict[str, Any],
    resident_id: int,
    draft_id: int | None = None,
) -> int:
    placeholder = _placeholder()
    payload = json.dumps(form_data, ensure_ascii=False)
    now = utcnow_iso()

    if g.get("db_kind") == "pg":
        if draft_id is not None:
            row = db_fetchone(
                f"""
                UPDATE assessment_drafts
                SET resident_id = {placeholder},
                    form_payload = {placeholder},
                    updated_at = {placeholder}
                WHERE id = {placeholder}
                  AND status = 'draft'
                  AND LOWER(COALESCE(shelter, '')) = {placeholder}
                RETURNING id
                """,
                (resident_id, payload, now, draft_id, current_shelter),
            )
            if row:
                return int(row["id"])

        row = db_fetchone(
            f"""
            INSERT INTO assessment_drafts
            (
                shelter,
                resident_id,
                form_payload,
                status,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES
            (
                {placeholder},
                {placeholder},
                {placeholder},
                'draft',
                {placeholder},
                {placeholder},
                {placeholder}
            )
            RETURNING id
            """,
            (
                current_shelter,
                resident_id,
                payload,
                session.get("user_id"),
                now,
                now,
            ),
        )
        return int(row["id"])

    if draft_id is not None:
        db_execute(
            f"""
            UPDATE assessment_drafts
            SET resident_id = {placeholder},
                form_payload = {placeholder},
                updated_at = {placeholder}
            WHERE id = {placeholder}
              AND status = 'draft'
              AND LOWER(COALESCE(shelter, '')) = {placeholder}
            """,
            (resident_id, payload, now, draft_id, current_shelter),
        )
        existing = db_fetchone(
            f"""
            SELECT id
            FROM assessment_drafts
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
        INSERT INTO assessment_drafts
        (
            shelter,
            resident_id,
            form_payload,
            status,
            created_by_user_id,
            created_at,
            updated_at
        )
        VALUES
        (
            {placeholder},
            {placeholder},
            {placeholder},
            'draft',
            {placeholder},
            {placeholder},
            {placeholder}
        )
        """,
        (
            current_shelter,
            resident_id,
            payload,
            session.get("user_id"),
            now,
            now,
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _load_assessment_draft(current_shelter: str, draft_id: int) -> dict[str, Any] | None:
    placeholder = _placeholder()
    row = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            form_payload
        FROM assessment_drafts
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

    resident_id = row["resident_id"] if isinstance(row, dict) else row[1]
    if resident_id is not None and "resident_id" not in payload:
        payload["resident_id"] = str(resident_id)

    return payload


def _complete_assessment_draft(draft_id: int) -> None:
    placeholder = _placeholder()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            UPDATE assessment_drafts
            SET status = 'completed',
                updated_at = NOW()
            WHERE id = {placeholder}
            """,
            (draft_id,),
        )
        return

    db_execute(
        f"""
        UPDATE assessment_drafts
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


def _validate_assessment_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "resident_id": _parse_int(form.get("resident_id")),
        "ace_score": _clean(form.get("ace_score")),
        "grit_score": _clean(form.get("grit_score")),
        "sexual_survivor": _clean(form.get("sexual_survivor")),
        "domestic_violence_history": _clean(form.get("domestic_violence_history")),
        "human_trafficking_history": _clean(form.get("human_trafficking_history")),
        "drug_court": _clean(form.get("drug_court")),
        "warrants_unpaid": _clean(form.get("warrants_unpaid")),
        "mh_exam_completed": _clean(form.get("mh_exam_completed")),
        "med_exam_completed": _clean(form.get("med_exam_completed")),
        "car_at_entry": _clean(form.get("car_at_entry")),
        "car_insurance_at_entry": _clean(form.get("car_insurance_at_entry")),
    }

    errors: list[str] = []

    if not data["resident_id"]:
        errors.append("Resident is required.")

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


def _find_active_enrollment_id(resident_id: int, shelter: str) -> int | None:
    placeholder = _placeholder()

    row = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {placeholder}
          AND {_shelter_equals_sql("shelter")}
          AND exit_date IS NULL
        ORDER BY entry_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not row:
        return None

    return int(row["id"] if isinstance(row, dict) else row[0])


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


def _upsert_assessment_for_enrollment(enrollment_id: int, data: dict[str, Any]) -> None:
    placeholder = _placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM intake_assessments
        WHERE enrollment_id = {placeholder}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if existing:
        if g.get("db_kind") == "pg":
            db_execute(
                f"""
                UPDATE intake_assessments
                SET ace_score = {placeholder},
                    grit_score = {placeholder},
                    drug_court = {placeholder},
                    sexual_survivor = {placeholder},
                    dv_survivor = {placeholder},
                    human_trafficking_survivor = {placeholder},
                    warrants_unpaid = {placeholder},
                    mh_exam_completed = {placeholder},
                    med_exam_completed = {placeholder},
                    car_at_entry = {placeholder},
                    car_insurance_at_entry = {placeholder},
                    updated_at = {placeholder}
                WHERE enrollment_id = {placeholder}
                """,
                (
                    data["ace_score"],
                    data["grit_score"],
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
                    enrollment_id,
                ),
            )
            return

        db_execute(
            f"""
            UPDATE intake_assessments
            SET ace_score = {placeholder},
                grit_score = {placeholder},
                drug_court = {placeholder},
                sexual_survivor = {placeholder},
                dv_survivor = {placeholder},
                human_trafficking_survivor =
