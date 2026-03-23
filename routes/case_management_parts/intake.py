from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.constants import EDUCATION_LEVEL_OPTIONS
from core.db import db_execute, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.intake_drafts import _complete_intake_draft
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_drafts import _save_intake_draft
from routes.case_management_parts.intake_inserts import _insert_family_snapshot
from routes.case_management_parts.intake_inserts import _insert_intake_assessment
from routes.case_management_parts.intake_inserts import _insert_program_enrollment
from routes.case_management_parts.intake_inserts import _insert_resident
from routes.case_management_parts.intake_validation import _find_possible_duplicate
from routes.case_management_parts.intake_validation import _validate_intake_form


def _intake_template_context(
    current_shelter: str,
    form_data: dict[str, Any] | None = None,
    review_passed: bool = False,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": form_data or {},
        "review_passed": review_passed,
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


def _duplicate_identity(duplicate: Any) -> tuple[str | None, str, str]:
    duplicate_identifier = (
        duplicate["resident_identifier"]
        if isinstance(duplicate, dict)
        else duplicate[6]
    )
    duplicate_first_name = (
        duplicate["first_name"]
        if isinstance(duplicate, dict)
        else duplicate[2]
    )
    duplicate_last_name = (
        duplicate["last_name"]
        if isinstance(duplicate, dict)
        else duplicate[3]
    )
    return duplicate_identifier, duplicate_first_name or "", duplicate_last_name or ""


def _form_review_passed(form_source: Any) -> bool:
    value = clean(form_source.get("review_passed"))
    return value in {"1", "true", "yes", "on"}


def intake_form_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    draft_id = parse_int(request.args.get("draft_id"))
    form_data: dict[str, Any] | None = None
    review_passed = False

    if draft_id is not None:
        form_data = _load_intake_draft(current_shelter, draft_id)
        if not form_data:
            flash("Intake draft not found.", "error")
            return redirect(url_for("case_management.intake_index"))

        review_passed = _form_review_passed(form_data)

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
            review_passed=review_passed,
        ),
    )


def submit_intake_assessment_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "review").strip().lower()
    draft_id = parse_int(request.form.get("draft_id"))
    review_passed = _form_review_passed(request.form)

    if action == "save_draft":
        first_name = clean(request.form.get("first_name"))
        last_name = clean(request.form.get("last_name"))

        if not first_name or not last_name:
            flash("Save Draft requires at least first name and last name.", "error")
            return render_template(
                "case_management/intake_assessment.html",
                **_intake_template_context(
                    current_shelter=current_shelter,
                    form_data=request.form.to_dict(flat=True),
                    review_passed=review_passed,
                ),
            )

        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=request.form,
            draft_id=draft_id,
            status="draft",
        )

        flash("Intake draft saved.", "success")
        return redirect(url_for("case_management.intake_form", draft_id=saved_draft_id))

    data, errors = _validate_intake_form(request.form, current_shelter)

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/intake_assessment.html",
            **_intake_template_context(
                current_shelter=current_shelter,
                form_data=request.form.to_dict(flat=True),
                review_passed=review_passed,
            ),
        )

    if action == "review":
        duplicate = _find_possible_duplicate(
            first_name=data["first_name"],
            last_name=data["last_name"],
            birth_year=data["birth_year"],
            phone=data["phone"],
            email=data["email"],
            shelter=current_shelter,
            shelter_equals_sql=shelter_equals_sql,
        )

        if duplicate:
            duplicate_identifier, duplicate_first_name, duplicate_last_name = _duplicate_identity(duplicate)

            saved_draft_id = _save_intake_draft(
                current_shelter=current_shelter,
                form=request.form,
                draft_id=draft_id,
                status="pending_duplicate_review",
            )

            if duplicate_identifier:
                flash(
                    f"Possible duplicate resident found. Existing Resident ID: {duplicate_identifier}. "
                    f"Your intake was saved for review and no new resident was created.",
                    "warning",
                )
            else:
                flash(
                    "Possible duplicate resident found. Your intake was saved for review and "
                    "no new resident was created.",
                    "warning",
                )

            flash(
                f"Possible match: {duplicate_first_name} {duplicate_last_name} "
                f"(Resident ID: {duplicate_identifier or 'unknown'}). "
                f"Review the duplicate before deciding whether to use the existing resident or create a new one.",
                "warning",
            )

            return redirect(
                url_for("case_management.intake_duplicate_review", draft_id=saved_draft_id)
            )

        review_form = request.form.copy()
        review_form["review_passed"] = "1"

        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=review_form,
            draft_id=draft_id,
            status="draft",
        )

        flash("No duplicate found. You can now continue the full intake and assessment.", "success")
        return redirect(url_for("case_management.intake_form", draft_id=saved_draft_id))

    if not review_passed:
        flash("Submit the basic identity information for review before finalizing intake.", "error")
        return render_template(
            "case_management/intake_assessment.html",
            **_intake_template_context(
                current_shelter=current_shelter,
                form_data=request.form.to_dict(flat=True),
                review_passed=False,
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


def family_intake_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    ph = placeholder()

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))

        if not child_name:
            flash("Child name is required.", "error")
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
            )

        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            INSERT INTO resident_children
            (
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                is_active,
                created_at,
                updated_at
            )
            VALUES
            (
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                1,
                {ph},
                {ph}
            )
            """,
            (
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                now,
                now,
            ),
        )

        flash("Child added.", "success")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    return render_template(
        "case_management/family_intake.html",
        resident_id=resident_id,
    )


def edit_child_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    child = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            child_name,
            birth_year,
            relationship,
            living_status
        FROM resident_children
        WHERE id = {ph}
        """,
        (child_id,),
    )

    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))

        db_execute(
            f"""
            UPDATE resident_children
            SET
                child_name = {ph},
                birth_year = {ph},
                relationship = {ph},
                living_status = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                child_name,
                birth_year,
                relationship,
                living_status,
                datetime.utcnow().isoformat(),
                child_id,
            ),
        )

        resident_id = child["resident_id"] if isinstance(child, dict) else child[1]

        flash("Child updated.", "success")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    return render_template(
        "case_management/edit_child.html",
        child=child,
    )
