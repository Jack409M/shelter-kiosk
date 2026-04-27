from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from routes.admin_parts.helpers import require_admin_role
from routes.case_management_parts.helpers import placeholder


_ACTIVE_RESIDENT_SQL = """
COALESCE(LOWER(TRIM(CAST(is_active AS TEXT))), '') IN ('1', 'true', 't', 'yes')
"""

_ACTIVE_ENROLLMENT_SQL = """
LOWER(TRIM(COALESCE(program_status, ''))) = 'active'
"""

_UNCONFIRMED_DUPLICATE_NAME_SQL = """
NOT EXISTS (
    SELECT 1
    FROM duplicate_name_reviews dnr
    WHERE dnr.first_name_key = LOWER(TRIM(first_name))
      AND dnr.last_name_key = LOWER(TRIM(last_name))
      AND dnr.status IN ('verified_separate_people', 'needs_merge_review')
)
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

        if resident_id:
            updated_row["action_url"] = f"/staff/residents/{resident_id}/edit"
            updated_row["action_label"] = "Edit profile"

        updated_rows.append(updated_row)

    return updated_rows


def _with_missing_intake_fix(rows: list[dict]) -> list[dict]:
    updated_rows = []

    for row in rows:
        updated_row = dict(row)
        enrollment_id = updated_row.get("enrollment_id")

        if enrollment_id:
            updated_row["action_post_url"] = (
                f"/staff/admin/system-health/data-quality/fix/missing-intake/{enrollment_id}"
            )
            updated_row["action_post_label"] = "Create intake baseline"

        updated_rows.append(updated_row)

    return updated_rows


def _with_shelter_mismatch_fix(rows: list[dict]) -> list[dict]:
    updated_rows = []

    for row in rows:
        updated_row = dict(row)
        enrollment_id = updated_row.get("enrollment_id")

        if enrollment_id:
            updated_row["action_post_actions"] = [
                {
                    "url": (
                        "/staff/admin/system-health/data-quality/fix/"
                        f"shelter-mismatch/{enrollment_id}/resident"
                    ),
                    "label": "Set resident to enrollment shelter",
                },
                {
                    "url": (
                        "/staff/admin/system-health/data-quality/fix/"
                        f"shelter-mismatch/{enrollment_id}/enrollment"
                    ),
                    "label": "Set enrollment to resident shelter",
                },
            ]

        updated_rows.append(updated_row)

    return updated_rows


def _with_duplicate_review_actions(rows: list[dict]) -> list[dict]:
    updated_rows = []

    for row in rows:
        updated_row = dict(row)
        first_name_key = (updated_row.get("first_name") or "").strip().lower()
        last_name_key = (updated_row.get("last_name") or "").strip().lower()

        if first_name_key and last_name_key:
            updated_row["action_url"] = (
                "/staff/admin/system-health/data-quality/duplicate-names/review"
                f"?first_name_key={quote(first_name_key)}&last_name_key={quote(last_name_key)}"
            )
            updated_row["action_label"] = "Review side by side"
            updated_row["action_post_actions"] = [
                {
                    "url": "/staff/admin/system-health/data-quality/fix/duplicate-names/mark-same",
                    "label": "Same person",
                    "hidden_fields": {
                        "first_name_key": first_name_key,
                        "last_name_key": last_name_key,
                    },
                },
                {
                    "url": "/staff/admin/system-health/data-quality/fix/duplicate-names/confirm-separate",
                    "label": "Not same person",
                    "hidden_fields": {
                        "first_name_key": first_name_key,
                        "last_name_key": last_name_key,
                    },
                },
            ]

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
        fix_note="Open the resident profile editor. Phone can be corrected without requiring enrollment.",
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
        fix_note="Open the resident profile editor. Birth year is collected, but full date of birth is not collected.",
    )


def _active_without_enrollment_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM residents r
        WHERE {_ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active')}
          AND NOT EXISTS (
              SELECT 1
              FROM program_enrollments pe
              WHERE pe.resident_id = r.id
                AND {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          )
        """
    )
    rows = _rows(
        f"""
        SELECT r.id, r.first_name, r.last_name, r.shelter
        FROM residents r
        WHERE {_ACTIVE_RESIDENT_SQL.replace('is_active', 'r.is_active')}
          AND NOT EXISTS (
              SELECT 1
              FROM program_enrollments pe
              WHERE pe.resident_id = r.id
                AND {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
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
        fix_note="Open the resident case page to start or review enrollment.",
    )


def _enrollment_shelter_mismatch_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND LOWER(TRIM(COALESCE(pe.shelter, ''))) <> LOWER(TRIM(COALESCE(r.shelter, '')))
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            pe.id AS enrollment_id,
            r.first_name,
            r.last_name,
            r.shelter AS resident_shelter,
            pe.shelter AS enrollment_shelter
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
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
    rows = _with_shelter_mismatch_fix(rows)

    return _issue(
        key="enrollment_shelter_mismatch",
        label="Enrollment shelter mismatch",
        description="Active enrollments where the enrollment shelter differs from the resident profile shelter.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Choose which shelter value is correct, then apply the matching repair action.",
    )


def _missing_intake_issue() -> dict:
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
          AND ia.id IS NULL
        """
    )
    rows = _rows(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            pe.id AS enrollment_id,
            pe.shelter,
            pe.entry_date
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        LEFT JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        WHERE {_ACTIVE_ENROLLMENT_SQL.replace('program_status', 'pe.program_status')}
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
    rows = _with_missing_intake_fix(rows)

    return _issue(
        key="missing_intake_baseline",
        label="Incomplete intake baseline",
        description="Active enrollments without an intake assessment baseline row.",
        severity="error",
        count=count,
        rows=rows,
        fix_note="Create intake baseline, then complete intake edit.",
    )


def _duplicate_names_issue() -> dict:
    where = f"{_ACTIVE_RESIDENT_SQL} AND {_UNCONFIRMED_DUPLICATE_NAME_SQL}"
    count = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT
                LOWER(TRIM(first_name)) AS first_name_key,
                LOWER(TRIM(last_name)) AS last_name_key
            FROM residents
            WHERE {where}
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
        WHERE {where}
        GROUP BY LOWER(TRIM(first_name)), LOWER(TRIM(last_name))
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC, last_name, first_name
        LIMIT 25
        """
    )
    rows = _with_duplicate_review_actions(rows)

    return _issue(
        key="duplicate_active_names",
        label="Duplicate active resident names",
        description="Active residents sharing the same first and last name.",
        severity="warn",
        count=count,
        rows=rows,
        fix_note="Review matching records side by side, then mark them as same person or not same person.",
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


def fix_missing_intake_baseline_view(enrollment_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ph = placeholder()

    enrollment = db_fetchone(
        f"""
        SELECT id, resident_id
        FROM program_enrollments
        WHERE id = {ph}
        """,
        (enrollment_id,),
    )

    if not enrollment:
        flash("Enrollment not found.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    resident_id = enrollment["resident_id"]

    existing = db_fetchone(
        f"""
        SELECT id
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if existing:
        return redirect(url_for("case_management.intake_edit", resident_id=resident_id))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    columns = [
        "enrollment_id",
        "city",
        "county",
        "last_zipcode_residence",
        "length_of_time_in_amarillo",
        "income_at_entry",
        "education_at_entry",
        "treatment_grad_date",
        "sobriety_date",
        "days_sober_at_entry",
        "drug_of_choice",
        "ace_score",
        "grit_score",
        "veteran",
        "disability",
        "marital_status",
        "notes_basic",
        "entry_notes",
        "initial_snapshot_notes",
        "trauma_notes",
        "barrier_notes",
        "place_staying_before_entry",
        "entry_felony_conviction",
        "entry_parole_probation",
        "drug_court",
        "sexual_survivor",
        "dv_survivor",
        "human_trafficking_survivor",
        "warrants_unpaid",
        "mh_exam_completed",
        "med_exam_completed",
        "car_at_entry",
        "car_insurance_at_entry",
        "pregnant_at_entry",
        "dental_need_at_entry",
        "vision_need_at_entry",
        "employment_status_at_entry",
        "mental_health_need_at_entry",
        "medical_need_at_entry",
        "substance_use_need_at_entry",
        "id_documents_status_at_entry",
        "has_drivers_license",
        "has_social_security_card",
        "parenting_class_needed",
        "dwc_level_today",
        "created_at",
        "updated_at",
    ]

    values = [
        enrollment_id,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        "unknown",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        None,
        0,
        0,
        0,
        None,
        0,
        0,
        0,
        None,
        now,
        now,
    ]

    ph_list = ",".join([placeholder()] * len(columns))

    with db_transaction():
        db_execute(
            f"INSERT INTO intake_assessments ({','.join(columns)}) VALUES ({ph_list})",
            tuple(values),
        )

    flash("Intake baseline created. Complete and save the intake edit form.", "success")
    return redirect(url_for("case_management.intake_edit", resident_id=resident_id))


def fix_shelter_mismatch_view(enrollment_id: int, target: str):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    target = (target or "").strip().lower()

    if target not in {"resident", "enrollment"}:
        flash("Invalid shelter repair target.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.shelter AS enrollment_shelter,
            r.shelter AS resident_shelter
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        WHERE pe.id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if not row:
        flash("Enrollment not found.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    resident_id = row["resident_id"]
    resident_shelter = (row.get("resident_shelter") or "").strip()
    enrollment_shelter = (row.get("enrollment_shelter") or "").strip()

    if not resident_shelter or not enrollment_shelter:
        flash("Cannot repair shelter mismatch because one shelter value is blank.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        if target == "resident":
            db_execute(
                f"""
                UPDATE residents
                SET shelter = {ph}, updated_at = {ph}
                WHERE id = {ph}
                """,
                (enrollment_shelter, now, resident_id),
            )
            flash("Resident shelter updated to match enrollment shelter.", "success")

        if target == "enrollment":
            db_execute(
                f"""
                UPDATE program_enrollments
                SET shelter = {ph}, updated_at = {ph}
                WHERE id = {ph}
                """,
                (resident_shelter, now, enrollment_id),
            )
            flash("Enrollment shelter updated to match resident shelter.", "success")

    return redirect(url_for("admin.admin_system_health_data_quality"))


def confirm_duplicate_names_separate_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    first_name_key = (request.form.get("first_name_key") or "").strip().lower()
    last_name_key = (request.form.get("last_name_key") or "").strip().lower()

    if not first_name_key or not last_name_key:
        flash("Invalid duplicate confirmation request.", "error")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    ph = placeholder()
    existing = db_fetchone(
        f"""
        SELECT id
        FROM duplicate_name_reviews
        WHERE first_name_key = {ph}
          AND last_name_key = {ph}
          AND status = 'verified_separate_people'
        LIMIT 1
        """,
        (first_name_key, last_name_key),
    )

    if existing:
        flash("Duplicate group already confirmed as separate people.", "info")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    active_matches = _count(
        f"""
        SELECT COUNT(*) AS count
        FROM residents
        WHERE {_ACTIVE_RESIDENT_SQL}
          AND LOWER(TRIM(first_name)) = {ph}
          AND LOWER(TRIM(last_name)) = {ph}
        """,
        (first_name_key, last_name_key),
    )

    if active_matches < 2:
        flash("Duplicate group no longer has multiple active matching residents.", "warning")
        return redirect(url_for("admin.admin_system_health_data_quality"))

    raw_staff_user_id = session.get("staff_user_id")
    try:
        staff_user_id = int(raw_staff_user_id) if raw_staff_user_id not in (None, "") else None
    except (TypeError, ValueError):
        staff_user_id = None

    now = datetime.now(UTC).replace(tzinfo=None).isoformat()

    with db_transaction():
        db_execute(
            f"""
            INSERT INTO duplicate_name_reviews
            (
                first_name_key,
                last_name_key,
                status,
                reviewed_by_user_id,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (
                first_name_key,
                last_name_key,
                "verified_separate_people",
                staff_user_id,
                now,
                now,
                now,
            ),
        )

    flash("Duplicate name group confirmed as not the same person.", "success")
    return redirect(url_for("admin.admin_system_health_data_quality"))


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
