from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchall
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


@case_management.get("")
@require_login
@require_shelter
def index():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    query = (request.args.get("q") or "").strip()
    placeholder = _placeholder()

    if query:
        like_value = f"%{query.lower()}%"
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
              AND (
                LOWER(COALESCE(first_name, '')) LIKE {placeholder}
                OR LOWER(COALESCE(last_name, '')) LIKE {placeholder}
                OR LOWER(COALESCE(resident_code, '')) LIKE {placeholder}
              )
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter, like_value, like_value, like_value),
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
            WHERE {_shelter_equals_sql("shelter")}
            ORDER BY last_name ASC, first_name ASC
            LIMIT 25
            """,
            (shelter,),
        )

    return render_template(
        "case_management/index.html",
        residents=residents,
        query=query,
        shelter=shelter,
    )
