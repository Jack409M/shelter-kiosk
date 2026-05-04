from __future__ import annotations

from flask import Blueprint, abort, render_template, request, session

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone

ra_resident_contacts = Blueprint(
    "ra_resident_contacts",
    __name__,
    url_prefix="/staff/ra/residents",
)

RA_CONTACT_VIEW_ROLES = {"admin", "shelter_director", "case_manager", "ra"}


def _clean_role() -> str:
    return str(session.get("role") or "").strip().lower()


def _can_view_contacts() -> bool:
    return _clean_role() in RA_CONTACT_VIEW_ROLES


def _current_shelter() -> str:
    return str(session.get("shelter") or "").strip().lower()


@ra_resident_contacts.get("")
@require_login
@require_shelter
def contact_list():
    if not _can_view_contacts():
        abort(403)

    shelter = _current_shelter()
    query = str(request.args.get("q") or "").strip()

    params: list[object] = [shelter]
    where_clause = "LOWER(COALESCE(shelter, '')) = %s AND is_active = TRUE"

    if query:
        params.extend([f"%{query.lower()}%", f"%{query.lower()}%"])
        where_clause += " AND (LOWER(COALESCE(first_name, '')) LIKE %s OR LOWER(COALESCE(last_name, '')) LIKE %s)"

    residents = db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone
        FROM residents
        WHERE {where_clause}
        ORDER BY last_name ASC, first_name ASC
        """,
        tuple(params),
    )

    return render_template(
        "ra_resident_contacts.html",
        residents=residents,
        query=query,
    )


@ra_resident_contacts.get("/<int:resident_id>")
@require_login
@require_shelter
def contact_detail(resident_id: int):
    if not _can_view_contacts():
        abort(403)

    resident = db_fetchone(
        """
        SELECT
            id,
            first_name,
            last_name,
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone
        FROM residents
        WHERE id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
          AND is_active = TRUE
        LIMIT 1
        """,
        (resident_id, _current_shelter()),
    )

    if not resident:
        abort(404)

    return render_template("ra_resident_contact_detail.html", resident=resident)
