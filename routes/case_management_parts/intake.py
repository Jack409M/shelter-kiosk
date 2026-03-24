from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import abort, flash, redirect, render_template, request, session, url_for

from core.constants import EDUCATION_LEVEL_OPTIONS
from core.db import db_execute, db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.helpers import yes_no_to_int
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
    is_edit_mode: bool = False,
    resident_id: int | None = None,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": form_data or {},
        "review_passed": review_passed,
        "is_edit_mode": is_edit_mode,
        "resident_id": resident_id,
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


def _normalize_yes_no_value(value: Any) -> str:
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


def _normalize_yes_no_fields(form_data: dict[str, Any]) -> dict[str, Any]:
    yes_no_fields = [
        "veteran",
        "pregnant",
        "dental_need",
        "vision_need",
        "sexual_survivor",
        "domestic_violence_history",
        "human_trafficking_history",
        "drug_court",
        "warrants_unpaid",
        "mental_health_need",
        "medical_need",
        "mh_exam_completed",
        "med_exam_completed",
        "substance_use_need",
        "parenting_class_needed",
        "felony_history",
        "probation_parole",
    ]

    for field_name in yes_no_fields:
        if field_name in form_data:
            form_data[field_name] = _normalize_yes_no_value(form_data.get(field_name))

    return form_data


def _apply_intake_edit_aliases(form_data: dict[str, Any]) -> dict[str, Any]:
    field_aliases = {
        "prior_living": "place_staying_before_entry",
        "felony_history": "entry_felony_conviction",
        "probation_parole": "entry_parole_probation",
        "domestic_violence_history": "dv_survivor",
        "human_trafficking_history": "human_trafficking_survivor",
        "pregnant": "pregnant_at_entry",
        "dental_need": "dental_need_at_entry",
        "vision_need": "vision_need_at_entry",
        "employment_status": "employment_status_at_entry",
        "mental_health_need": "mental_health_need_at_entry",
        "medical_need": "medical_need_at_entry",
        "substance_use_need": "substance_use_need_at_entry",
        "id_documents_status": "id_documents_status_at_entry",
        "last_zipcode_residence": "last_zipcode_of_residence",
    }

    for form_key, db_key in field_aliases.items():
        if form_data.get(form_key) in (None, "") and db_key in form_data:
            form_data[form_key] = form_data.get(db_key)

    return form_data


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


def intake_edit_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    current_shelter = normalize_shelter_name(session.get("shelter"))

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {ph}
        """,
        (resident_id,),
    )

    if not resident:
        abort(404)

    enrollment = db_fetchone(
        f"""
        SELECT *
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    if not enrollment:
        abort(404)

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    intake = db_fetchone(
        f"""
        SELECT *
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    family = db_fetchone(
        f"""
        SELECT *
        FROM family_snapshots
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    form_data: dict[str, Any] = {}

    if resident:
        form_data.update(dict(resident))

    if enrollment:
        form_data.update(dict(enrollment))

    if intake:
        form_data.update(dict(intake))

    if family:
        form_data.update(dict(family))

    form_data = _apply_intake_edit_aliases(form_data)
    form_data = _normalize_yes_no_fields(form_data)
    form_data["review_passed"] = "1"

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
            review_passed=True,
            is_edit_mode=True,
            resident_id=resident_id,
        ),
    )


