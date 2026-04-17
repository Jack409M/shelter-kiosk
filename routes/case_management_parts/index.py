from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.db import db_fetchall
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    shelter_equals_sql,
)


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


def _load_resident_rows_for_index(shelter: str, show: str):
    if show == "all":
        return db_fetchall(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                resident_code,
                is_active
            FROM residents
            WHERE {shelter_equals_sql("shelter")}
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    active_sql = _active_sql_literal()
    return db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            is_active
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
          AND is_active = {active_sql}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def _build_index_residents(shelter: str, show: str) -> list[dict]:
    resident_rows = _load_resident_rows_for_index(shelter, show)
    return [dict(row) for row in resident_rows]


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
