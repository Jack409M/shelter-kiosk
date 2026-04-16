from __future__ import annotations

from datetime import datetime

from flask import current_app, flash, g, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.runtime import init_db
from db.schema_people import ensure_resident_child_income_supports_table
from routes.case_management_parts.family_validation import (
    validate_child_form,
    validate_child_service_form,
)
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    fetch_current_enrollment_for_resident,
    normalize_shelter_name,
    placeholder,
    shelter_equals_sql,
)
from routes.case_management_parts.income_state_sync import recalculate_and_sync_income_state_atomic


def _resident_case_redirect(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _quick_add_requested() -> bool:
    return (request.form.get("redirect_to") or "").strip().lower() == "resident_case"


def _child_services_redirect(child_id: int):
    return redirect(url_for("case_management.child_services", child_id=child_id))


def _post_child_service_redirect(child_id: int, resident_id: int):
    if _quick_add_requested():
        return _resident_case_redirect(resident_id)
    return _child_services_redirect(child_id)


def _ensure_family_income_support_schema() -> None:
    ensure_resident_child_income_supports_table(g.get("db_kind"))


def _resident_in_scope(resident_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter
        FROM residents r
        WHERE r.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _latest_enrollment_for_resident(resident_id: int, shelter: str):
    return fetch_current_enrollment_for_resident(
        resident_id,
        shelter=shelter,
        columns="id",
    )


def _recalculate_current_enrollment_income_support(resident_id: int) -> None:
    shelter = _current_shelter()
    enrollment = _latest_enrollment_for_resident(resident_id, shelter)
    if not enrollment:
        return
    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    recalculate_and_sync_income_state_atomic(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
    )

# rest of file unchanged
