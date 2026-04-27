from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.db import db_fetchall
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    shelter_equals_sql,
)

CRITICAL_INTEGRITY_CODES = {"ENR", "BED", "RENT", "INTAKE"}


def _require_case_manager_access():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))
    return None


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _current_show_mode() -> str:
    show = (request.args.get("show") or "active").strip().lower()
    if show not in {"active", "all"}:
        return "active"
    return show


def _active_sql_literal() -> str:
    return "TRUE" if g.get("db_kind") == "pg" else "1"


def _db_placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _has_text(value: object) -> bool:
    return bool(str(value or "").strip())


def _float_value(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _compute_resident_file_integrity(row: dict) -> dict:
    missing: list[str] = []
    shelter = str(row.get("shelter") or "").strip().lower()

    if not _has_text(row.get("first_name")) or not _has_text(row.get("last_name")) or not row.get(
        "birth_year"
    ):
        missing.append("ID")

    if not row.get("enrollment_id"):
        missing.append("ENR")

    if not _has_text(row.get("shelter")) and not _has_text(row.get("enrollment_shelter")):
        missing.append("SH")

    if not row.get("placement_id") or not row.get("housing_unit_id"):
        missing.append("BED")

    if not _has_text(row.get("program_level")):
        missing.append("LVL")

    if not row.get("intake_assessment_id"):
        missing.append("INTAKE")

    rent_config_missing = not row.get("rent_config_id")
    rent_level_missing = not _has_text(row.get("rent_level_snapshot"))
    rent_unit_missing = shelter in {"abba", "gratitude"} and not _has_text(
        row.get("rent_apartment_number_snapshot")
    )
    rent_resolution_missing = (
        not _truthy(row.get("rent_is_exempt"))
        and _float_value(row.get("rent_monthly_rent")) <= 0
        and not _has_text(row.get("rent_apartment_size_snapshot"))
    )

    if rent_config_missing or rent_level_missing or rent_unit_missing or rent_resolution_missing:
        missing.append("RENT")

    if not missing:
        status = "OK"
    elif any(code in CRITICAL_INTEGRITY_CODES for code in missing):
        status = "BROKEN"
    else:
        status = "WARNING"

    return {
        "status": status,
        "missing": missing,
    }


def _active_enrollment_id_sql() -> str:
    return """
        SELECT pe.id
        FROM program_enrollments pe
        WHERE pe.resident_id = r.id
          AND LOWER(COALESCE(pe.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
          AND LOWER(COALESCE(pe.program_status, '')) = 'active'
          AND COALESCE(pe.exit_date, '') = ''
        ORDER BY pe.entry_date DESC, pe.id DESC
        LIMIT 1
    """


def _load_resident_rows_for_index(shelter: str, show: str):
    active_enrollment_id_sql = _active_enrollment_id_sql()
    active_filter = ""
    if show != "all":
        active_filter = f"AND r.is_active = {_active_sql_literal()}"

    return db_fetchall(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.resident_code,
            r.birth_year,
            r.shelter,
            r.program_level,
            r.is_active,
            ({active_enrollment_id_sql}) AS enrollment_id,
            (
                SELECT pe.shelter
                FROM program_enrollments pe
                WHERE pe.id = ({active_enrollment_id_sql})
                LIMIT 1
            ) AS enrollment_shelter,
            (
                SELECT ia.id
                FROM intake_assessments ia
                WHERE ia.enrollment_id = ({active_enrollment_id_sql})
                ORDER BY ia.id DESC
                LIMIT 1
            ) AS intake_assessment_id,
            (
                SELECT rp.id
                FROM resident_placements rp
                WHERE rp.resident_id = r.id
                  AND LOWER(COALESCE(rp.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rp.end_date, '') = ''
                ORDER BY rp.start_date DESC, rp.id DESC
                LIMIT 1
            ) AS placement_id,
            (
                SELECT rp.housing_unit_id
                FROM resident_placements rp
                WHERE rp.resident_id = r.id
                  AND LOWER(COALESCE(rp.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rp.end_date, '') = ''
                ORDER BY rp.start_date DESC, rp.id DESC
                LIMIT 1
            ) AS housing_unit_id,
            (
                SELECT hu.unit_label
                FROM resident_placements rp
                JOIN housing_units hu ON hu.id = rp.housing_unit_id
                WHERE rp.resident_id = r.id
                  AND LOWER(COALESCE(rp.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rp.end_date, '') = ''
                ORDER BY rp.start_date DESC, rp.id DESC
                LIMIT 1
            ) AS housing_unit_label,
            (
                SELECT rc.id
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_config_id,
            (
                SELECT rc.level_snapshot
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_level_snapshot,
            (
                SELECT rc.apartment_number_snapshot
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_apartment_number_snapshot,
            (
                SELECT rc.apartment_size_snapshot
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_apartment_size_snapshot,
            (
                SELECT rc.monthly_rent
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_monthly_rent,
            (
                SELECT rc.is_exempt
                FROM resident_rent_configs rc
                WHERE rc.resident_id = r.id
                  AND LOWER(COALESCE(rc.shelter, '')) = LOWER(COALESCE(r.shelter, ''))
                  AND COALESCE(rc.effective_end_date, '') = ''
                ORDER BY rc.effective_start_date DESC, rc.id DESC
                LIMIT 1
            ) AS rent_is_exempt
        FROM residents r
        WHERE {shelter_equals_sql("r.shelter")}
          {active_filter}
        ORDER BY r.is_active DESC, r.last_name ASC, r.first_name ASC
        """,
        (shelter,),
    )


def _build_index_residents(shelter: str, show: str) -> list[dict]:
    resident_rows = _load_resident_rows_for_index(shelter, show)
    residents = [dict(row) for row in resident_rows]
    for resident in residents:
        resident["file_integrity"] = _compute_resident_file_integrity(resident)
    return residents


def _load_intake_drafts(shelter: str):
    shelter_param = _db_placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )


def _load_duplicate_review_drafts(shelter: str):
    shelter_param = _db_placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'pending_duplicate_review'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )


def _load_assessment_drafts(shelter: str):
    shelter_param = _db_placeholder()
    return db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            updated_at
        FROM assessment_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )


def _load_residents_for_intake(shelter: str):
    return db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def index_view():
    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    init_db()

    shelter = _current_shelter()
    show = _current_show_mode()
    residents = _build_index_residents(shelter, show)

    return render_template(
        "case_management/index.html",
        residents=residents,
        shelter=shelter,
        show=show,
    )


def intake_index_view():
    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    init_db()

    shelter = _current_shelter()

    drafts = _load_intake_drafts(shelter)
    duplicate_review_drafts = _load_duplicate_review_drafts(shelter)
    assessment_drafts = _load_assessment_drafts(shelter)
    residents = _load_residents_for_intake(shelter)

    return render_template(
        "intake_assessment/index.html",
        drafts=drafts,
        duplicate_review_drafts=duplicate_review_drafts,
        assessment_drafts=assessment_drafts,
        shelter=shelter,
        residents=residents,
    )
