from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.attendance_hours import build_attendance_hours_snapshot
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.NP_placement_service import (
    PLACEMENT_TYPE_NONE,
    end_active_placement,
    get_active_placement,
    replace_active_placement,
)
from core.runtime import init_db
from routes.case_management_parts.budget_scoring import load_budget_score_snapshot
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.progress_report_loaders import load_case_manager_name
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_discipline import load_active_writeup_restrictions
from routes.case_management_parts.resident_case_employment import (
    build_employment_income_snapshot,
    build_employment_stability_snapshot,
    load_employment_income_defaults,
    resolve_employment_status_snapshot,
)
from routes.case_management_parts.resident_case_enrollment_context import load_enrollment_context
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)
from routes.case_management_parts.update_note_helpers import collect_note_form_values
from routes.inspection_v2 import build_inspection_stability_snapshot
from routes.rent_tracking import build_rent_stability_snapshot

_NOTE_INSERT_COLUMNS = (
    "enrollment_id",
    "staff_user_id",
    "meeting_date",
    "notes",
    "progress_notes",
    "setbacks_or_incidents",
    "action_items",
    "next_appointment",
    "overall_summary",
    "updated_grit",
    "parenting_class_completed",
    "warrants_or_fines_paid",
    "ready_for_next_level",
    "recommended_next_level",
    "blocker_reason",
    "override_or_exception",
    "staff_review_note",
    "created_at",
    "updated_at",
)


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _require_case_manager_access():
    if case_manager_allowed():
        return None
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None
    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        return None


