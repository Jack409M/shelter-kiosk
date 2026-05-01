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


def _deny_case_manager_access():
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _request_form_data() -> dict[str, Any]:
    return request.form.to_dict(flat=True)


def _blank_none_values(form_data: dict[str, Any] | None) -> dict[str, Any]:
    if not form_data:
        return {}
    return {key: ("" if value is None else value) for key, value in form_data.items()}


def _render_intake_form(
    *,
    current_shelter: str,
    form_data: dict[str, Any] | None,
    review_passed: bool,
    is_edit_mode: bool,
    resident_id: int | None,
):
    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        ),
    )


def _render_intake_form_from_request(
    *,
    current_shelter: str,
    review_passed: bool,
    is_edit_mode: bool,
    resident_id: int | None,
):
    return _render_intake_form(
        current_shelter=current_shelter,
        form_data=_request_form_data(),
        review_passed=review_passed,
        is_edit_mode=is_edit_mode,
        resident_id=resident_id,
    )


def _intake_template_context(
    current_shelter: str,
    form_data: dict[str, Any] | None = None,
    review_passed: bool = False,
    is_edit_mode: bool = False,
    resident_id: int | None = None,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": _blank_none_values(form_data),
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

    if isinstance(value, int | bool):
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
        "receives_snap_at_entry",
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

    for field_name in [
        "car_at_entry",
        "car_insurance_at_entry",
        "receives_snap_at_entry",
    ]:
        if field_name in form_data:
            form_data[field_name] = _normalize_yes_no_value(form_data.get(field_name))

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


def _preserve_existing_update_values(
    *,
    resident: dict[str, Any],
    enrollment: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Protect update requests from partial form submissions.

    The intake edit screen normally posts a full form. If a browser, template change,
    or future partial-update endpoint omits optional fields, validation will normalize
    those missing values to None or derived zero values. This merge preserves existing
    persisted values for omitted fields so partial updates cannot silently erase data.
    """
    existing_data, selected_need_keys = intake_edit_form_data(
        resident=resident,
        enrollment=enrollment,
    )
    existing_data = _apply_intake_edit_aliases(existing_data)
    existing_data = _normalize_yes_no_fields(existing_data)
    existing_data = _apply_selected_need_flags(existing_data, selected_need_keys)

    merged = dict(data)

    for key, existing_value in existing_data.items():
        if key not in merged:
            merged[key] = existing_value
            continue

        if merged.get(key) is None and existing_value not in (None, ""):
            merged[key] = existing_value

    income_fields = (
        "employment_income_1",
        "employment_income_2",
        "employment_income_3",
        "ssi_ssdi_income",
        "tanf_income",
        "child_support_income",
        "alimony_income",
        "other_income",
    )
    income_was_not_submitted = not any(field_name in request.form for field_name in income_fields)
    if income_was_not_submitted and existing_data.get("income_at_entry") not in (None, ""):
        merged["income_at_entry"] = existing_data.get("income_at_entry")
        for field_name in income_fields:
            if existing_data.get(field_name) not in (None, ""):
                merged[field_name] = existing_data.get(field_name)

    family_fields = (
        "kids_at_dwc",
        "kids_served_outside_under_18",
        "kids_ages_0_5",
        "kids_ages_6_11",
        "kids_ages_12_17",
        "kids_reunited_while_in_program",
        "healthy_babies_born_at_dwc",
    )
    family_was_not_submitted = not any(field_name in request.form for field_name in family_fields)
    if family_was_not_submitted:
        for field_name in family_fields:
            if existing_data.get(field_name) not in (None, ""):
                merged[field_name] = existing_data.get(field_name)

    needs_were_not_submitted = "entry_need" not in request.form
    if needs_were_not_submitted and selected_need_keys:
        merged["entry_need_keys"] = selected_need_keys
        merged = _apply_selected_need_flags(merged, selected_need_keys)

    return merged


def _find_duplicate_for_data(*, data: dict[str, Any], current_shelter: str):
    return _find_possible_duplicate(
        first_name=data["first_name"],
        last_name=data["last_name"],
        birth_year=data["birth_year"],
        phone=data["phone"],
        email=data["email"],
        shelter=current_shelter,
        shelter_equals_sql=None,
    )


def _handle_save_draft(
    *,
    current_shelter: str,
    draft_id: int | None,
    review_passed: bool,
    is_edit_mode: bool,
    resident_id: int | None,
):
    first_name = clean(request.form.get("first_name"))
    last_name = clean(request.form.get("last_name"))

    if not first_name or not last_name:
        flash("Save Draft requires at least first name and last name.", "error")
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        )

    from routes.case_management_parts.intake_drafts import _save_intake_draft

    saved_draft_id = _save_intake_draft(
        current_shelter=current_shelter,
        form=request.form,
        draft_id=draft_id,
        status="draft",
    )

    flash("Intake draft saved.", "success")
    return redirect(url_for("case_management.intake_form", draft_id=saved_draft_id))


def _handle_review(
    *,
    current_shelter: str,
    draft_id: int | None,
    data: dict[str, Any],
):
    duplicate = _find_duplicate_for_data(data=data, current_shelter=current_shelter)

    review_result = save_intake_review_decision(
        current_shelter=current_shelter,
        form=request.form,
        draft_id=draft_id,
        data=data,
        duplicate=duplicate,
    )

    if review_result.duplicate_stop is not None:
        stop = review_result.duplicate_stop

        if stop.duplicate_identifier:
            flash(
                f"Possible duplicate resident found. Existing Resident ID: {stop.duplicate_identifier}. "
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
            f"Possible match: {stop.duplicate_first_name} {stop.duplicate_last_name} "
            f"(Resident ID: {stop.duplicate_identifier or 'unknown'}). "
            f"Review the duplicate before deciding whether to use the existing resident or create a new one.",
            "warning",
        )

        return redirect(url_for("case_management.intake_duplicate_review", draft_id=stop.draft_id))

    flash("No duplicate found. You can now continue the full intake and assessment.", "success")
    return redirect(
        url_for("case_management.intake_form", draft_id=review_result.approved_draft_id)
    )


def _handle_update(
    *,
    current_shelter: str,
    resident_id: int,
    data: dict[str, Any],
    review_passed: bool,
    is_edit_mode: bool,
):
    resident, enrollment = resident_enrollment_in_scope(resident_id, current_shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        flash("No enrollment found for update.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = int(enrollment["id"])
    protected_data = _preserve_existing_update_values(
        resident=dict(resident),
        enrollment=dict(enrollment),
        data=data,
    )

    try:
        update_intake(
            resident_id=resident_id,
            enrollment_id=enrollment_id,
            data=protected_data,
        )
    except LookupError:
        flash("No intake assessment found for update.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))
    except Exception:
        current_app.logger.exception(
            "Failed to update intake for resident_id=%s enrollment_id=%s",
            resident_id,
            enrollment_id,
        )
        flash(
            "Unable to save intake changes. Please try again or contact an administrator.", "error"
        )
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        )

    flash("Intake updated successfully.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _handle_create(
    *,
    current_shelter: str,
    draft_id: int | None,
    resident_id: int | None,
    data: dict[str, Any],
    review_passed: bool,
    is_edit_mode: bool,
):
    del resident_id
    del is_edit_mode

    try:
        create_result = create_intake(
            current_shelter=current_shelter,
            data=data,
            draft_id=draft_id,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to create intake for shelter=%s first_name=%s last_name=%s",
            current_shelter,
            data.get("first_name"),
            data.get("last_name"),
        )
        flash("Unable to save intake. Please try again or contact an administrator.", "error")
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=review_passed,
            is_edit_mode=False,
            resident_id=None,
        )

    flash(
        f"Resident created successfully. Resident ID: {create_result.resident_identifier}. Resident Code: {create_result.resident_code}",
        "success",
    )
    return redirect(url_for("case_management.intake_edit", resident_id=create_result.resident_id))


def intake_form_view():
    if not case_manager_allowed():
        return _deny_case_manager_access()

    init_db()

    current_shelter = _current_shelter()
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

    return _render_intake_form(
        current_shelter=current_shelter,
        form_data=form_data,
        review_passed=review_passed,
        is_edit_mode=False,
        resident_id=None,
    )


def intake_edit_view(resident_id: int):
    if not case_manager_allowed():
        return _deny_case_manager_access()

    init_db()

    current_shelter = _current_shelter()
    resident, enrollment = resident_enrollment_in_scope(resident_id, current_shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if not enrollment:
        abort(404)

    form_data, selected_need_keys = intake_edit_form_data(
        resident=dict(resident),
        enrollment=dict(enrollment),
    )

    form_data = _apply_intake_edit_aliases(form_data)
    form_data = _normalize_yes_no_fields(form_data)
    form_data = _apply_selected_need_flags(form_data, selected_need_keys)
    form_data["review_passed"] = "1"

    return _render_intake_form(
        current_shelter=current_shelter,
        form_data=form_data,
        review_passed=True,
        is_edit_mode=True,
        resident_id=resident_id,
    )


def submit_intake_assessment_view():
    if not case_manager_allowed():
        return _deny_case_manager_access()

    init_db()

    current_shelter = _current_shelter()
    action = (request.form.get("action") or "review").strip().lower()
    resident_id = parse_int(request.form.get("resident_id"))
    is_edit_mode = request.form.get("is_edit_mode") == "true" or resident_id is not None
    draft_id = parse_int(request.form.get("draft_id"))
    review_passed = _form_review_passed(request.form)

    if action == "save_draft":
        return _handle_save_draft(
            current_shelter=current_shelter,
            draft_id=draft_id,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        )

    data, errors = _validate_intake_form(request.form, current_shelter)

    if errors:
        for error in errors:
            flash(error, "error")
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        )

    if action == "review":
        return _handle_review(
            current_shelter=current_shelter,
            draft_id=draft_id,
            data=data,
        )

    if not review_passed:
        flash("Submit the basic identity information for review before finalizing intake.", "error")
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=False,
            is_edit_mode=is_edit_mode,
            resident_id=resident_id,
        )

    if is_edit_mode and resident_id:
        return _handle_update(
            current_shelter=current_shelter,
            resident_id=resident_id,
            data=data,
            review_passed=review_passed,
            is_edit_mode=is_edit_mode,
        )

    return _handle_create(
        current_shelter=current_shelter,
        draft_id=draft_id,
        resident_id=resident_id,
        data=data,
        review_passed=review_passed,
        is_edit_mode=is_edit_mode,
    )
