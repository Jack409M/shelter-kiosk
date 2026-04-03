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


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _ensure_tables() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_writeups (
                id SERIAL PRIMARY KEY,
                resident_id INTEGER NOT NULL REFERENCES residents(id),
                shelter_snapshot TEXT NOT NULL,
                incident_date TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'Low',
                summary TEXT NOT NULL,
                full_notes TEXT,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                resolution_notes TEXT,
                resolved_at TEXT,
                created_by_staff_user_id INTEGER,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_writeups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_id INTEGER NOT NULL,
                shelter_snapshot TEXT NOT NULL,
                incident_date TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'Low',
                summary TEXT NOT NULL,
                full_notes TEXT,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'Open',
                resolution_notes TEXT,
                resolved_at TEXT,
                created_by_staff_user_id INTEGER,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (resident_id) REFERENCES residents(id)
            )
            """
        )


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


@writeups.route("/resident/<int:resident_id>", methods=["GET", "POST"])
@require_login
@require_shelter
def resident_writeups(resident_id: int):
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    _ensure_tables()

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

        if category not in VALID_WRITEUP_CATEGORIES:
            category = "Other"
        if severity not in VALID_WRITEUP_SEVERITIES:
            severity = "Low"
        if status not in VALID_WRITEUP_STATUSES:
            status = "Open"

        if not incident_date or not summary:
            flash("Incident date and summary are required.", "error")
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
                    created_by_staff_user_id,
                    updated_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    created_by_staff_user_id,
                    updated_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                session.get("staff_user_id"),
                session.get("staff_user_id"),
                now,
                now,
            ),
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
