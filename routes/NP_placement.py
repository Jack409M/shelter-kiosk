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


def _unit_sort_key(unit) -> tuple[int, int | str]:
    label = str(unit.get("unit_label") or "").strip()
    if label.isdigit():
        return (0, int(label))
    return (1, label.lower())


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


def _active_housing_unit_ids_for_shelter(shelter: str, *, exclude_resident_id: int | None = None) -> set[int]:
    params: tuple[object, ...]
    exclude_clause = ""

    if exclude_resident_id is not None:
        exclude_clause = "AND resident_id <> %s"
        params = (shelter, exclude_resident_id)
    else:
        params = (shelter,)

    rows = db_fetchall(
        f"""
        SELECT housing_unit_id
        FROM resident_placements
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND COALESCE(end_date, '') = ''
          AND housing_unit_id IS NOT NULL
          {exclude_clause}
        """,
        params,
    )

    occupied: set[int] = set()
    for row in rows or []:
        unit_id = row.get("housing_unit_id")
        if isinstance(unit_id, int):
            occupied.add(unit_id)
    return occupied


def _active_haven_dorm_assignment_count() -> int:
    row = db_fetchone(
        """
        SELECT COUNT(*) AS assigned_count
        FROM resident_placements
        WHERE LOWER(COALESCE(shelter, '')) = 'haven'
          AND COALESCE(end_date, '') = ''
        """
    )
    count = row.get("assigned_count") if row else 0
    return count if isinstance(count, int) else 0


def _load_units_for_shelter(shelter: str):
    rows = db_fetchall(
        """
        SELECT id, unit_label, unit_type, bedroom_count, max_occupancy
        FROM housing_units
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND is_active = TRUE
        """,
        (shelter,),
    )
    return sorted(rows or [], key=_unit_sort_key)


def _load_available_units_for_shelter(shelter: str, *, resident_id: int):
    if shelter == "haven":
        return _load_units_for_shelter(shelter)

    occupied_unit_ids = _active_housing_unit_ids_for_shelter(
        shelter,
        exclude_resident_id=resident_id,
    )
    return [
        unit
        for unit in _load_units_for_shelter(shelter)
        if unit.get("id") not in occupied_unit_ids
    ]


def _load_dashboard_rows(shelter: str):
    return db_fetchall(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.program_level AS resident_level,
            p.program_level AS placement_level,
            p.housing_unit_id,
            u.unit_label,
            CASE
                WHEN COALESCE(p.program_level, r.program_level, '') = '9' THEN 4
                WHEN p.id IS NULL THEN 1
                WHEN p.housing_unit_id IS NULL THEN 2
                ELSE 3
            END AS status_order
        FROM residents r
        LEFT JOIN resident_placements p
          ON p.resident_id = r.id
         AND LOWER(COALESCE(p.shelter, '')) = %s
         AND COALESCE(p.end_date, '') = ''
        LEFT JOIN housing_units u
          ON u.id = p.housing_unit_id
        WHERE LOWER(COALESCE(r.shelter, '')) = %s
          AND r.is_active = TRUE
        ORDER BY status_order, r.last_name, r.first_name
        """,
        (shelter, shelter),
    )


@bp.route("/dashboard")
@require_login
@require_shelter
def dashboard():
    if not _can_manage_placement():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _current_shelter()
    rows = _load_dashboard_rows(shelter)

    return render_template(
        "NP_placement_dashboard.html",
        shelter=shelter,
        rows=rows,
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

    units = _load_available_units_for_shelter(shelter, resident_id=resident_id)
    active_placement = get_active_placement(resident_id=resident_id, shelter=shelter)
    haven_dorm_assignment_count = _active_haven_dorm_assignment_count() if shelter == "haven" else None

    if request.method == "POST":
        unit_label = (request.form.get("unit_label") or "").strip() or None
        valid_unit_labels = {str(unit.get("unit_label") or "").strip() for unit in units}
        if unit_label and unit_label not in valid_unit_labels:
            flash("Select a valid available unit for this shelter.", "error")
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
        haven_dorm_assignment_count=haven_dorm_assignment_count,
    )
