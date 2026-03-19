from __future__ import annotations

import json
from typing import Any

from flask import flash, g, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.helpers import yes_no_to_int


# ============================================================================
# Assessment Draft Persistence
# ----------------------------------------------------------------------------
# This block was extracted from routes/case_management.py.
# ============================================================================

def _save_assessment_draft(
    current_shelter: str,
    form_data: dict[str, Any],
    resident_id: int,
    draft_id: int | None = None,
) -> int:
    ph = placeholder()
    payload = json.dumps(form_data, ensure_ascii=False)
    now = utcnow_iso()

    if g.get("db_kind") == "pg":
        if draft_id is not None:
            row = db_fetchone(
                f"""
                UPDATE assessment_drafts
                SET resident_id = {ph},
                    form_payload = {ph},
                    updated_at = {ph}
                WHERE id = {ph}
                  AND status = 'draft'
                  AND LOWER(COALESCE(shelter, '')) = {ph}
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
                {ph},
                {ph},
                {ph},
                'draft',
                {ph},
                {ph},
                {ph}
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
            SET resident_id = {ph},
                form_payload = {ph},
                updated_at = {ph}
            WHERE id = {ph}
              AND status = 'draft'
              AND LOWER(COALESCE(shelter, '')) = {ph}
            """,
            (resident_id, payload, now, draft_id, current_shelter),
        )
        existing = db_fetchone(
            f"""
            SELECT id
            FROM assessment_drafts
            WHERE id = {ph}
              AND status = 'draft'
              AND LOWER(COALESCE(shelter, '')) = {ph}
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
            {ph},
            {ph},
            {ph},
            'draft',
            {ph},
            {ph},
            {ph}
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
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            form_payload
        FROM assessment_drafts
        WHERE id = {ph}
          AND status = 'draft'
          AND LOWER(COALESCE(shelter, '')) = {ph}
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
    ph = placeholder()

    db_execute(
        f"""
        UPDATE assessment_drafts
        SET status = 'completed',
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (utcnow_iso(), draft_id),
    )


# ============================================================================
# Assessment Validation and Persistence
# ----------------------------------------------------------------------------
# This block was extracted from routes/case_management.py.
# ============================================================================

def _validate_assessment_form(form: Any) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "resident_id": clean(form.get("resident_id")),
        "ace_score": clean(form.get("ace_score")),
        "grit_score": clean(form.get("grit_score")),
        "sexual_survivor": clean(form.get("sexual_survivor")),
        "domestic_violence_history": clean(form.get("domestic_violence_history")),
        "human_trafficking_history": clean(form.get("human_trafficking_history")),
        "drug_court": clean(form.get("drug_court")),
        "warrants_unpaid": clean(form.get("warrants_unpaid")),
        "mh_exam_completed": clean(form.get("mh_exam_completed")),
        "med_exam_completed": clean(form.get("med_exam_completed")),
        "car_at_entry": clean(form.get("car_at_entry")),
        "car_insurance_at_entry": clean(form.get("car_insurance_at_entry")),
    }

    errors: list[str] = []

    resident_id = parse_int(data["resident_id"])
    if resident_id is None:
        errors.append("Resident is required.")
    data["resident_id"] = resident_id

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

    yes_no_fields = [
        "sexual_survivor",
        "domestic_violence_history",
        "human_trafficking_history",
        "drug_court",
        "warrants_unpaid",
        "mh_exam_completed",
        "med_exam_completed",
        "car_at_entry",
        "car_insurance_at_entry",
    ]

    for field_name in yes_no_fields:
        value = data[field_name]
        if value not in {None, "yes", "no"}:
            errors.append(f"{field_name.replace('_', ' ').title()} must be Yes or No.")

    if data["car_insurance_at_entry"] == "yes" and data["car_at_entry"] != "yes":
        errors.append("Car Insurance at Entry cannot be Yes unless Car at Entry is Yes.")

    return data, errors


def _find_active_enrollment_id(resident_id: int, shelter: str) -> int | None:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND {shelter_equals_sql("shelter")}
          AND exit_date IS NULL
        ORDER BY entry_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )

    if not row:
        return None

    return int(row["id"] if isinstance(row, dict) else row[0])


