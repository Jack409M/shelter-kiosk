from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.attendance_hours import build_attendance_hours_snapshot
from core.db import db_fetchall
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.inspection_v2 import build_inspection_stability_snapshot
from routes.rent_tracking import build_rent_stability_snapshot


def _to_float(value) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _to_bool_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if value in {1, "1", "true", "True", "yes", "Yes", "on"}:
        return True
    if value in {0, "0", "false", "False", "no", "No", "off"}:
        return False
    return bool(value)


def _build_engagement_score(recovery_snapshot: dict | None) -> float | None:
    snapshot = recovery_snapshot or {}

    score = 0.0
    signal_count = 0

    employment_status = str(snapshot.get("employment_status_current") or "").strip().lower()
    if employment_status:
        signal_count += 1
        if employment_status == "employed":
            score += 40.0

    sponsor_active = _to_bool_or_none(snapshot.get("sponsor_active"))
    if sponsor_active is not None:
        signal_count += 1
        if sponsor_active:
            score += 30.0

    step_work_active = _to_bool_or_none(snapshot.get("step_work_active"))
    if step_work_active is not None:
        signal_count += 1
        if step_work_active:
            score += 20.0

    program_level_raw = str(snapshot.get("program_level") or "").strip()
    if program_level_raw:
        signal_count += 1
        try:
            program_level = int(program_level_raw)
        except Exception:
            program_level = None

        if program_level is not None:
            if program_level >= 3:
                score += 10.0
            elif program_level == 2:
                score += 5.0

    if signal_count == 0:
        return None

    return round(min(score, 100.0), 1)


def _build_readiness_score(resident_id: int, shelter: str) -> dict:
    enrollment = fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            entry_date
        """,
    )
    enrollment_id = enrollment.get("id") if enrollment else None
    enrollment_entry_date = enrollment.get("entry_date") if enrollment else None

    attendance_snapshot = build_attendance_hours_snapshot(
        resident_id=resident_id,
        shelter=shelter,
        enrollment_entry_date=enrollment_entry_date,
    )
    inspection_snapshot = build_inspection_stability_snapshot(
        resident_id,
        shelter=shelter,
    )
    rent_snapshot = build_rent_stability_snapshot(resident_id)
    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)

    weighted_total = 0.0
    weight_used = 0.0
    detail_parts: list[str] = []

    attendance_weeks = int(attendance_snapshot.get("eligible_weeks_count") or 0)
    if attendance_weeks > 0:
        attendance_score = _to_float(attendance_snapshot.get("average_percent"))
        weighted_total += attendance_score * 0.40
        weight_used += 0.40
        detail_parts.append(f"Attendance {attendance_score:.1f}")

    inspection_count = int(inspection_snapshot.get("inspection_count") or 0)
    if inspection_count > 0:
        inspection_score = _to_float(inspection_snapshot.get("average_score"))
        weighted_total += inspection_score * 0.25
        weight_used += 0.25
        detail_parts.append(f"Inspection {inspection_score:.1f}")

    rent_month_rows = rent_snapshot.get("month_rows") or []
    rent_has_history = any(_to_float(row.get("score")) > 0 for row in rent_month_rows)
    if rent_has_history:
        rent_score = _to_float(rent_snapshot.get("average_score"))
        weighted_total += rent_score * 0.20
        weight_used += 0.20
        detail_parts.append(f"Rent {rent_score:.1f}")

    engagement_score = _build_engagement_score(recovery_snapshot)
    if engagement_score is not None:
        weighted_total += engagement_score * 0.15
        weight_used += 0.15
        detail_parts.append(f"Recovery Engagement {engagement_score:.1f}")

    if weight_used == 0:
        return {
            "score": None,
            "score_display": "—",
            "label": "Pending",
            "tone": "pending",
            "detail": "Waiting for enough scoring data to calculate a readiness score.",
        }

    score = int(round(weighted_total / weight_used))

    if score >= 80:
        label = "Doing Great"
        tone = "great"
    elif score >= 50:
        label = "Struggling"
        tone = "struggling"
    else:
        label = "Failing"
        tone = "failing"

    return {
        "score": score,
        "score_display": str(score),
        "label": label,
        "tone": tone,
        "detail": " | ".join(detail_parts) if detail_parts else "Composite readiness score",
    }


def index_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    show = (request.args.get("show") or "active").strip().lower()
    if show not in {"active", "all"}:
        show = "active"

    if show == "all":
        resident_rows = db_fetchall(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                resident_code,
                is_active
            FROM residents
            WHERE {shelter_equals_sql("shelter")}
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """,
            (shelter,),
        )
    else:
        active_sql = "TRUE" if g.get("db_kind") == "pg" else "1"
        resident_rows = db_fetchall(
            f"""
            SELECT
                id,
                first_name,
                last_name,
                resident_code,
                is_active
            FROM residents
            WHERE {shelter_equals_sql("shelter")}
              AND is_active = {active_sql}
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    residents = [dict(row) for row in resident_rows]

    for resident in residents:
        resident["readiness"] = _build_readiness_score(resident["id"], shelter)

    return render_template(
        "case_management/index.html",
        residents=residents,
        shelter=shelter,
        show=show,
    )


def intake_index_view():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    shelter_param = "%s" if g.get("db_kind") == "pg" else "?"

    drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    duplicate_review_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'pending_duplicate_review'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    assessment_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            updated_at
        FROM assessment_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {shelter_param}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    residents = db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    return render_template(
        "intake_assessment/index.html",
        drafts=drafts,
        duplicate_review_drafts=duplicate_review_drafts,
        assessment_drafts=assessment_drafts,
        shelter=shelter,
        residents=residents,
    )
