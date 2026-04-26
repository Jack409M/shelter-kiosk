from __future__ import annotations

from datetime import UTC, datetime

from flask import flash, redirect, render_template, url_for

from core.db import db_fetchall, db_fetchone
from routes.admin_parts.helpers import require_admin_role


_ACTIVE_RESIDENT_SQL = """
COALESCE(LOWER(TRIM(CAST(is_active AS TEXT))), '') IN ('1', 'true', 't', 'yes')
"""

_ACTIVE_ENROLLMENT_SQL = """
LOWER(TRIM(COALESCE(program_status, ''))) = 'active'
"""


def _count(sql: str, params: tuple = ()) -> int:
    row = db_fetchone(sql, params) or {}
    value = row.get("count") or row.get("row_count") or 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    return db_fetchall(sql, params) or []


def _resident_has_active_enrollment(resident_id: object) -> bool:
    if not resident_id:
        return False

    row = db_fetchone(
        f"""
        SELECT 1 AS ok
        FROM program_enrollments
        WHERE resident_id = ?
          AND {_ACTIVE_ENROLLMENT_SQL}
        LIMIT 1
        """,
        (resident_id,),
    )
    return bool(row)


def _with_action(rows: list[dict], *, action_url: str, action_label: str) -> list[dict]:
    updated_rows = []
    for row in rows:
        updated_row = dict(row)
        resident_id = updated_row.get("id")
        if resident_id:
            updated_row["action_url"] = action_url.format(resident_id=resident_id)
            updated_row["action_label"] = action_label
        updated_rows.append(updated_row)
    return updated_rows


def _with_profile_action(rows: list[dict]) -> list[dict]:
    updated_rows = []

    for row in rows:
        updated_row = dict(row)
        resident_id = updated_row.get("id")

        if resident_id and _resident_has_active_enrollment(resident_id):
            updated_row["action_url"] = f"/staff/case-management/{resident_id}/intake-edit"
            updated_row["action_label"] = "Edit intake/profile"
        elif resident_id:
            updated_row["action_url"] = f"/staff/case-management/{resident_id}"
            updated_row["action_label"] = "Start or review enrollment"

        updated_rows.append(updated_row)

    return updated_rows


def _issue(
    *,
    key: str,
    label: str,
    description: str,
    severity: str,
    count: int,
    rows: list[dict],
    fix_note: str,
) -> dict:
    return {
        "key": key,
        "label": label,
        "description": description,
        "severity": severity,
        "count": count,
        "rows": rows,
        "fix_note": fix_note,
    }


def _missing_phone_issue() -> dict:
    where = f"{_ACTIVE_RESIDENT_SQL} AND COALESCE(TRIM(phone), '') = ''"
    count = _count(f"SELECT COUNT(*) AS count FROM residents WHERE {where}")
    rows = _rows(
        f"""
        SELECT id, first_name, last_name, shelter, phone
        FROM residents
        WHERE {where}
        ORDER BY shelter, last_name, first_name
        LIMIT 25
        """
    )
    rows = _with_profile_action(rows)
    return _issue(
        key="missing_phone",
        label="Missing phone",
        description="Active residents with no phone number on the resident profile.",
        severity="warn",
        count=count,
        rows=rows,
        fix_note="If the resident has an active enrollment, edit intake/profile. If not, start or review enrollment first.",
    )


def _missing_birth_year_issue() -> dict:
    where = f"{_ACTIVE_RESIDENT_SQL} AND birth_year IS NULL"
    count = _count(f"SELECT COUNT(*) AS count FROM residents WHERE {where}")
    rows = _rows(
        f"""
        SELECT id, first_name, last_name, shelter, birth_year
        FROM residents
        WHERE {where}
        ORDER BY shelter, last_name, first_name
        LIMIT 25
        """
    )
    rows = _with_profile_action(rows)
    return _issue(
        key="missing_birth_year",
        label="Missing birth year",
        description="Active residents with no birth year on the resident profile. Full date of birth is not collected.",
        severity="warn",
        count=count,
        rows=rows,
        fix_note="If the resident has an active enrollment, edit intake/profile. If not, start or review enrollment first. Birth year is collected, but full date of birth is not collected.",
    )