def _upsert_assessment_for_enrollment(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    existing = db_fetchone(
        f"""
        SELECT id
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if existing:
        db_execute(
            f"""
            UPDATE intake_assessments
            SET ace_score = {ph},
                grit_score = {ph},
                sexual_survivor = {ph},
                dv_survivor = {ph},
                human_trafficking_survivor = {ph},
                drug_court = {ph},
                warrants_unpaid = {ph},
                mh_exam_completed = {ph},
                med_exam_completed = {ph},
                car_at_entry = {ph},
                car_insurance_at_entry = {ph},
                updated_at = {ph}
            WHERE enrollment_id = {ph}
            """,
            (
                data["ace_score"],
                data["grit_score"],
                yes_no_to_int(data["sexual_survivor"]),
                yes_no_to_int(data["domestic_violence_history"]),
                yes_no_to_int(data["human_trafficking_history"]),
                yes_no_to_int(data["drug_court"]),
                yes_no_to_int(data["warrants_unpaid"]),
                yes_no_to_int(data["mh_exam_completed"]),
                yes_no_to_int(data["med_exam_completed"]),
                yes_no_to_int(data["car_at_entry"]),
                yes_no_to_int(data["car_insurance_at_entry"]),
                now,
                enrollment_id,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO intake_assessments
        (
            enrollment_id,
            ace_score,
            grit_score,
            sexual_survivor,
            dv_survivor,
            human_trafficking_survivor,
            drug_court,
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
            {ph},
            {ph},
            {ph},
            {ph},
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
            enrollment_id,
            data["ace_score"],
            data["grit_score"],
            yes_no_to_int(data["sexual_survivor"]),
            yes_no_to_int(data["domestic_violence_history"]),
            yes_no_to_int(data["human_trafficking_history"]),
            yes_no_to_int(data["drug_court"]),
            yes_no_to_int(data["warrants_unpaid"]),
            yes_no_to_int(data["mh_exam_completed"]),
            yes_no_to_int(data["med_exam_completed"]),
            yes_no_to_int(data["car_at_entry"]),
            yes_no_to_int(data["car_insurance_at_entry"]),
            now,
            now,
        ),
    )


# ============================================================================
# Views
# ----------------------------------------------------------------------------
# These are called by thin wrappers in routes/case_management.py.
# ============================================================================

def assessment_form_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    draft_id = parse_int(request.args.get("draft_id"))
    form_data: dict[str, Any] = {}

    if draft_id is not None:
        loaded = _load_assessment_draft(shelter, draft_id)
        if not loaded:
            flash("Assessment draft not found.", "error")
            return redirect(url_for("case_management.intake_index"))
        form_data = loaded

    residents = db_fetchall(
        f"""
        SELECT id, first_name, last_name
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    return render_template(
        "case_management/assessment.html",
        shelter=shelter,
        residents=residents,
        form_data=form_data,
    )


def submit_assessment_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "complete").strip().lower()
    draft_id = parse_int(request.form.get("draft_id"))

    residents = db_fetchall(
        f"""
        SELECT id, first_name, last_name
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    form_data, errors = _validate_assessment_form(request.form)
    form_data["draft_id"] = request.form.get("draft_id", "")
    resident_id = form_data["resident_id"]

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/assessment.html",
            shelter=shelter,
            residents=residents,
            form_data={
                "draft_id": request.form.get("draft_id", ""),
                "resident_id": request.form.get("resident_id", ""),
                "ace_score": request.form.get("ace_score", ""),
                "grit_score": request.form.get("grit_score", ""),
                "sexual_survivor": request.form.get("sexual_survivor", ""),
                "domestic_violence_history": request.form.get("domestic_violence_history", ""),
                "human_trafficking_history": request.form.get("human_trafficking_history", ""),
                "drug_court": request.form.get("drug_court", ""),
                "warrants_unpaid": request.form.get("warrants_unpaid", ""),
                "mh_exam_completed": request.form.get("mh_exam_completed", ""),
                "med_exam_completed": request.form.get("med_exam_completed", ""),
                "car_at_entry": request.form.get("car_at_entry", ""),
                "car_insurance_at_entry": request.form.get("car_insurance_at_entry", ""),
            },
        )

    form_data_for_template = {
        "draft_id": request.form.get("draft_id", ""),
        "resident_id": request.form.get("resident_id", ""),
        "ace_score": request.form.get("ace_score", ""),
        "grit_score": request.form.get("grit_score", ""),
        "sexual_survivor": request.form.get("sexual_survivor", ""),
        "domestic_violence_history": request.form.get("domestic_violence_history", ""),
        "human_trafficking_history": request.form.get("human_trafficking_history", ""),
        "drug_court": request.form.get("drug_court", ""),
        "warrants_unpaid": request.form.get("warrants_unpaid", ""),
        "mh_exam_completed": request.form.get("mh_exam_completed", ""),
        "med_exam_completed": request.form.get("med_exam_completed", ""),
        "car_at_entry": request.form.get("car_at_entry", ""),
        "car_insurance_at_entry": request.form.get("car_insurance_at_entry", ""),
    }

    if action == "save_draft":
        saved_draft_id = _save_assessment_draft(
            current_shelter=shelter,
            form_data=form_data_for_template,
            resident_id=resident_id,
            draft_id=draft_id,
        )
        flash("Assessment draft saved.", "success")
        return redirect(url_for("case_management.assessment_form", draft_id=saved_draft_id))

    enrollment_id = _find_active_enrollment_id(resident_id, shelter)
    if enrollment_id is None:
        flash("This resident does not have an active enrollment. Assessment cannot be finalized.", "error")
        return render_template(
            "case_management/assessment.html",
            shelter=shelter,
            residents=residents,
            form_data=form_data_for_template,
        )

    _upsert_assessment_for_enrollment(enrollment_id, form_data)

    if draft_id is not None:
        _complete_assessment_draft(draft_id)

    flash("Assessment finalized successfully.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
