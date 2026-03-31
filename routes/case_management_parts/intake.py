from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from core.constants import EDUCATION_LEVEL_OPTIONS
from core.db import db_execute, db_fetchone, db_transaction
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.intake_drafts import _complete_intake_draft
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_drafts import _save_intake_draft
from routes.case_management_parts.intake_inserts import _build_family_snapshot_payload
from routes.case_management_parts.intake_inserts import _build_intake_assessment_payload
from routes.case_management_parts.intake_inserts import _insert_family_snapshot
from routes.case_management_parts.intake_inserts import _insert_intake_assessment
from routes.case_management_parts.intake_inserts import _insert_program_enrollment
from routes.case_management_parts.intake_inserts import _insert_resident
from routes.case_management_parts.intake_validation import _find_possible_duplicate
from routes.case_management_parts.intake_validation import _validate_intake_form
from routes.case_management_parts.needs import OFFICIAL_NEEDS
from routes.case_management_parts.needs import build_triggered_needs
from routes.case_management_parts.needs import list_enrollment_need_keys
from routes.case_management_parts.needs import sync_enrollment_needs


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
        "sexual_survivor",
        "domestic_violence_history",
        "human_trafficking_history",
        "drug_court",
        "felony_history",
        "probation_parole",
        "car_at_entry",
        "car_insurance_at_entry",
    ]

    for field_name in yes_no_fields:
        if field_name in form_data:
            form_data[field_name] = _normalize_yes_no_value(form_data.get(field_name))

    for need in OFFICIAL_NEEDS:
        field_name = f"need_{need['need_key']}"
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
        "employment_status": "employment_status_at_entry",
        "last_zipcode_residence": "last_zipcode_of_residence",
    }

    for form_key, db_key in field_aliases.items():
        if form_data.get(form_key) in (None, "") and db_key in form_data:
            form_data[form_key] = form_data.get(db_key)

    if "car_at_entry" in form_data:
        form_data["car_at_entry"] = _normalize_yes_no_value(form_data.get("car_at_entry"))

    if "car_insurance_at_entry" in form_data:
        form_data["car_insurance_at_entry"] = _normalize_yes_no_value(form_data.get("car_insurance_at_entry"))

    return form_data


def _apply_selected_need_flags(
    form_data: dict[str, Any],
    selected_need_keys: list[str],
) -> dict[str, Any]:
    for need in OFFICIAL_NEEDS:
        field_name = f"need_{need['need_key']}"
        if need["need_key"] in selected_need_keys:
            form_data[field_name] = "yes"
        elif field_name not in form_data:
            form_data[field_name] = ""

    return form_data