def submit_intake_assessment_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "review").strip().lower()
    resident_id = parse_int(request.form.get("resident_id"))
    is_edit_mode = request.form.get("is_edit_mode") == "true" or resident_id is not None
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
                    is_edit_mode=is_edit_mode,
                    resident_id=resident_id,
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
                is_edit_mode=is_edit_mode,
                resident_id=resident_id,
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
                is_edit_mode=is_edit_mode,
                resident_id=resident_id,
            ),
        )

    if is_edit_mode and resident_id:
        ph = placeholder()

        enrollment = db_fetchone(
            f"""
            SELECT id
            FROM program_enrollments
            WHERE resident_id = {ph}
            ORDER BY id DESC
            LIMIT 1
            """,
            (resident_id,),
        )

        if not enrollment:
            flash("No enrollment found for update.", "error")
            return redirect(url_for("case_management.resident_case", resident_id=resident_id))

        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            UPDATE residents
            SET
                first_name = {ph},
                last_name = {ph},
                birth_year = {ph},
                phone = {ph},
                email = {ph},
                emergency_contact_name = {ph},
                emergency_contact_relationship = {ph},
                emergency_contact_phone = {ph},
                gender = {ph},
                race = {ph},
                ethnicity = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                data.get("first_name"),
                data.get("last_name"),
                data.get("birth_year"),
                data.get("phone"),
                data.get("email"),
                data.get("emergency_contact_name"),
                data.get("emergency_contact_relationship"),
                data.get("emergency_contact_phone"),
                data.get("gender"),
                data.get("race"),
                data.get("ethnicity"),
                now,
                resident_id,
            ),
        )

        db_execute(
            f"""
            UPDATE program_enrollments
            SET
                entry_date = {ph},
                program_status = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                data.get("entry_date"),
                data.get("program_status"),
                now,
                enrollment_id,
            ),
        )

        db_execute(
            f"""
            UPDATE intake_assessments
            SET
                veteran = {ph},
                notes_basic = {ph},
                place_staying_before_entry = {ph},
                sobriety_date = {ph},
                treatment_grad_date = {ph},
                drug_of_choice = {ph},
                income_at_entry = {ph},
                education_at_entry = {ph},
                disability = {ph},
                length_of_time_in_amarillo = {ph},
                marital_status = {ph},
                city = {ph},
                last_zipcode_residence = {ph},
                entry_notes = {ph},
                pregnant_at_entry = {ph},
                dental_need_at_entry = {ph},
                vision_need_at_entry = {ph},
                employment_status_at_entry = {ph},
                id_documents_status_at_entry = {ph},
                initial_snapshot_notes = {ph},
                ace_score = {ph},
                grit_score = {ph},
                sexual_survivor = {ph},
                dv_survivor = {ph},
                human_trafficking_survivor = {ph},
                drug_court = {ph},
                warrants_unpaid = {ph},
                mental_health_need_at_entry = {ph},
                medical_need_at_entry = {ph},
                mh_exam_completed = {ph},
                med_exam_completed = {ph},
                substance_use_need_at_entry = {ph},
                parenting_class_needed = {ph},
                dwc_level_today = {ph},
                trauma_notes = {ph},
                entry_felony_conviction = {ph},
                entry_parole_probation = {ph},
                barrier_notes = {ph},
                updated_at = {ph}
            WHERE enrollment_id = {ph}
            """,
            (
                yes_no_to_int(data.get("veteran")),
                data.get("notes_basic"),
                data.get("prior_living"),
                data.get("sobriety_date"),
                data.get("treatment_grad_date"),
                data.get("drug_of_choice"),
                data.get("income_at_entry"),
                data.get("education_at_entry"),
                data.get("disability"),
                data.get("length_of_time_in_amarillo"),
                data.get("marital_status"),
                data.get("city"),
                data.get("last_zipcode_residence"),
                data.get("entry_notes"),
                yes_no_to_int(data.get("pregnant")),
                yes_no_to_int(data.get("dental_need")),
                yes_no_to_int(data.get("vision_need")),
                data.get("employment_status"),
                data.get("id_documents_status"),
                data.get("initial_snapshot_notes"),
                data.get("ace_score"),
                data.get("grit_score"),
                yes_no_to_int(data.get("sexual_survivor")),
                yes_no_to_int(data.get("domestic_violence_history")),
                yes_no_to_int(data.get("human_trafficking_history")),
                yes_no_to_int(data.get("drug_court")),
                yes_no_to_int(data.get("warrants_unpaid")),
                yes_no_to_int(data.get("mental_health_need")),
                yes_no_to_int(data.get("medical_need")),
                yes_no_to_int(data.get("mh_exam_completed")),
                yes_no_to_int(data.get("med_exam_completed")),
                yes_no_to_int(data.get("substance_use_need")),
                yes_no_to_int(data.get("parenting_class_needed")),
                data.get("dwc_level_today"),
                data.get("trauma_notes"),
                yes_no_to_int(data.get("felony_history")),
                yes_no_to_int(data.get("probation_parole")),
                data.get("barrier_notes"),
                now,
                enrollment_id,
            ),
        )

        db_execute(
            f"""
            UPDATE family_snapshots
            SET updated_at = {ph}
            WHERE enrollment_id = {ph}
            """,
            (
                now,
                enrollment_id,
            ),
        )

        flash("Intake updated successfully.", "success")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

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
    return redirect(url_for("case_management.intake_edit", resident_id=resident_id))


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
                TRUE,
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


def edit_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    service = db_fetchone(
        f"""
        SELECT
            id,
            resident_child_id,
            service_type,
            outcome,
            quantity,
            unit,
            notes,
            service_date
        FROM child_services
        WHERE id = {ph}
        """,
        (service_id,),
    )

    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    return render_template(
        "case_management/edit_child_service.html",
        service=service,
    )


def child_services_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    child = db_fetchone(
        f"""
        SELECT
            id,
            resident_id
        FROM resident_children
        WHERE id = {ph}
        """,
        (child_id,),
    )

    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"] if isinstance(child, dict) else child[1]

    enrollment = db_fetchone(
        f"""
        SELECT
            id
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    if not enrollment:
        flash("No active enrollment found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    if request.method == "POST":
        service_type = clean(request.form.get("service_type"))
        outcome = clean(request.form.get("outcome"))
        quantity = parse_int(request.form.get("quantity"))
        unit = clean(request.form.get("unit"))
        notes = clean(request.form.get("notes"))
        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            INSERT INTO child_services
            (
                resident_child_id,
                enrollment_id,
                service_date,
                service_type,
                outcome,
                quantity,
                unit,
                notes,
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
                {ph},
                {ph},
                {ph},
                {ph},
                {ph}
            )
            """,
            (
                child_id,
                enrollment_id,
                now,
                service_type,
                outcome,
                quantity,
                unit,
                notes,
                now,
                now,
            ),
        )

        flash("Child service added.", "success")
        return redirect(url_for("case_management.child_services", child_id=child_id))

    services = db_fetchall(
        f"""
        SELECT
            id,
            service_date,
            service_type,
            quantity,
            unit,
            outcome,
            notes
        FROM child_services
        WHERE resident_child_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (child_id,),
    )

    return render_template(
        "case_management/child_services.html",
        child_id=child_id,
        services=services,
    )
