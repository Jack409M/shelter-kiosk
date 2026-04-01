from __future__ import annotations

# ============================================================================
# Case Management Routes
# ----------------------------------------------------------------------------
# This file is now the transition shell for case management.
#
# Current responsibilities still living here:
# 1. Temporary admin utilities during build and testing
#
# Extracted:
# - routes.case_management_parts.assessment
#   assessment form, assessment drafts, validation, and persistence
# - routes.case_management_parts.intake_drafts
#   intake draft save, load, and complete
# - routes.case_management_parts.intake_validation
#   intake validation and duplicate detection
# - routes.case_management_parts.intake_inserts
#   resident, enrollment, intake assessment, and family snapshot inserts
# - routes.case_management_parts.intake
#   intake form flow shell
# - routes.case_management_parts.family
#   family intake, child records, and child services
# - routes.case_management_parts.intake_duplicates
#   duplicate review flow for pending intake records
# - routes.case_management_parts.resident_case
#   resident summary page and related reads
# - routes.case_management_parts.index
#   dashboard and intake landing
# - routes.case_management_parts.update
#   progress update flow
# - routes.case_management_parts.actions
#   create enrollment, add goal, and add appointment writes
# - routes.case_management_parts.exit
#   exit assessment flow
# - routes.case_management_parts.followups
#   6 month and 1 year follow up flow
#
# Future extraction plan:
# - routes.case_management_parts.helpers
#   shared parsing, shelter, permission, and SQL helpers
#
# Goal:
# keep shrinking this file until it becomes a thin blueprint shell like admin.py
# ============================================================================

from flask import Blueprint, flash, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_pretty_dt, utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.actions import add_appointment_view
from routes.case_management_parts.actions import add_goal_view
from routes.case_management_parts.actions import create_enrollment_view
from routes.case_management_parts.assessment import assessment_form_view
from routes.case_management_parts.assessment import submit_assessment_view
from routes.case_management_parts.budget_sessions import add_budget_session_view
from routes.case_management_parts.budget_sessions import budget_sessions_view
from routes.case_management_parts.budget_sessions import edit_budget_session_view
from routes.case_management_parts.exit import exit_assessment_form_view
from routes.case_management_parts.exit import submit_exit_assessment_view
from routes.case_management_parts.family import child_services_view
from routes.case_management_parts.family import delete_child_service_view
from routes.case_management_parts.family import delete_child_view
from routes.case_management_parts.family import edit_child_service_view
from routes.case_management_parts.family import edit_child_view
from routes.case_management_parts.family import family_intake_view
from routes.case_management_parts.followups import followup_form_view
from routes.case_management_parts.followups import submit_followup_view
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import digits_only
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.helpers import yes_no_to_int
from routes.case_management_parts.index import index_view
from routes.case_management_parts.index import intake_index_view
from routes.case_management_parts.inspection_log import add_inspection_log_view
from routes.case_management_parts.inspection_log import edit_inspection_log_view
from routes.case_management_parts.inspection_log import inspection_log_view
from routes.case_management_parts.intake import intake_edit_view
from routes.case_management_parts.intake import intake_form_view
from routes.case_management_parts.intake import submit_intake_assessment_view
from routes.case_management_parts.intake_duplicates import duplicate_review_create_new_view
from routes.case_management_parts.intake_duplicates import duplicate_review_dismiss_view
from routes.case_management_parts.intake_duplicates import duplicate_review_return_to_edit_view
from routes.case_management_parts.intake_duplicates import duplicate_review_use_existing_view
from routes.case_management_parts.intake_duplicates import duplicate_review_view
from routes.case_management_parts.medications import add_medication_view
from routes.case_management_parts.medications import edit_medication_view
from routes.case_management_parts.medications import medication_form_view
from routes.case_management_parts.recovery_profile import update_recovery_profile_view
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case import resident_case_view
from routes.case_management_parts.resident_case_notes import build_note_objects
from routes.case_management_parts.ua_log import add_ua_log_view
from routes.case_management_parts.ua_log import edit_ua_log_view
from routes.case_management_parts.ua_log import ua_log_view
from routes.case_management_parts.update import add_case_note_view
from routes.case_management_parts.update import edit_case_note_view


