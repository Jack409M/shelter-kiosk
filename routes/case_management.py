from __future__ import annotations

from datetime import date
import secrets
from typing import Any

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
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


def _generate_resident_identifier() -> str:
    placeholder = _placeholder()

    for _ in range(25):
        candidate = str(secrets.randbelow(90000000) + 10000000)

        existing = db_fetchone(
            f"""
            SELECT id
            FROM residents
            WHERE resident_identifier = {placeholder}
            LIMIT 1
            """,
            (candidate,),
        )

        if not existing:
            return candidate

    raise RuntimeError("Could not generate a unique resident identifier.")


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
    }


def _validate_intake_form(form: Any, shelter: str) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "first_name": _clean(form.get("first_name")),
        "middle_name": _clean(form.get("middle_name")),
        "last_name": _clean(form.get("last_name")),
        "dob": _clean(form.get("dob")),
        "phone": _clean(form.get("phone")),
        "email": _clean(form.get("email")),
        "ssn_last4": _clean(form.get("ssn_last4")),
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
        "domestic_violence_history": _clean(form.get("domestic_violence_history")),
        "human_trafficking_history": _clean(form.get("human_trafficking_history")),
        "mental_health_need": _clean(form.get("mental_health_need")),
        "medical_need": _clean(form.get("medical_need")),
        "substance_use_need": _clean(form.get("substance_use_need")),
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

    dob_date = _parse_iso_date(data["dob"])
    if data["dob"] and dob_date is None:
        errors.append("Date of Birth must be a valid date.")

    entry_date = _parse_iso_date(data["entry_date"])
    if data["entry_date"] and entry_date is None:
        errors.append("Date Entered must be a valid date.")

    sobriety_date = _parse_iso_date(data["sobriety_date"])
    if data["sobriety_date"] and sobriety_date is None:
        errors.append("Sobriety Date must be a valid date.")

    today = date.today()

    if dob_date and dob_date > today:
        errors.append("Date of Birth cannot be in the future.")

    if entry_date and entry_date > today:
        errors.append("Date Entered cannot be in the future.")

    if dob_date and entry_date and dob_date > entry_date:
        errors.append("Date of Birth cannot be later than Date Entered.")

    if sobriety_date and entry_date and sobriety_date > entry_date:
        errors.append("Sobriety Date cannot be later than Date Entered.")

    ssn_last4 = _digits_only(data["ssn_last4"])
    if data["ssn_last4"] and len(ssn_last4) != 4:
        errors.append("Last 4 of SSN must be exactly 4 digits.")
    data["ssn_last4"] = ssn_last4 or None

    phone_digits = _digits_only(data["phone"])
    if data["phone"] and len(phone_digits) < 10:
        errors.append("Phone must contain at least 10 digits.")

    emergency_phone_digits = _digits_only(data["emergency_contact_phone"])
    if data["emergency_contact_phone"] and len(emergency_phone_digits) < 10:
        errors.append("Emergency Contact Phone must contain at least 10 digits.")

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
    dob: str | None,
    phone: str | None,
    email: str | None,
    shelter: str,
) -> Any:
    placeholder = _placeholder()

    if email:
        existing = db_fetchone(
            f"""
            SELECT id, first_name, last_name, dob, phone, email, resident_identifier
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
            SELECT id, first_name, last_name, dob, phone, email, resident_identifier
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
              AND COALESCE(phone, '') = {placeholder}
            LIMIT 1
            """,
            (shelter, phone),
        )
        if existing:
            return existing

    if first_name and last_name and dob:
        existing = db_fetchone(
            f"""
            SELECT id, first_name, last_name, dob, phone, email, resident_identifier
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
              AND LOWER(COALESCE(first_name, '')) = LOWER({placeholder})
              AND LOWER(COALESCE(last_name, '')) = LOWER({placeholder})
              AND COALESCE(dob, '') = {placeholder}
            LIMIT 1
            """,
            (shelter, first_name, last_name, dob),
        )
        if existing:
            return existing

    return None


def _insert_resident(data: dict[str, Any], shelter: str) -> tuple[int, str]:
    placeholder = _placeholder()
    resident_identifier = _generate_resident_identifier()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO residents
            (
                resident_identifier,
                first_name,
                last_name,
                dob,
                phone,
                email,
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
                TRUE,
                NOW()
            )
            RETURNING id
            """,
            (
                resident_identifier,
                data["first_name"],
                data["last_name"],
                data["dob"],
                data["phone"],
                data["email"],
                shelter,
            ),
        )
        return int(row["id"]), resident_identifier

    db_execute(
        f"""
        INSERT INTO residents
        (
            resident_identifier,
            first_name,
            last_name,
            dob,
            phone,
            email,
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
            1,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_identifier,
            data["first_name"],
            data["last_name"],
            data["dob"],
            data["phone"],
            data["email"],
            shelter,
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"]), resident_identifier


def _insert_program_enrollment(resident_id: int, data: dict[str, Any], shelter: str) -> None:
    placeholder = _placeholder()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO program_enrollments
            (
                resident_id,
                shelter,
                program_status,
                entry_date,
                created_at
            )
            VALUES (
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                NOW()
            )
            """,
            (
                resident_id,
                shelter,
                data["program_status"] or "active",
                data["entry_date"],
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            program_status,
            entry_date,
            created_at
        )
        VALUES (
            {placeholder},
            {placeholder},
            {placeholder},
            {placeholder},
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


@case_management.get("")
@require_login
@require_shelter
def index():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))

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

    return render_template(
        "case_management/index.html",
        residents=residents,
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

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(current_shelter=current_shelter),
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
    data, errors = _validate_intake_form(request.form, current_shelter)

    duplicate = _find_possible_duplicate(
        first_name=data["first_name"],
        last_name=data["last_name"],
        dob=data["dob"],
        phone=data["phone"],
        email=data["email"],
        shelter=current_shelter,
    )

    if duplicate:
        duplicate_id = duplicate["id"] if isinstance(duplicate, dict) else duplicate[0]
        duplicate_identifier = duplicate["resident_identifier"] if isinstance(duplicate, dict) else None
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
                form_data=dict(request.form),
            ),
        )

    resident_id, resident_identifier = _insert_resident(data, current_shelter)
    _insert_program_enrollment(resident_id, data, current_shelter)

    flash(
        f"Resident created successfully. Resident ID: {resident_identifier}",
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
