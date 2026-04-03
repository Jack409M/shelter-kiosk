from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_fetchall
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import shelter_equals_sql


def index_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    show = (request.args.get("show") or "active").strip().lower()
    if show not in {"active", "all"}:
        show = "active"

    if show == "all":
        residents = db_fetchall(
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
    else:
        residents = db_fetchall(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                resident_code,
                is_active
            FROM residents
            WHERE {shelter_equals_sql("shelter")}
              AND is_active = 1
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    return render_template(
        "case_management/index.html",
        residents=residents,
        shelter=shelter,
        show=show,
    )


def intake_index_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = "?" if "sqlite" else None  # placeholder variable not needed, kept out intentionally

    drafts = db_fetchall(
        """
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = ?
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """
        if False else
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {('?' if shelter is not None else '?')}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    duplicate_review_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {('?' if shelter is not None else '?')}
          AND status = 'pending_duplicate_review'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    assessment_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            updated_at
        FROM assessment_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {('?' if shelter is not None else '?')}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    residents = db_fetchall(
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

    return render_template(
        "intake_assessment/index.html",
        drafts=drafts,
        duplicate_review_drafts=duplicate_review_drafts,
        assessment_drafts=assessment_drafts,
        shelter=shelter,
        residents=residents,
    )