def _none_if_blank(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _normalized_level_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _load_current_program_level(*, resident_id: int, shelter: str) -> str | None:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT program_level
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = LOWER({ph})
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    if not row:
        return None
    return _normalized_level_text(row.get("program_level"))


def _load_employment_income_settings(shelter: str) -> dict:
    ph = placeholder()
    defaults = load_employment_income_defaults()

    try:
        row = db_fetchone(
            f"""
            SELECT
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max
            FROM shelter_operation_settings
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
            LIMIT 1
            """,
            (shelter,),
        )
    except Exception:
        row = None

    if not row:
        return defaults

    resolved = dict(defaults)
    for key in resolved:
        if row.get(key) is not None:
            resolved[key] = row.get(key)
    return resolved


def _stable_snapshot(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _build_hard_blockers(
    *,
    blockers: list[str],
    has_disciplinary_block: bool,
    disciplinary_flags: list[str],
    rent_snapshot: dict | None,
    employment_income_snapshot: dict | None,
    employment_stability_snapshot: dict | None,
) -> list[str]:
    hard_blockers = list(blockers or [])

    if has_disciplinary_block and disciplinary_flags:
        hard_blockers.append("Active disciplinary restriction blocks promotion.")

    if rent_snapshot and not rent_snapshot.get("passes_graduation"):
        hard_blockers.append(
            f"Rent stability below graduation threshold of {rent_snapshot.get('graduation_target', 95)}."
        )

    if employment_income_snapshot and not employment_income_snapshot.get("meets_goal"):
        hard_blockers.append("Adjusted weighted income is below the graduation minimum.")

    if employment_stability_snapshot and not employment_stability_snapshot.get("passes"):
        hard_blockers.append("Employment stability is below the original job stability threshold.")

    seen: set[str] = set()
    deduped: list[str] = []
    for item in hard_blockers:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped


def _load_latest_promotion_review(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT
            id,
            meeting_date,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            notes,
            action_items,
            created_at,
            updated_at,
            staff_user_id
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND (
            ready_for_next_level IS NOT NULL
            OR COALESCE(recommended_next_level, '') <> ''
            OR COALESCE(blocker_reason, '') <> ''
            OR COALESCE(override_or_exception, '') <> ''
            OR COALESCE(staff_review_note, '') <> ''
            OR COALESCE(action_items, '') <> ''
          )
        ORDER BY meeting_date DESC, id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


def _load_promotion_audit_history(enrollment_id: int) -> list[dict[str, Any]]:
    ph = placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            id,
            meeting_date,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            notes,
            action_items,
            created_at,
            updated_at,
            staff_user_id
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND (
            ready_for_next_level IS NOT NULL
            OR COALESCE(recommended_next_level, '') <> ''
            OR COALESCE(blocker_reason, '') <> ''
            OR COALESCE(override_or_exception, '') <> ''
            OR COALESCE(staff_review_note, '') <> ''
            OR COALESCE(action_items, '') <> ''
          )
        ORDER BY COALESCE(meeting_date, '') DESC, id DESC
        """,
        (enrollment_id,),
    )

    history: list[dict[str, Any]] = []
    for row in rows or []:
        item = dict(row)
        item["staff_name"] = load_case_manager_name(item.get("staff_user_id"))
        action_text = str(item.get("action_items") or "")
        item["is_apply_action"] = "Applied promotion" in action_text
        history.append(item)
    return history


def _insert_promotion_review(
    *,
    enrollment_id: int,
    staff_user_id: int,
    values: dict[str, Any],
    now: str,
    action_items: str | None = None,
) -> int:
    ph = placeholder()
    insert_columns_sql = ",\n            ".join(_NOTE_INSERT_COLUMNS)
    values_sql = ",".join([ph] * len(_NOTE_INSERT_COLUMNS))
    row = db_fetchone(
        f"""
        INSERT INTO case_manager_updates
        (
            {insert_columns_sql}
        )
        VALUES ({values_sql})
        RETURNING id
        """,
        (
            enrollment_id,
            staff_user_id,
            values["meeting_date"],
            _none_if_blank(values["notes"]),
            None,
            _none_if_blank(values["setbacks_or_incidents"]),
            _none_if_blank(action_items),
            None,
            None,
            values["updated_grit"],
            values["parenting_class_completed"],
            values["warrants_or_fines_paid"],
            values["ready_for_next_level"],
            _none_if_blank(values["recommended_next_level"]),
            _none_if_blank(values["blocker_reason"]),
            _none_if_blank(values["override_or_exception"]),
            _none_if_blank(values["staff_review_note"]),
            now,
            now,
        ),
    )
    note_id = row.get("id") if row else None
    if not isinstance(note_id, int):
        raise RuntimeError("Promotion review insert returned invalid id")
    return note_id


def _apply_promotion_to_resident(*, resident_id: int, target_level: str, now: str) -> None:
    ph = placeholder()
    db_execute(
        f"""
        UPDATE residents
        SET
            program_level = {ph},
            level_start_date = {ph},
            step_changed_at = {ph}
        WHERE id = {ph}
        """,
        (
            target_level,
            now[:10],
            now,
            resident_id,
        ),
    )


def _active_rent_config_for_resident(*, resident_id: int, shelter: str) -> dict[str, Any] | None:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            id,
            level_snapshot,
            apartment_number_snapshot,
            apartment_size_snapshot,
            monthly_rent,
            is_exempt
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


def _sync_housing_for_promotion(
    *,
    resident_id: int,
    shelter: str,
    current_level: str | None,
    target_level: str,
    now: str,
) -> str | None:
    active_config = _active_rent_config_for_resident(
        resident_id=resident_id,
        shelter=shelter,
    )
    if not active_config:
        return None

    ph = placeholder()
    config_id = active_config.get("id")
    apartment_number = str(active_config.get("apartment_number_snapshot") or "").strip() or None

    if target_level == "9":
        db_execute(
            f"""
            UPDATE resident_rent_configs
            SET
                level_snapshot = {ph},
                effective_end_date = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                target_level,
                now[:10],
                now,
                config_id,
            ),
        )
        if apartment_number:
            return (
                f"Apartment {apartment_number} relinquished during promotion from level "
                f"{current_level or 'unknown'} to level 9."
            )
        return "Active DWC housing assignment relinquished during promotion to level 9."

    db_execute(
        f"""
        UPDATE resident_rent_configs
        SET
            level_snapshot = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            target_level,
            now,
            config_id,
        ),
    )
    return None


def _sync_placement_for_promotion(
    *,
    resident_id: int,
    enrollment_id: int,
    shelter: str,
    current_level: str | None,
    target_level: str,
    now: str,
) -> str | None:
    active_placement = get_active_placement(resident_id=resident_id, shelter=shelter)

    if target_level == "9":
        end_active_placement(
            resident_id=resident_id,
            shelter=shelter,
            end_date=now[:10],
            note="Placement ended at Level 9 planned exit boundary.",
            now=now,
        )
        return None

    replace_active_placement(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        shelter=shelter,
        program_level=target_level,
        housing_unit_id=(active_placement or {}).get("housing_unit_id"),
        placement_type=(active_placement or {}).get("placement_type") or PLACEMENT_TYPE_NONE,
        effective_date=now[:10],
        change_reason="promotion_level_change",
        note=f"Promotion from level {current_level or 'unknown'} to level {target_level}.",
        now=now,
    )
    return None


def promotion_review_view(resident_id: int):
    init_db()

    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    shelter = _current_shelter()
    resident = load_resident_in_scope(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = load_current_enrollment(resident_id, shelter)
    if not enrollment:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment.get("id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if request.method == "POST":
        staff_user_id = _current_staff_user_id()
        if staff_user_id is None:
            flash("Your session is missing a staff user id. Please log in again.", "error")
            return redirect(url_for("auth.staff_login"))

        form_action = (request.form.get("form_action") or "save_review").strip().lower()
        values = collect_note_form_values(request.form)
        if not values["meeting_date"]:
            flash("Review date is required.", "error")
            return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

        if form_action == "apply_promotion":
            confirmed = (request.form.get("confirm_apply_promotion") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            latest_review = _load_latest_promotion_review(enrollment_id)
            current_level = _load_current_program_level(
                resident_id=resident_id,
                shelter=shelter,
            )

            if not latest_review:
                flash("You must save a promotion review before applying promotion.", "error")
                return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

            target_level = _normalized_level_text(latest_review.get("recommended_next_level"))
            flash(f"DEBUG target_level={target_level!r}", "error")

            if not confirmed:
                flash("Confirm the promotion before applying it.", "error")
                return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

            if not target_level:
                flash("Latest review does not include a recommended next level.", "error")
                return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

            if current_level and target_level == current_level:
                flash("Recommended next level matches the resident's current level.", "error")
                return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

            now = utcnow_iso()
            action_items_parts = [
                f"Applied promotion from level {current_level or 'unknown'} to level {target_level}."
            ]
            apply_values = dict(values)
            apply_values["recommended_next_level"] = target_level
            try:
                with db_transaction():
                    _apply_promotion_to_resident(
                        resident_id=resident_id,
                        target_level=target_level,
                        now=now,
                    )
                    housing_action = _sync_housing_for_promotion(
                        resident_id=resident_id,
                        shelter=shelter,
                        current_level=current_level,
                        target_level=target_level,
                        now=now,
                    )
                    placement_action = _sync_placement_for_promotion(
                        resident_id=resident_id,
                        enrollment_id=enrollment_id,
                        shelter=shelter,
                        current_level=current_level,
                        target_level=target_level,
                        now=now,
                    )
                    if housing_action:
                        action_items_parts.append(housing_action)
                    if placement_action:
                        action_items_parts.append(placement_action)
                    if target_level == "9":
                        action_items_parts.append(
                            "Resident promoted to Level 9. Apartment released. Level 9 disposition required."
                        )
                    _insert_promotion_review(
                        enrollment_id=enrollment_id,
                        staff_user_id=staff_user_id,
                        values=apply_values,
                        now=now,
                        action_items=" ".join(action_items_parts),
                    )
            except Exception:
                flash("Unable to apply promotion. Please try again or contact an administrator.", "error")
                return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

            flash("Promotion applied and logged.", "success")

            actual_level = _load_current_program_level(
                resident_id=resident_id,
                shelter=shelter,
            )
            if actual_level == "9":
                return redirect(url_for("case_management.l9_disposition", resident_id=resident_id))

            return redirect(url_for("case_management.promotion_review", resident_id=resident_id, applied=1))

        if (
            values["ready_for_next_level"] is None
            and not values["recommended_next_level"]
            and not values["blocker_reason"]
            and not values["override_or_exception"]
            and not values["staff_review_note"]
            and not values["notes"]
            and not values["setbacks_or_incidents"]
        ):
            flash(
                "Enter a decision, rationale, blocker, exception, recommendation, or review summary.",
                "error",
            )
            return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

        now = utcnow_iso()
        try:
            with db_transaction():
                _insert_promotion_review(
                    enrollment_id=enrollment_id,
                    staff_user_id=staff_user_id,
                    values=values,
                    now=now,
                )
        except Exception:
            flash("Unable to save the promotion review. Please try again or contact an administrator.", "error")
            return redirect(url_for("case_management.promotion_review", resident_id=resident_id))

        flash("Promotion review saved.", "success")
        return redirect(url_for("case_management.promotion_review", resident_id=resident_id, saved=1))

    enrollment_context = load_enrollment_context(enrollment_id)
    recovery_snapshot = _stable_snapshot(load_recovery_snapshot(resident_id, enrollment_id))
    attendance_snapshot = _stable_snapshot(
        build_attendance_hours_snapshot(
            resident_id=resident_id,
            shelter=shelter,
            enrollment_entry_date=enrollment.get("entry_date"),
        )
    )
    inspection_snapshot = _stable_snapshot(build_inspection_stability_snapshot(resident_id, shelter=shelter))
    rent_snapshot = _stable_snapshot(build_rent_stability_snapshot(resident_id))
    disciplinary_flags = load_active_writeup_restrictions(resident_id)
    latest_review = _load_latest_promotion_review(enrollment_id)
    promotion_history = _load_promotion_audit_history(enrollment_id)
    budget_score_snapshot = _stable_snapshot(load_budget_score_snapshot(resident_id))

    employment_income_settings = _load_employment_income_settings(shelter)
    intake_income_support = enrollment_context.get("intake_income_support") or {}
    monthly_income_for_display = intake_income_support.get("weighted_stable_income")
    if monthly_income_for_display in (None, ""):
        monthly_income_for_display = intake_income_support.get("total_cash_support")
    if monthly_income_for_display in (None, ""):
        intake_assessment = enrollment_context.get("intake_assessment") or {}
        monthly_income_for_display = intake_assessment.get("income_at_entry")

    employment_income_snapshot = _stable_snapshot(
        build_employment_income_snapshot(
            monthly_income_for_display,
            employment_income_settings,
        )
    )
    employment_status_snapshot = resolve_employment_status_snapshot(
        recovery_snapshot,
        enrollment_context.get("intake_assessment"),
    )
    employment_stability_snapshot = _stable_snapshot(
        build_employment_stability_snapshot(
            recovery_snapshot,
            employment_status_snapshot=employment_status_snapshot,
        )
    )

    pr = recovery_snapshot.get("promotion_readiness") or {}
    hard_blockers = _build_hard_blockers(
        blockers=list(pr.get("blockers", []) or []),
        has_disciplinary_block=len(disciplinary_flags) > 0,
        disciplinary_flags=disciplinary_flags,
        rent_snapshot=rent_snapshot,
        employment_income_snapshot=employment_income_snapshot,
        employment_stability_snapshot=employment_stability_snapshot,
    )

    return render_template(
        "case_management/promotion_review.html",
        resident=resident,
        enrollment=enrollment,
        recovery_snapshot=recovery_snapshot,
        attendance_hours_snapshot=attendance_snapshot,
        inspection_snapshot=inspection_snapshot,
        rent_snapshot=rent_snapshot,
        employment_income_snapshot=employment_income_snapshot,
        employment_status_snapshot=employment_status_snapshot,
        employment_stability_snapshot=employment_stability_snapshot,
        disciplinary_flags=disciplinary_flags,
        has_disciplinary_block=len(disciplinary_flags) > 0,
        hard_blockers=hard_blockers,
        latest_review=latest_review,
        promotion_history=promotion_history,
        budget_score_snapshot=budget_score_snapshot,
        saved=request.args.get("saved") == "1",
        applied=request.args.get("applied") == "1",
    )
