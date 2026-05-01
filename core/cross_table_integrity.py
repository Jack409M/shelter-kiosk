from __future__ import annotations

from typing import Any

from core.db import db_fetchall, db_fetchone

_ACTIVE_ENROLLMENT_SQL = """
LOWER(TRIM(COALESCE(program_status, ''))) = 'active'
"""

_ACTIVE_RESIDENT_SQL = """
COALESCE(LOWER(TRIM(CAST(is_active AS TEXT))), '') IN ('1', 'true', 't', 'yes')
"""


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = db_fetchone(sql, params) or {}
    value = row.get("count") or row.get("row_count") or 0

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return db_fetchall(sql, params) or []


def _issue(
    *,
    key: str,
    label: str,
    description: str,
    severity: str,
    count: int,
    rows: list[dict[str, Any]],
    fix_note: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "description": description,
        "severity": severity,
        "count": count,
        "rows": rows,
        "fix_note": fix_note,
    }


def _with_case_action(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated_rows: list[dict[str, Any]] = []

    for row in rows:
        updated_row = dict(row)
        resident_id = updated_row.get("id") or updated_row.get("resident_id")
        if resident_id:
            updated_row["action_url"] = f"/staff/case-management/{resident_id}"
            updated_row["action_label"] = "Open resident case"
        updated_rows.append(updated_row)

    return updated_rows


def _with_intake_action(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated_rows: list[dict[str, Any]] = []

    for row in rows:
        updated_row = dict(row)
        resident_id = updated_row.get("id") or updated_row.get("resident_id")
        if resident_id:
            updated_row["action_url"] = f"/staff/case-management/{resident_id}/intake-edit"
            updated_row["action_label"] = "Open intake edit"
        updated_rows.append(updated_row)

    return updated_rows


def _orphan_enrollments_issue() -> dict[str, Any]:
    count = _count(
        """
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE r.id IS NULL
        """
    )
    rows = _rows(
        """
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.shelter,
            pe.program_status,
            pe.entry_date
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE r.id IS NULL
        ORDER BY pe.id DESC
        LIMIT 25
        """
    )

    return _issue(
        key="orphan_enrollments",
        label="Orphan program enrollments",
        description="Program enrollments linked to a resident id that no longer exists.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Review manually before repair. These rows should not be reassigned without confirming the correct resident.",
    )


def _orphan_intake_assessments_issue() -> dict[str, Any]:
    count = _count(
        """
        SELECT COUNT(*) AS count
        FROM intake_assessments ia
        LEFT JOIN program_enrollments pe ON pe.id = ia.enrollment_id
        WHERE pe.id IS NULL
        """
    )
    rows = _rows(
        """
        SELECT
            ia.id AS intake_assessment_id,
            ia.enrollment_id,
            ia.created_at,
            ia.updated_at
        FROM intake_assessments ia
        LEFT JOIN program_enrollments pe ON pe.id = ia.enrollment_id
        WHERE pe.id IS NULL
        ORDER BY ia.id DESC
        LIMIT 25
        """
    )

    return _issue(
        key="orphan_intake_assessments",
        label="Orphan intake assessments",
        description="Intake baseline rows linked to an enrollment id that no longer exists.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Review manually. These rows are not reportable until linked to a valid enrollment or removed after backup.",
    )


def _orphan_family_snapshots_issue() -> dict[str, Any]:
    count = _count(
        """
        SELECT COUNT(*) AS count
        FROM family_snapshots fs
        LEFT JOIN program_enrollments pe ON pe.id = fs.enrollment_id
        WHERE pe.id IS NULL
        """
    )
    rows = _rows(
        """
        SELECT
            fs.id AS family_snapshot_id,
            fs.enrollment_id,
            fs.created_at,
            fs.updated_at
        FROM family_snapshots fs
        LEFT JOIN program_enrollments pe ON pe.id = fs.enrollment_id
        WHERE pe.id IS NULL
        ORDER BY fs.id DESC
        LIMIT 25
        """
    )

    return _issue(
        key="orphan_family_snapshots",
        label="Orphan family snapshots",
        description="Family baseline rows linked to an enrollment id that no longer exists.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Review manually. These rows are not reportable until linked to a valid enrollment or removed after backup.",
    )


def _missing_family_baseline_issue() -> dict[str, Any]:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN family_snapshots fs ON fs.enrollment_id = pe.id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND fs.id IS NULL
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            pe.id AS enrollment_id,
            r.first_name,
            r.last_name,
            pe.shelter,
            pe.entry_date
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN family_snapshots fs ON fs.enrollment_id = pe.id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND fs.id IS NULL
        ORDER BY pe.entry_date DESC, r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_intake_action(rows)

    return _issue(
        key="missing_family_baseline",
        label="Missing family baseline",
        description="Active enrollments without a family snapshot baseline row.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open intake edit and save a complete baseline. Do not infer family counts from reports.",
    )


def _duplicate_active_enrollments_issue() -> dict[str, Any]:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT resident_id
            FROM program_enrollments
            WHERE {_ACTIVE_ENROLLMENT_SQL}
            GROUP BY resident_id
            HAVING COUNT(*) > 1
        ) duplicate_active
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter,
            COUNT(pe.id) AS active_enrollment_count,
            MIN(pe.entry_date) AS earliest_entry_date,
            MAX(pe.entry_date) AS latest_entry_date
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
        GROUP BY r.id, r.first_name, r.last_name, r.shelter
        HAVING COUNT(pe.id) > 1
        ORDER BY active_enrollment_count DESC, r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_case_action(rows)

    return _issue(
        key="duplicate_active_enrollments",
        label="Multiple active enrollments",
        description="Residents with more than one active program enrollment.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open the resident case and decide which enrollment should remain active. Do not auto close without review.",
    )


def _duplicate_intake_baselines_issue() -> dict[str, Any]:
    count = _count(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT enrollment_id
            FROM intake_assessments
            GROUP BY enrollment_id
            HAVING COUNT(*) > 1
        ) duplicate_intakes
        """
    )
    rows = _rows(
        """
        SELECT
            ia.enrollment_id,
            pe.resident_id AS id,
            r.first_name,
            r.last_name,
            COUNT(ia.id) AS intake_baseline_count,
            MAX(ia.id) AS newest_intake_assessment_id
        FROM intake_assessments ia
        LEFT JOIN program_enrollments pe ON pe.id = ia.enrollment_id
        LEFT JOIN residents r ON r.id = pe.resident_id
        GROUP BY ia.enrollment_id, pe.resident_id, r.first_name, r.last_name
        HAVING COUNT(ia.id) > 1
        ORDER BY intake_baseline_count DESC, ia.enrollment_id DESC
        LIMIT 25
        """
    )
    rows = _with_intake_action(rows)

    return _issue(
        key="duplicate_intake_baselines",
        label="Duplicate intake baselines",
        description="Enrollments with more than one intake assessment baseline row.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Review manually. The official baseline should be one row per enrollment.",
    )


def _duplicate_family_baselines_issue() -> dict[str, Any]:
    count = _count(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT enrollment_id
            FROM family_snapshots
            GROUP BY enrollment_id
            HAVING COUNT(*) > 1
        ) duplicate_family
        """
    )
    rows = _rows(
        """
        SELECT
            fs.enrollment_id,
            pe.resident_id AS id,
            r.first_name,
            r.last_name,
            COUNT(fs.id) AS family_baseline_count,
            MAX(fs.id) AS newest_family_snapshot_id
        FROM family_snapshots fs
        LEFT JOIN program_enrollments pe ON pe.id = fs.enrollment_id
        LEFT JOIN residents r ON r.id = pe.resident_id
        GROUP BY fs.enrollment_id, pe.resident_id, r.first_name, r.last_name
        HAVING COUNT(fs.id) > 1
        ORDER BY family_baseline_count DESC, fs.enrollment_id DESC
        LIMIT 25
        """
    )
    rows = _with_intake_action(rows)

    return _issue(
        key="duplicate_family_baselines",
        label="Duplicate family baselines",
        description="Enrollments with more than one family snapshot baseline row.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Review manually. The official family baseline should be one row per enrollment.",
    )


def _inactive_resident_with_active_enrollment_issue() -> dict[str, Any]:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND NOT ({_ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active')})
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            pe.id AS enrollment_id,
            r.first_name,
            r.last_name,
            r.shelter,
            r.is_active,
            pe.program_status
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND NOT ({_ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active')})
        ORDER BY r.last_name, r.first_name
        LIMIT 25
        """
    )
    rows = _with_case_action(rows)

    return _issue(
        key="inactive_resident_with_active_enrollment",
        label="Inactive resident with active enrollment",
        description="Residents marked inactive while still having an active program enrollment.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Open the resident case and resolve the lifecycle state. Exit should normally drive deactivation.",
    )


def load_cross_table_integrity_issues() -> list[dict[str, Any]]:
    return [
        _orphan_enrollments_issue(),
        _orphan_intake_assessments_issue(),
        _orphan_family_snapshots_issue(),
        _missing_family_baseline_issue(),
        _duplicate_active_enrollments_issue(),
        _duplicate_intake_baselines_issue(),
        _duplicate_family_baselines_issue(),
        _inactive_resident_with_active_enrollment_issue(),
    ]