def _active_without_enrollment_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM residents r
        WHERE { _ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active') }
          AND NOT EXISTS (
              SELECT 1
              FROM program_enrollments pe
              WHERE pe.resident_id = r.id
                AND { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          )
        """
    )
    rows = _rows(
        f"""
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        WHERE { _ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active') }
          AND NOT EXISTS (
              SELECT 1
              FROM program_enrollments pe
              WHERE pe.resident_id = r.id
                AND { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          )
        ORDER BY r.shelter, r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_action(
        rows,
        action_url="/staff/case-management/{resident_id}",
        action_label="Open resident case",
    )
    return _issue(
        key="active_without_enrollment",
        label="Active resident without active enrollment",
        description="Residents marked active but not attached to an active program enrollment.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open the resident case page. Intake edit is not the right destination until an enrollment exists.",
    )


def _enrollment_shelter_mismatch_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          AND LOWER(TRIM(COALESCE(pe.shelter, ''))) <> LOWER(TRIM(COALESCE(r.shelter, '')))
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter AS resident_shelter,
            pe.shelter AS enrollment_shelter
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          AND LOWER(TRIM(COALESCE(pe.shelter, ''))) <> LOWER(TRIM(COALESCE(r.shelter, '')))
        ORDER BY r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_action(
        rows,
        action_url="/staff/case-management/{resident_id}",
        action_label="Open resident case",
    )
    return _issue(
        key="enrollment_shelter_mismatch",
        label="Enrollment shelter mismatch",
        description="Active enrollments where the enrollment shelter differs from the resident profile shelter.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open the resident case page and review whether this is a transfer, housing move, or bad shelter value.",
    )


def _missing_intake_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        WHERE { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          AND ia.id IS NULL
        """
    )
    rows = _rows(
        f"""
        SELECT r.id, r.first_name, r.last_name, pe.shelter, pe.entry_date
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        WHERE { _ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status') }
          AND ia.id IS NULL
        ORDER BY pe.entry_date DESC, r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_action(
        rows,
        action_url="/staff/case-management/{resident_id}/intake-edit",
        action_label="Open intake edit",
    )
    return _issue(
        key="missing_intake_baseline",
        label="Incomplete intake baseline",
        description="Active enrollments without an intake assessment baseline row.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open intake edit for review. If no intake row exists, the current edit screen may show a no intake found message and this will need a repair workflow later.",
    )


def _duplicate_names_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT LOWER(TRIM(first_name)) AS first_name_key,
                   LOWER(TRIM(last_name)) AS last_name_key
            FROM residents
            WHERE { _ACTIVE_RESIDENT_SQL }
            GROUP BY LOWER(TRIM(first_name)), LOWER(TRIM(last_name))
            HAVING COUNT(*) > 1
        ) duplicate_names
        """
    )
    rows = _rows(
        f"""
        SELECT
            MIN(id) AS id,
            LOWER(TRIM(first_name)) AS first_name,
            LOWER(TRIM(last_name)) AS last_name,
            COUNT(*) AS duplicate_count
        FROM residents
        WHERE { _ACTIVE_RESIDENT_SQL }
        GROUP BY LOWER(TRIM(first_name)), LOWER(TRIM(last_name))
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC, last_name, first_name
        LIMIT 25
        """
    )
    rows = _with_action(
        rows,
        action_url="/staff/case-management/{resident_id}",
        action_label="Review first match",
    )
    return _issue(
        key="duplicate_active_names",
        label="Duplicate active resident names",
        description="Active residents sharing the same first and last name.",
        severity="warn",
        count=count,
        rows=rows,
        fix_note="Open the first matching resident case and compare with the resident list before making changes.",
    )


def _load_data_quality_issues() -> list[dict]:
    return [
        _missing_phone_issue(),
        _missing_birth_year_issue(),
        _active_without_enrollment_issue(),
        _enrollment_shelter_mismatch_issue(),
        _missing_intake_issue(),
        _duplicate_names_issue(),
    ]


def system_health_data_quality_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    issues = _load_data_quality_issues()
    total_issues = sum(issue["count"] for issue in issues)
    error_count = sum(issue["count"] for issue in issues if issue["severity"] == "error")
    warning_count = sum(issue["count"] for issue in issues if issue["severity"] == "warn")

    return render_template(
        "sh_data_quality.html",
        title="Data Quality",
        checked_at=checked_at,
        issues=issues,
        total_issues=total_issues,
        error_count=error_count,
        warning_count=warning_count,
    )
