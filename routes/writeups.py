from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


writeups = Blueprint(
    "writeups",
    __name__,
    url_prefix="/staff/writeups",
)


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
VALID_DISCIPLINARY_OUTCOMES = [
    "none",
    "program_probation",
    "pre_termination",
]


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


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


def _insert_resident_notification(
    *,
    resident_id: int,
    shelter: str,
    notification_type: str,
    title: str,
    message: str,
) -> None:
    db_execute(
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s)
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            None,
            utcnow_iso(),
            None,
        ),
    )


@writeups.route("/resident/<int:resident_id>", methods=["GET", "POST"])
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

        disciplinary_outcome = (request.form.get("disciplinary_outcome") or "none").strip().lower()
        probation_start_date = (request.form.get("probation_start_date") or "").strip() or None
        probation_end_date = (request.form.get("probation_end_date") or "").strip() or None
        pre_termination_date = (request.form.get("pre_termination_date") or "").strip() or None
        blocks_passes_raw = (request.form.get("blocks_passes") or "").strip().lower()

        if category not in VALID_WRITEUP_CATEGORIES:
            category = "Other"
        if severity not in VALID_WRITEUP_SEVERITIES:
            severity = "Low"
        if status not in VALID_WRITEUP_STATUSES:
            status = "Open"
        if disciplinary_outcome not in VALID_DISCIPLINARY_OUTCOMES:
            disciplinary_outcome = "none"

        blocks_passes = blocks_passes_raw in {"1", "true", "yes", "on"}

        errors: list[str] = []

        if not incident_date or not summary:
            errors.append("Incident date and summary are required.")

        if disciplinary_outcome == "program_probation":
            if not probation_start_date or not probation_end_date:
                errors.append("Program Probation requires a begin date and end date.")
            if pre_termination_date:
                errors.append("Pre Termination date should not be set when Program Probation is selected.")
            blocks_passes = True

        if disciplinary_outcome == "pre_termination":
            if not pre_termination_date:
                errors.append("Pre Termination requires a scheduled date.")
            if probation_start_date or probation_end_date:
                errors.append("Probation dates should not be set when Pre Termination is selected.")
            blocks_passes = True

        if disciplinary_outcome == "none":
            probation_start_date = None
            probation_end_date = None
            pre_termination_date = None

        if status in {"Resolved", "Dismissed"}:
            blocks_passes = False

        if errors:
            for err in errors:
                flash(err, "error")
            return redirect(url_for("writeups.resident_writeups", resident_id=resident_id))

        now = utcnow_iso()
        resolved_at = now if status in {"Resolved", "Dismissed"} else None

        db_execute(
            (
                """
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                if g.get("db_kind") == "pg"
                else
                """
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
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
                1 if blocks_passes else 0,
                session.get("staff_user_id"),
                session.get("staff_user_id"),
                now,
                now,
            ),
        )

        if disciplinary_outcome == "pre_termination" and pre_termination_date and status == "Open":
            _insert_resident_notification(
                resident_id=resident_id,
                shelter=shelter,
                notification_type="pre_termination_scheduled",
                title="Pre Termination Scheduled",
                message=f"You are scheduled for Pre Termination on {pre_termination_date}. Please contact staff immediately.",
            )

        if disciplinary_outcome == "program_probation" and probation_start_date and probation_end_date and status == "Open":
            _insert_resident_notification(
                resident_id=resident_id,
                shelter=shelter,
                notification_type="program_probation_assigned",
                title="Program Probation Assigned",
                message=f"You are on Program Probation from {probation_start_date} through {probation_end_date}. Passes are denied during this period.",
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
        disciplinary_outcomes=VALID_DISCIPLINARY_OUTCOMES,
    )