# ============================================================================
# Compatibility aliases
# ----------------------------------------------------------------------------
# Other route modules still import the old underscore helper names directly
# from routes.case_management. Keep these aliases in place during the refactor
# so those modules do not break while logic is moved into case_management_parts.
# ============================================================================

_case_manager_allowed = case_manager_allowed
_clean = clean
_digits_only = digits_only
_normalize_shelter_name = normalize_shelter_name
_parse_int = parse_int
_parse_iso_date = parse_iso_date
_parse_money = parse_money
_placeholder = placeholder
_shelter_equals_sql = shelter_equals_sql
_yes_no_to_int = yes_no_to_int


# ============================================================================
# Blueprint Registration
# ----------------------------------------------------------------------------
# All routes in this file live under /staff/case-management
#
# Future state:
# this file should mostly contain blueprint creation plus thin decorated wrappers
# that delegate into routes.case_management_parts.*
# ============================================================================

case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


def _load_current_enrollment(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        """,
    )


def _load_single_case_note(enrollment_id: int, update_id: int):
    ph = placeholder()

    notes_raw = db_fetchall(
        f"""
        SELECT
            id,
            staff_user_id,
            meeting_date,
            notes,
            progress_notes,
            setbacks_or_incidents,
            action_items,
            next_appointment,
            overall_summary,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            created_at
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND id = {ph}
        LIMIT 1
        """,
        (enrollment_id, update_id),
    )

    if not notes_raw:
        return None

    services_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            service_type,
            service_date,
            quantity,
            unit,
            notes
        FROM client_services
        WHERE enrollment_id = {ph}
          AND case_manager_update_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (enrollment_id, update_id),
    )

    summary_rows_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
        ORDER BY sort_order ASC, id ASC
        """,
        (update_id,),
    )

    notes, _ = build_note_objects(notes_raw, services_raw, summary_rows_raw)
    return notes[0] if notes else None