def _resident_enrollment_in_scope(resident_id: int, current_shelter: str):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        LIMIT 1
        """,
        (resident_id, current_shelter),
    )

    if not resident:
        return None, None

    enrollment = fetch_current_enrollment_for_resident(resident_id)
    return resident, enrollment


def _latest_intake_for_enrollment(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT *
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


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

        form_data = _normalize_yes_no_fields(form_data)
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
    resident, enrollment = _resident_enrollment_in_scope(resident_id, current_shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

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

    selected_need_keys = list_enrollment_need_keys(enrollment_id)

    if not selected_need_keys and intake:
        selected_need_keys = [
            need["need_key"]
            for need in build_triggered_needs(intake_row=dict(intake))
        ]

    form_data = _apply_selected_need_flags(form_data, selected_need_keys)
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
        resident, enrollment = _resident_enrollment_in_scope(resident_id, current_shelter)

        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("case_management.index"))

        if not enrollment:
            flash("No enrollment found for update.", "error")
            return redirect(url_for("case_management.resident_case", resident_id=resident_id))

        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
        existing_intake = _latest_intake_for_enrollment(enrollment_id)

        if not existing_intake:
            flash("No intake assessment found for update.", "error")
            return redirect(url_for("case_management.resident_case", resident_id=resident_id))

        intake_assessment_id = existing_intake["id"] if isinstance(existing_intake, dict) else existing_intake[0]
        now = datetime.utcnow().isoformat()
        ph = placeholder()
        intake_payload = _build_intake_assessment_payload(data)
        family_payload = _build_family_snapshot_payload(data)

        try:
            with db_transaction():
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
                        city = {ph},
                        county = {ph},
                        last_zipcode_residence = {ph},
                        length_of_time_in_amarillo = {ph},
                        income_at_entry = {ph},
                        education_at_entry = {ph},
                        treatment_grad_date = {ph},
                        sobriety_date = {ph},
                        days_sober_at_entry = {ph},
                        drug_of_choice = {ph},
                        ace_score = {ph},
                        grit_score = {ph},
                        veteran = {ph},
                        disability = {ph},
                        marital_status = {ph},
                        notes_basic = {ph},
                        entry_notes = {ph},
                        initial_snapshot_notes = {ph},
                        trauma_notes = {ph},
                        barrier_notes = {ph},
                        place_staying_before_entry = {ph},
                        entry_felony_conviction = {ph},
                        entry_parole_probation = {ph},
                        drug_court = {ph},
                        sexual_survivor = {ph},
                        dv_survivor = {ph},
                        human_trafficking_survivor = {ph},
                        warrants_unpaid = {ph},
                        mh_exam_completed = {ph},
                        med_exam_completed = {ph},
                        car_at_entry = {ph},
                        car_insurance_at_entry = {ph},
                        pregnant_at_entry = {ph},
                        dental_need_at_entry = {ph},
                        vision_need_at_entry = {ph},
                        employment_status_at_entry = {ph},
                        mental_health_need_at_entry = {ph},
                        medical_need_at_entry = {ph},
                        substance_use_need_at_entry = {ph},
                        id_documents_status_at_entry = {ph},
                        has_drivers_license = {ph},
                        has_social_security_card = {ph},
                        parenting_class_needed = {ph},
                        dwc_level_today = {ph},
                        updated_at = {ph}
                    WHERE id = {ph}
                    """,
                    (
                        intake_payload["city"],
                        intake_payload["county"],
                        intake_payload["last_zipcode_residence"],
                        intake_payload["length_of_time_in_amarillo"],
                        intake_payload["income_at_entry"],
                        intake_payload["education_at_entry"],
                        intake_payload["treatment_grad_date"],
                        intake_payload["sobriety_date"],
                        intake_payload["days_sober_at_entry"],
                        intake_payload["drug_of_choice"],
                        intake_payload["ace_score"],
                        intake_payload["grit_score"],
                        intake_payload["veteran"],
                        intake_payload["disability"],
                        intake_payload["marital_status"],
                        intake_payload["notes_basic"],
                        intake_payload["entry_notes"],
                        intake_payload["initial_snapshot_notes"],
                        intake_payload["trauma_notes"],
                        intake_payload["barrier_notes"],
                        intake_payload["place_staying_before_entry"],
                        intake_payload["entry_felony_conviction"],
                        intake_payload["entry_parole_probation"],
                        intake_payload["drug_court"],
                        intake_payload["sexual_survivor"],
                        intake_payload["dv_survivor"],
                        intake_payload["human_trafficking_survivor"],
                        intake_payload["warrants_unpaid"],
                        intake_payload["mh_exam_completed"],
                        intake_payload["med_exam_completed"],
                        intake_payload["car_at_entry"],
                        intake_payload["car_insurance_at_entry"],
                        intake_payload["pregnant_at_entry"],
                        intake_payload["dental_need_at_entry"],
                        intake_payload["vision_need_at_entry"],
                        intake_payload["employment_status_at_entry"],
                        intake_payload["mental_health_need_at_entry"],
                        intake_payload["medical_need_at_entry"],
                        intake_payload["substance_use_need_at_entry"],
                        intake_payload["id_documents_status_at_entry"],
                        intake_payload["has_drivers_license"],
                        intake_payload["has_social_security_card"],
                        intake_payload["parenting_class_needed"],
                        intake_payload["dwc_level_today"],
                        now,
                        intake_assessment_id,
                    ),
                )

                existing_family = db_fetchone(
                    f"""
                    SELECT id
                    FROM family_snapshots
                    WHERE enrollment_id = {ph}
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (enrollment_id,),
                )

                if existing_family:
                    db_execute(
                        f"""
                        UPDATE family_snapshots
                        SET
                            kids_at_dwc = {ph},
                            kids_served_outside_under_18 = {ph},
                            kids_ages_0_5 = {ph},
                            kids_ages_6_11 = {ph},
                            kids_ages_12_17 = {ph},
                            kids_reunited_while_in_program = {ph},
                            healthy_babies_born_at_dwc = {ph},
                            updated_at = {ph}
                        WHERE enrollment_id = {ph}
                        """,
                        (
                            family_payload["kids_at_dwc"],
                            family_payload["kids_served_outside_under_18"],
                            family_payload["kids_ages_0_5"],
                            family_payload["kids_ages_6_11"],
                            family_payload["kids_ages_12_17"],
                            family_payload["kids_reunited_while_in_program"],
                            family_payload["healthy_babies_born_at_dwc"],
                            now,
                            enrollment_id,
                        ),
                    )
                else:
                    _insert_family_snapshot(enrollment_id, data)

                sync_enrollment_needs(
                    enrollment_id,
                    selected_need_keys=data.get("entry_need_keys", []),
                )
        except Exception:
            current_app.logger.exception(
                "Failed to update intake for resident_id=%s enrollment_id=%s",
                resident_id,
                enrollment_id,
            )
            flash("Unable to save intake changes. Please try again or contact an administrator.", "error")
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

        flash("Intake updated successfully.", "success")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    try:
        with db_transaction():
            final_duplicate = _find_possible_duplicate(
                first_name=data["first_name"],
                last_name=data["last_name"],
                birth_year=data["birth_year"],
                phone=data["phone"],
                email=data["email"],
                shelter=current_shelter,
                shelter_equals_sql=shelter_equals_sql,
            )

            if final_duplicate:
                duplicate_identifier, duplicate_first_name, duplicate_last_name = _duplicate_identity(final_duplicate)

                saved_draft_id = _save_intake_draft(
                    current_shelter=current_shelter,
                    form=request.form,
                    draft_id=draft_id,
                    status="pending_duplicate_review",
                )

                flash(
                    f"Possible duplicate resident found during final save: "
                    f"{duplicate_first_name} {duplicate_last_name} "
                    f"(Resident ID: {duplicate_identifier or 'unknown'}). "
                    f"No new resident was created.",
                    "warning",
                )
                return redirect(
                    url_for("case_management.intake_duplicate_review", draft_id=saved_draft_id)
                )

            new_resident_id, resident_identifier, resident_code = _insert_resident(data, current_shelter)
            enrollment_id = _insert_program_enrollment(new_resident_id, data, current_shelter)
            _insert_intake_assessment(enrollment_id, data)
            _insert_family_snapshot(enrollment_id, data)

            if draft_id is not None:
                _complete_intake_draft(draft_id)

    except Exception:
        current_app.logger.exception(
            "Failed to create intake for shelter=%s first_name=%s last_name=%s",
            current_shelter,
            data.get("first_name"),
            data.get("last_name"),
        )
        flash("Unable to save intake. Please try again or contact an administrator.", "error")
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

    flash(
        f"Resident created successfully. Resident ID: {resident_identifier}. Resident Code: {resident_code}",
        "success",
    )
    return redirect(url_for("case_management.intake_edit", resident_id=new_resident_id))
