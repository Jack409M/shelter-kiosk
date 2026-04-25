from __future__ import annotations

# Standard library
# Third party
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

# Core / app
from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

bp = Blueprint("writeups", __name__, url_prefix="/writeups")

VALID_WRITEUP_STATUSES = ["Open", "Resolved", "Dismissed"]
VALID_WRITEUP_CATEGORIES = [
    "Rules Violation",
    "Behavioral Concern",
    "Safety Concern",
    "Conflict",
    "Room Issue",
    "Program Non Compliance",
    "Other",
]
VALID_WRITEUP_SEVERITIES = ["Low", "Moderate", "High"]


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _resident_context(resident_id: int, shelter: str):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


@bp.route("/")
@require_login
@require_shelter
def writeups_list():
    rows = db_fetchall(
        """
        SELECT *
        FROM writeups
        ORDER BY created_at DESC
        """
    )
    return render_template("writeups/list.html", rows=rows)


@bp.route("/create", methods=["GET", "POST"])
@require_login
@require_shelter
def writeups_create():
    if request.method == "POST":
        resident_id = request.form.get("resident_id")
        notes = request.form.get("notes")
        staff_user_id = g.user["id"]

        db_execute(
            """
            INSERT INTO writeups (
                resident_id,
                notes,
                created_at,
                created_by
            )
            VALUES (?, ?, ?, ?)
            """,
            (resident_id, notes, utcnow_iso(), staff_user_id),
        )

        log_action(
            "writeup",
            None,
            session.get("shelter"),
            staff_user_id,
            "create",
            details={
                "resident_id": resident_id,
                "source": "writeups_create",
            },
        )

        flash("Write-up created", "success")
        return redirect(url_for("writeups.writeups_list"))

    return render_template("writeups/create.html")


@bp.route("/<int:writeup_id>")
@require_login
@require_shelter
def writeups_detail(writeup_id: int):
    row = db_fetchone(
        """
        SELECT *
        FROM writeups
        WHERE id = ?
        """,
        (writeup_id,),
    )

    if not row:
        flash("Write-up not found", "warning")
        return redirect(url_for("writeups.writeups_list"))

    return render_template("writeups/detail.html", row=row)


@bp.route("/resident/<int:resident_id>", methods=["GET", "POST"])
@require_login
@require_shelter
def resident_writeups(resident_id: int):
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = _resident_context(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if request.method == "POST":
        incident_date = (request.form.get("incident_date") or "").strip()
        category = (request.form.get("category") or "Other").strip()
        severity = (request.form.get("severity") or "Low").strip()
        summary = (request.form.get("summary") or "").strip()
        full_notes = (request.form.get("full_notes") or "").strip() or None
        action_taken = (request.form.get("action_taken") or "").strip() or None
        status = (request.form.get("status") or "Open").strip()
        resolution_notes = (request.form.get("resolution_notes") or "").strip() or None
        disciplinary_outcome = (request.form.get("disciplinary_outcome") or "none").strip()
        probation_start_date = (request.form.get("probation_start_date") or "").strip() or None
        probation_end_date = (request.form.get("probation_end_date") or "").strip() or None
        pre_termination_date = (request.form.get("pre_termination_date") or "").strip() or None
        blocks_passes = (request.form.get("blocks_passes") or "").strip() == "1"

        if category not in VALID_WRITEUP_CATEGORIES:
            category = "Other"
        if severity not in VALID_WRITEUP_SEVERITIES:
            severity = "Low"
        if status not in VALID_WRITEUP_STATUSES:
            status = "Open"
        if disciplinary_outcome not in {"none", "program_probation", "pre_termination"}:
            disciplinary_outcome = "none"

        if not incident_date or not summary:
            flash("Incident date and summary are required.", "error")
            return redirect(url_for("writeups.resident_writeups", resident_id=resident_id))

        if disciplinary_outcome == "program_probation":
            if not probation_start_date or not probation_end_date:
                flash("Program Probation requires a begin date and end date.", "error")
                return redirect(url_for("writeups.resident_writeups", resident_id=resident_id))
            pre_termination_date = None
        elif disciplinary_outcome == "pre_termination":
            if not pre_termination_date:
                flash("Pre Termination requires a scheduled date.", "error")
                return redirect(url_for("writeups.resident_writeups", resident_id=resident_id))
            probation_start_date = None
            probation_end_date = None
        else:
            probation_start_date = None
            probation_end_date = None
            pre_termination_date = None
            blocks_passes = False

        now = utcnow_iso()
        resolved_at = now if status in {"Resolved", "Dismissed"} else None
        ph = _placeholder()
        staff_user_id = session.get("staff_user_id")

        db_execute(
            f"""
            INSERT INTO resident_writeups (
                resident_id,
                shelter_snapshot,
                incident_date,
                category,
                severity,
                summary,
                full_notes,
                action_taken,
                status,
                resolution_notes,
                resolved_at,
                disciplinary_outcome,
                probation_start_date,
                probation_end_date,
                pre_termination_date,
                blocks_passes,
                created_by_staff_user_id,
                updated_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (
                {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
            )
            """,
            (
                resident_id,
                shelter,
                incident_date,
                category,
                severity,
                summary,
                full_notes,
                action_taken,
                status,
                resolution_notes,
                resolved_at,
                disciplinary_outcome,
                probation_start_date,
                probation_end_date,
                pre_termination_date,
                blocks_passes,
                staff_user_id,
                staff_user_id,
                now,
                now,
            ),
        )

        log_action(
            "resident_writeup",
            resident_id,
            shelter,
            staff_user_id,
            "create",
            details={
                "blocks_passes": blocks_passes,
                "category": category,
                "disciplinary_outcome": disciplinary_outcome,
                "incident_date": incident_date,
                "severity": severity,
                "status": status,
            },
        )

        flash("Write up saved.", "ok")
        return redirect(url_for("writeups.resident_writeups", resident_id=resident_id))

    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT *
        FROM resident_writeups
        WHERE resident_id = {ph}
        ORDER BY incident_date DESC, id DESC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/writeups.html",
        resident=resident,
        rows=rows,
        statuses=VALID_WRITEUP_STATUSES,
        categories=VALID_WRITEUP_CATEGORIES,
        severities=VALID_WRITEUP_SEVERITIES,
    )