def _load_case_manager_name(staff_user_id: int | None) -> str:
    if not staff_user_id:
        return "Current Staff"

    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            first_name,
            last_name,
            username
        FROM staff_users
        WHERE id = {ph}
        LIMIT 1
        """,
        (staff_user_id,),
    )

    if not row:
        return "Current Staff"

    first_name = (row.get("first_name") or "").strip()
    last_name = (row.get("last_name") or "").strip()
    username = (row.get("username") or "").strip()

    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or username or "Current Staff"


def _build_progress_report_context(
    *,
    resident: dict,
    enrollment: dict | None,
    note: dict,
    goals: list[dict],
    recovery_snapshot: dict | None,
    case_manager_name: str,
):
    recovery_snapshot = recovery_snapshot or {}
    note_services = note.get("services") or []

    resident_name = " ".join(
        part for part in [resident.get("first_name"), resident.get("last_name")] if part
    ).strip() or "Resident"

    resident_display_id = (
        resident.get("resident_identifier")
        or resident.get("resident_code")
        or str(resident.get("id") or "")
    )

    service_rows = []
    for service in note_services:
        quantity_display = service.get("quantity_display")
        service_rows.append(
            {
                "service_type": service.get("service_type") or "—",
                "service_date": service.get("service_date") or note.get("meeting_date") or "—",
                "quantity_display": quantity_display if quantity_display and quantity_display != "—" else "",
                "notes": service.get("notes") or "",
            }
        )

    goal_rows = []
    for goal in goals:
        goal_rows.append(
            {
                "goal_text": goal.get("goal_text") or "—",
                "status": goal.get("status") or "—",
                "target_date": goal.get("target_date") or "",
            }
        )

    generated_at = utcnow_iso()

    return {
        "report_title": "Progress Report",
        "generated_at_display": fmt_pretty_dt(generated_at),
        "resident_name": resident_name,
        "resident_display_id": resident_display_id,
        "resident": resident,
        "enrollment": enrollment,
        "note": note,
        "goals": goal_rows,
        "case_manager_name": case_manager_name,
        "service_rows": service_rows,
        "program_snapshot": [
            {"label": "Program Status", "value": enrollment.get("program_status") if enrollment else "—"},
            {"label": "Level", "value": recovery_snapshot.get("program_level") or "—"},
            {"label": "Level Start Date", "value": recovery_snapshot.get("level_start_date") or "—"},
            {
                "label": "Days On Level",
                "value": recovery_snapshot.get("days_on_level")
                if recovery_snapshot.get("days_on_level") is not None
                else "—",
            },
            {
                "label": "Days Sober",
                "value": recovery_snapshot.get("days_sober_today")
                if recovery_snapshot.get("days_sober_today") is not None
                else "—",
            },
            {"label": "Sobriety Date", "value": recovery_snapshot.get("sobriety_date") or "—"},
            {"label": "Drug Of Choice", "value": recovery_snapshot.get("drug_of_choice") or "—"},
            {"label": "Sponsor", "value": recovery_snapshot.get("sponsor_name") or "—"},
            {"label": "Employment Status", "value": recovery_snapshot.get("employment_status_current") or "—"},
            {
                "label": "Monthly Income",
                "value": recovery_snapshot.get("monthly_income")
                if recovery_snapshot.get("monthly_income") not in (None, "")
                else "—",
            },
        ],
        "advancement_rows": [
            {"label": "Ready For Next Level", "value": note.get("ready_for_next_level_display") or "—"},
            {"label": "Recommended Next Level", "value": note.get("recommended_next_level") or "—"},
            {"label": "Blocker Reason", "value": note.get("blocker_reason") or "—"},
            {"label": "Override Or Exception", "value": note.get("override_or_exception") or "—"},
            {"label": "Staff Review Note", "value": note.get("staff_review_note") or "—"},
        ],
    }


# ============================================================================
# Index and Intake Landing Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.index
# ============================================================================

@case_management.get("/")
@require_login
@require_shelter
def index():
    return index_view()


@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_index():
    return intake_index_view()


# ============================================================================
# Assessment Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.assessment
# ============================================================================

@case_management.get("/assessment/new")
@require_login
@require_shelter
def assessment_form():
    return assessment_form_view()


@case_management.post("/assessment/new")
@require_login
@require_shelter
def submit_assessment():
    return submit_assessment_view()


# ============================================================================
# Intake Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.intake
# ============================================================================

@case_management.get("/intake-assessment/new")
@require_login
@require_shelter
def intake_form():
    return intake_form_view()


@case_management.post("/intake-assessment/new")
@require_login
@require_shelter
def submit_intake_assessment():
    return submit_intake_assessment_view()


@case_management.get("/<int:resident_id>/intake-edit")
@require_login
@require_shelter
def intake_edit(resident_id: int):
    return intake_edit_view(resident_id)


@case_management.route("/<int:resident_id>/family-intake", methods=["GET", "POST"])
@require_login
@require_shelter
def family_intake(resident_id: int):
    return family_intake_view(resident_id)


@case_management.route("/child/<int:child_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_child(child_id: int):
    return edit_child_view(child_id)


@case_management.post("/child/<int:child_id>/delete")
@require_login
@require_shelter
def delete_child(child_id: int):
    return delete_child_view(child_id)


@case_management.route("/child/<int:child_id>/services", methods=["GET", "POST"])
@require_login
@require_shelter
def child_services(child_id: int):
    return child_services_view(child_id)


@case_management.route("/child-service/<int:service_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_child_service(service_id: int):
    return edit_child_service_view(service_id)


@case_management.post("/child-service/<int:service_id>/delete")
@require_login
@require_shelter
def delete_child_service(service_id: int):
    return delete_child_service_view(service_id)


# ============================================================================
# Intake Duplicate Review Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.intake_duplicates
# ============================================================================

@case_management.get("/intake-assessment/duplicate-review/<int:draft_id>")
@require_login
@require_shelter
def intake_duplicate_review(draft_id: int):
    return duplicate_review_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/use-existing")
@require_login
@require_shelter
def intake_duplicate_use_existing(draft_id: int):
    return duplicate_review_use_existing_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/create-new")
@require_login
@require_shelter
def intake_duplicate_create_new(draft_id: int):
    return duplicate_review_create_new_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/dismiss")
@require_login
@require_shelter
def intake_duplicate_dismiss(draft_id: int):
    return duplicate_review_dismiss_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/return-to-edit")
@require_login
@require_shelter
def intake_duplicate_return_to_edit(draft_id: int):
    return duplicate_review_return_to_edit_view(draft_id)


# ============================================================================
# Exit Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.exit
# ============================================================================

@case_management.get("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def exit_assessment(resident_id: int):
    return exit_assessment_form_view(resident_id)


@case_management.post("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def submit_exit_assessment(resident_id: int):
    return submit_exit_assessment_view(resident_id)


# ============================================================================
# Follow Up Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.followups
# ============================================================================

@case_management.get("/<int:resident_id>/followup/<string:followup_type>")
@require_login
@require_shelter
def followup_form(resident_id: int, followup_type: str):
    return followup_form_view(resident_id, followup_type)


@case_management.post("/<int:resident_id>/followup/<string:followup_type>")
@require_login
@require_shelter
def submit_followup(resident_id: int, followup_type: str):
    return submit_followup_view(resident_id, followup_type)


# ============================================================================
# Case Management Actions
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.actions
# ============================================================================

@case_management.post("/case/<int:resident_id>/enroll")
@require_login
@require_shelter
def create_enrollment(resident_id: int):
    return create_enrollment_view(resident_id)


@case_management.post("/case/<int:resident_id>/goal")
@require_login
@require_shelter
def add_goal(resident_id: int):
    return add_goal_view(resident_id)


@case_management.post("/case/<int:resident_id>/appointment")
@require_login
@require_shelter
def add_appointment(resident_id: int):
    return add_appointment_view(resident_id)


# ============================================================================
# Recovery Profile Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.recovery_profile
# ============================================================================

@case_management.post("/<int:resident_id>/recovery-profile")
@require_login
@require_shelter
def update_recovery_profile(resident_id: int):
    return update_recovery_profile_view(resident_id)


# ============================================================================
# Medication Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.medications
# ============================================================================

@case_management.get("/<int:resident_id>/medications")
@require_login
@require_shelter
def medications(resident_id: int):
    return medication_form_view(resident_id)


@case_management.post("/<int:resident_id>/medications")
@require_login
@require_shelter
def add_medication(resident_id: int):
    return add_medication_view(resident_id)


@case_management.route("/<int:resident_id>/medications/<int:medication_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_medication(resident_id: int, medication_id: int):
    return edit_medication_view(resident_id, medication_id)


# ============================================================================
# UA Log Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.ua_log
# ============================================================================

@case_management.get("/<int:resident_id>/ua-log")
@require_login
@require_shelter
def ua_log(resident_id: int):
    return ua_log_view(resident_id)


@case_management.post("/<int:resident_id>/ua-log")
@require_login
@require_shelter
def add_ua_log(resident_id: int):
    return add_ua_log_view(resident_id)


@case_management.route("/<int:resident_id>/ua-log/<int:ua_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_ua_log(resident_id: int, ua_id: int):
    return edit_ua_log_view(resident_id, ua_id)


# ============================================================================
# Inspection Log Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.inspection_log
# ============================================================================

@case_management.get("/<int:resident_id>/inspection-log")
@require_login
@require_shelter
def inspection_log(resident_id: int):
    return inspection_log_view(resident_id)


@case_management.post("/<int:resident_id>/inspection-log")
@require_login
@require_shelter
def add_inspection_log(resident_id: int):
    return add_inspection_log_view(resident_id)


@case_management.route("/<int:resident_id>/inspection-log/<int:inspection_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_inspection_log(resident_id: int, inspection_id: int):
    return edit_inspection_log_view(resident_id, inspection_id)


# ============================================================================
# Budget Session Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.budget_sessions
# ============================================================================

@case_management.get("/<int:resident_id>/budget-sessions")
@require_login
@require_shelter
def budget_sessions(resident_id: int):
    return budget_sessions_view(resident_id)


@case_management.post("/<int:resident_id>/budget-sessions")
@require_login
@require_shelter
def add_budget_session(resident_id: int):
    return add_budget_session_view(resident_id)


@case_management.route("/<int:resident_id>/budget-sessions/<int:budget_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_budget_session(resident_id: int, budget_id: int):
    return edit_budget_session_view(resident_id, budget_id)


# ============================================================================
# Case Manager Update Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.update
# ============================================================================

@case_management.post("/<int:resident_id>/case-notes")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    return add_case_note_view(resident_id)


@case_management.route("/<int:resident_id>/case-notes/<int:update_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_case_note(resident_id: int, update_id: int):
    return edit_case_note_view(resident_id, update_id)


@case_management.get("/<int:resident_id>/case-notes/<int:update_id>/print")
@require_login
@require_shelter
def progress_report_print(resident_id: int, update_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = _load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    note = _load_single_case_note(enrollment_id, update_id)
    if not note:
        flash("Case note not found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    goals = db_fetchall(
        f"""
        SELECT
            goal_text,
            status,
            target_date
        FROM goals
        WHERE enrollment_id = {ph}
        ORDER BY created_at DESC, id DESC
        """,
        (enrollment_id,),
    )

    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)
    case_manager_name = _load_case_manager_name(note.get("staff_user_id"))

    report = _build_progress_report_context(
        resident=resident,
        enrollment=enrollment,
        note=note,
        goals=goals,
        recovery_snapshot=recovery_snapshot,
        case_manager_name=case_manager_name,
    )

    return render_template(
        "case_management/progress_report_print_v2.html",
        report=report,
    )


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - START
# ----------------------------------------------------------------------------
# PURPOSE:
# This temporary admin only route wipes resident related test data so intake
# can be retested from a clean state during development.
#
# IMPORTANT:
# Delete everything from the START comment above to the END comment below after
# testing is complete. Do not leave this route in production long term.
#
# WHAT IT DELETES:
# - weekly_resident_summary
# - exit_assessments
# - followups
# - family_snapshots
# - intake_assessments
# - assessment_drafts
# - intake_drafts
# - case_manager_updates
# - appointments
# - goals
# - resident_form_submissions
# - resident_transfers
# - attendance_events
# - resident_passes
# - child_services
# - resident_children
# - resident_substances
# - client_services
# - resident_budget_sessions
# - resident_living_area_inspections
# - resident_ua_log
# - resident_medications
# - program_enrollments
# - residents
# ============================================================================
@case_management.route("/admin/wipe-test-residents", methods=["GET", "POST"])
@require_login
@require_shelter
def wipe_test_residents():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("case_management.index"))

    init_db()

    try:
        db_execute("DELETE FROM weekly_resident_summary")
        db_execute("DELETE FROM exit_assessments")
        db_execute("DELETE FROM followups")
        db_execute("DELETE FROM family_snapshots")
        db_execute("DELETE FROM intake_assessments")
        db_execute("DELETE FROM case_manager_updates")
        db_execute("DELETE FROM goals")
        db_execute("DELETE FROM appointments")
        db_execute("DELETE FROM resident_form_submissions")
        db_execute("DELETE FROM child_services")
        db_execute("DELETE FROM client_services")
        db_execute("DELETE FROM resident_budget_sessions")
        db_execute("DELETE FROM resident_living_area_inspections")
        db_execute("DELETE FROM resident_ua_log")
        db_execute("DELETE FROM resident_medications")

        db_execute("DELETE FROM assessment_drafts")
        db_execute("DELETE FROM intake_drafts")
        db_execute("DELETE FROM resident_transfers")
        db_execute("DELETE FROM attendance_events")
        db_execute("DELETE FROM resident_passes")
        db_execute("DELETE FROM resident_children")
        db_execute("DELETE FROM resident_substances")

        db_execute("DELETE FROM program_enrollments")
        db_execute("DELETE FROM residents")

        flash("All residents and resident related data were wiped.", "success")
    except Exception as e:
        flash(f"Wipe failed: {e}", "error")

    return redirect(url_for("case_management.index"))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - END
# ============================================================================


# ============================================================================
# Resident Case Page
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.resident_case
# ============================================================================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    return resident_case_view(resident_id)
