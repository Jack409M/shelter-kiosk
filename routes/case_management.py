# [FULL FILE REWRITE STARTS HERE]

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


# =========================
# CASE MANAGEMENT INDEX
# =========================

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


# =========================
# INTAKE LANDING PAGE
# =========================

@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_index():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    placeholder = _placeholder()

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
        "intake_assessment/index.html",
        drafts=drafts,
        shelter=shelter,
    )


# =========================
# INTAKE FORM
# =========================

@case_management.get("/intake-assessment/new")
@require_login
@require_shelter
def intake_form():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = _normalize_shelter_name(session.get("shelter"))
    draft_id = _parse_int(request.args.get("draft_id"))

    form_data = None

    if draft_id:
        form_data = _load_intake_draft(current_shelter, draft_id)
        if not form_data:
            flash("Draft not found.", "error")
            return redirect(url_for("case_management.intake_index"))

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
        ),
    )


@case_management.post("/intake-assessment/new")
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
        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=request.form,
            draft_id=draft_id,
        )
        flash("Draft saved.", "success")
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
            ),
        )

    resident_id, resident_identifier, resident_code = _insert_resident(data, current_shelter)
    enrollment_id = _insert_program_enrollment(resident_id, data, current_shelter)
    _insert_intake_assessment(enrollment_id, data)
    _insert_family_snapshot(enrollment_id, data)

    if draft_id:
        _complete_intake_draft(draft_id)

    flash("Resident created successfully.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


# =========================
# EXISTING RESIDENT CASE
# =========================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    placeholder = _placeholder()

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {placeholder}
          AND {_shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
    )

# [FULL FILE REWRITE ENDS HERE]
