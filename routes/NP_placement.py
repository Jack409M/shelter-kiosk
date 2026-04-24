from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from core.NP_placement_service import get_active_placement
from routes.resident_parts.resident_transfer_helpers import upsert_resident_housing_assignment

bp = Blueprint("NP_placement", __name__, url_prefix="/staff/placement")


def _current_shelter() -> str:
    return (session.get("shelter") or "").strip().lower()


def _can_manage_placement() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _load_resident(resident_id: int):
    shelter = _current_shelter()
    return db_fetchone(
        """
        SELECT id, first_name, last_name, program_level, shelter, is_active
        FROM residents
        WHERE id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
          AND is_active = TRUE
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _load_units_for_shelter(shelter: str):
    return db_fetchall(
        """
        SELECT id, unit_label, unit_type, bedroom_count, max_occupancy
        FROM housing_units
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND is_active = TRUE
        ORDER BY unit_label
        """,
        (shelter,),
    )


@bp.route("/dashboard")
@require_login
@require_shelter
def dashboard():
    if not _can_manage_placement():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _current_shelter()

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

    units = _load_units_for_shelter(shelter)

    return render_template(
        "NP_placement_dashboard.html",
        shelter=shelter,
        residents=residents,
        placements=placements,
        units=units,
    )


@bp.route("/resident/<int:resident_id>/change", methods=["GET", "POST"])
@require_login
@require_shelter
def change_placement(resident_id: int):
    if not _can_manage_placement():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _current_shelter()
    resident = _load_resident(resident_id)
    if not resident:
        flash("Resident not found in the current shelter.", "error")
        return redirect(url_for("NP_placement.dashboard"))

    units = _load_units_for_shelter(shelter)
    active_placement = get_active_placement(resident_id=resident_id, shelter=shelter)

    if request.method == "POST":
        unit_label = (request.form.get("unit_label") or "").strip() or None
        valid_unit_labels = {str(unit.get("unit_label") or "").strip() for unit in units}
        if unit_label and unit_label not in valid_unit_labels:
            flash("Select a valid active unit for this shelter.", "error")
            return redirect(url_for("NP_placement.change_placement", resident_id=resident_id))

        upsert_resident_housing_assignment(
            resident_id=resident_id,
            destination_shelter=shelter,
            apartment_number=unit_label,
        )
        flash("Placement unit updated.", "success")
        return redirect(url_for("NP_placement.dashboard"))

    return render_template(
        "NP_change_placement.html",
        shelter=shelter,
        resident=resident,
        units=units,
        active_placement=active_placement,
    )
