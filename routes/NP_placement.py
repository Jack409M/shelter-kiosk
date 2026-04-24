from __future__ import annotations

from flask import Blueprint, render_template, session

from core.db import db_fetchall

bp = Blueprint("NP_placement", __name__, url_prefix="/staff/placement")


@bp.route("/dashboard")
def dashboard():
    shelter = (session.get("shelter") or "").lower()

    residents = db_fetchall(
        """
        SELECT r.id, r.first_name, r.last_name, r.program_level
        FROM residents r
        WHERE LOWER(COALESCE(r.shelter, '')) = %s
        AND r.is_active = TRUE
        ORDER BY r.last_name, r.first_name
        """,
        (shelter,),
    )

    placements = db_fetchall(
        """
        SELECT p.resident_id, p.housing_unit_id, p.program_level
        FROM resident_placements p
        WHERE LOWER(COALESCE(p.shelter, '')) = %s
        AND COALESCE(p.end_date, '') = ''
        """,
        (shelter,),
    )

    units = db_fetchall(
        """
        SELECT id, unit_label, unit_type
        FROM housing_units
        WHERE LOWER(COALESCE(shelter, '')) = %s
        AND is_active = TRUE
        ORDER BY unit_label
        """,
        (shelter,),
    )

    return render_template(
        "NP_placement_dashboard.html",
        residents=residents,
        placements=placements,
        units=units,
    )
