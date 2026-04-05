from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute
from core.helpers import utcnow_iso
from core.kiosk_activity_categories import (
    load_kiosk_activity_categories_for_shelter,
    reset_kiosk_activity_categories_for_shelter,
    save_kiosk_activity_categories_for_shelter,
)
from routes.operations_settings_parts.access import (
    _director_allowed,
    _normalize_shelter_name,
)
from routes.operations_settings_parts.config_sections import (
    _base_section_context,
    _configuration_section_map,
    _configuration_sections,
)
from routes.operations_settings_parts.employment_guidance import (
    _employment_income_guidance,
)
from routes.operations_settings_parts.parsing import (
    _merge_bool,
    _merge_float,
    _merge_int,
    _merge_text,
)
from routes.operations_settings_parts.settings_store import (
    _default_labels_text,
    _placeholder,
    _settings_row_for_shelter,
)

operations_settings = Blueprint(
    "operations_settings",
    __name__,
    url_prefix="/staff/admin/operations-settings",
)


def _build_settings_section_context(shelter: str, row, current_section: str) -> dict:
    context = _base_section_context(shelter, current_section)
    context["settings"] = row

    if current_section == "employment_income_guidance":
        context["employment_guidance"] = _employment_income_guidance(shelter, _placeholder())
    else:
        context["employment_guidance"] = None

    if current_section == "kiosk_activity_categories":
        context["kiosk_activity_categories"] = load_kiosk_activity_categories_for_shelter(shelter)
    else:
        context["kiosk_activity_categories"] = None

    return context


@operations_settings.route("", methods=["GET"])
@require_login
@require_shelter
def settings_page():
    if not _director_allowed(session):
        flash("Admin or shelter director access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    requested_section = (request.args.get("section") or "").strip().lower()
    section_map = _configuration_section_map()

    if requested_section in section_map:
        return redirect(
            url_for("operations_settings.settings_section_page", section_key=requested_section)
        )

    return render_template(
        "admin_operations_settings.html",
        shelter=shelter,
        sections=_configuration_sections(),
    )


@operations_settings.route("/<section_key>", methods=["GET", "POST"])
@require_login
@require_shelter
def settings_section_page(section_key: str):
    if not _director_allowed(session):
        flash("Admin or shelter director access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    row = _settings_row_for_shelter(shelter)
    section_map = _configuration_section_map()
    current_section = (section_key or "").strip().lower()

    if current_section not in section_map:
        flash("Configuration section not found.", "error")
        return redirect(url_for("operations_settings.settings_page"))

    current_section_meta = section_map[current_section]

    if request.method == "POST":
        form = request.form

        if current_section == "employment_income_guidance":
            return redirect(
                url_for("operations_settings.settings_section_page", section_key=current_section)
            )

        if current_section == "kiosk_activity_categories":
            action = (form.get("kiosk_action") or "save").strip().lower()
            if action == "reset_defaults":
                reset_kiosk_activity_categories_for_shelter(shelter)
                flash("Kiosk Activity Categories reset to shelter defaults.", "ok")
            else:
                save_kiosk_activity_categories_for_shelter(shelter)
                flash("Kiosk Activity Categories updated.", "ok")

            return redirect(
                url_for("operations_settings.settings_section_page", section_key=current_section)
            )

        now = utcnow_iso()
        is_pg = _placeholder() == "%s"
        default_inspection_items = _default_labels_text()

        late_day = min(
            max(
                _merge_int(
                    "rent_late_day_of_month",
                    form,
                    row.get("rent_late_day_of_month"),
                    6,
                ),
                1,
            ),
            28,
        )
        carry_forward_enabled = _merge_bool(
            "rent_carry_forward_enabled",
            form,
            row.get("rent_carry_forward_enabled"),
            True,
        )

        inspection_default_item_status = _merge_text(
            "inspection_default_item_status",
            form,
            row.get("inspection_default_item_status"),
            "passed",
        ).lower()
        if inspection_default_item_status not in {"passed", "needs_attention", "failed"}:
            inspection_default_item_status = "passed"

        inspection_item_labels = _merge_text(
            "inspection_item_labels",
            form,
            row.get("inspection_item_labels"),
            default_inspection_items,
        ) or default_inspection_items

        rent_score_paid = _merge_int("rent_score_paid", form, row.get("rent_score_paid"), 100)
        rent_score_partially_paid = _merge_int(
            "rent_score_partially_paid",
            form,
            row.get("rent_score_partially_paid"),
            75,
        )
        rent_score_paid_late = _merge_int(
            "rent_score_paid_late",
            form,
            row.get("rent_score_paid_late"),
            75,
        )
        rent_score_not_paid = _merge_int(
            "rent_score_not_paid",
            form,
            row.get("rent_score_not_paid"),
            0,
        )
        rent_score_exempt = _merge_int(
            "rent_score_exempt",
            form,
            row.get("rent_score_exempt"),
            100,
        )

        inspection_scoring_enabled = _merge_bool(
            "inspection_scoring_enabled",
            form,
            row.get("inspection_scoring_enabled"),
            True,
        )
        inspection_lookback_months = max(
            _merge_int(
                "inspection_lookback_months",
                form,
                row.get("inspection_lookback_months"),
                9,
            ),
            1,
        )
        inspection_include_current_open_month = _merge_bool(
            "inspection_include_current_open_month",
            form,
            row.get("inspection_include_current_open_month"),
            False,
        )
        inspection_score_passed = _merge_int(
            "inspection_score_passed",
            form,
            row.get("inspection_score_passed"),
            100,
        )
        inspection_needs_attention_enabled = _merge_bool(
            "inspection_needs_attention_enabled",
            form,
            row.get("inspection_needs_attention_enabled"),
            False,
        )
        inspection_score_needs_attention = _merge_int(
            "inspection_score_needs_attention",
            form,
            row.get("inspection_score_needs_attention"),
            70,
        )
        inspection_score_failed = _merge_int(
            "inspection_score_failed",
            form,
            row.get("inspection_score_failed"),
            0,
        )
        inspection_passing_threshold = _merge_int(
            "inspection_passing_threshold",
            form,
            row.get("inspection_passing_threshold"),
            83,
        )
        inspection_band_green_min = _merge_int(
            "inspection_band_green_min",
            form,
            row.get("inspection_band_green_min"),
            83,
        )
        inspection_band_yellow_min = _merge_int(
            "inspection_band_yellow_min",
            form,
            row.get("inspection_band_yellow_min"),
            78,
        )
        inspection_band_orange_min = _merge_int(
            "inspection_band_orange_min",
            form,
            row.get("inspection_band_orange_min"),
            56,
        )
        inspection_band_red_max = _merge_int(
            "inspection_band_red_max",
            form,
            row.get("inspection_band_red_max"),
            55,
        )

        if inspection_band_green_min < inspection_band_yellow_min:
            inspection_band_green_min = inspection_band_yellow_min + 1
        if inspection_band_yellow_min < inspection_band_orange_min:
            inspection_band_yellow_min = inspection_band_orange_min + 1
        if inspection_band_red_max >= inspection_band_orange_min:
            inspection_band_red_max = inspection_band_orange_min - 1

        employment_income_module_enabled = _merge_bool(
            "employment_income_module_enabled",
            form,
            row.get("employment_income_module_enabled"),
            True,
        )
        employment_income_graduation_minimum = _merge_float(
            "employment_income_graduation_minimum",
            form,
            row.get("employment_income_graduation_minimum"),
            1200.00,
        )
        employment_income_band_green_min = _merge_float(
            "employment_income_band_green_min",
            form,
            row.get("employment_income_band_green_min"),
            1200.00,
        )
        employment_income_band_yellow_min = _merge_float(
            "employment_income_band_yellow_min",
            form,
            row.get("employment_income_band_yellow_min"),
            1000.00,
        )
        employment_income_band_orange_min = _merge_float(
            "employment_income_band_orange_min",
            form,
            row.get("employment_income_band_orange_min"),
            700.00,
        )
        employment_income_band_red_max = _merge_float(
            "employment_income_band_red_max",
            form,
            row.get("employment_income_band_red_max"),
            699.99,
        )

        if employment_income_band_green_min < employment_income_band_yellow_min:
            employment_income_band_green_min = employment_income_band_yellow_min + 0.01
        if employment_income_band_yellow_min < employment_income_band_orange_min:
            employment_income_band_yellow_min = employment_income_band_orange_min + 0.01
        if employment_income_band_red_max >= employment_income_band_orange_min:
            employment_income_band_red_max = employment_income_band_orange_min - 0.01

        income_weight_employment = max(
            _merge_float(
                "income_weight_employment",
                form,
                row.get("income_weight_employment"),
                1.00,
            ),
            0.0,
        )
        income_weight_ssi_ssdi_self = max(
            _merge_float(
                "income_weight_ssi_ssdi_self",
                form,
                row.get("income_weight_ssi_ssdi_self"),
                1.00,
            ),
            0.0,
        )
        income_weight_tanf = max(
            _merge_float(
                "income_weight_tanf",
                form,
                row.get("income_weight_tanf"),
                1.00,
            ),
            0.0,
        )
        income_weight_alimony = max(
            _merge_float(
                "income_weight_alimony",
                form,
                row.get("income_weight_alimony"),
                0.50,
            ),
            0.0,
        )
        income_weight_other_income = max(
            _merge_float(
                "income_weight_other_income",
                form,
                row.get("income_weight_other_income"),
                0.25,
            ),
            0.0,
        )
        income_weight_survivor_cutoff_months = max(
            _merge_int(
                "income_weight_survivor_cutoff_months",
                form,
                row.get("income_weight_survivor_cutoff_months"),
                18,
            ),
            0,
        )

        db_execute(
            """
            UPDATE shelter_operation_settings
            SET rent_late_day_of_month = %s,
                rent_score_paid = %s,
                rent_score_partially_paid = %s,
                rent_score_paid_late = %s,
                rent_score_not_paid = %s,
                rent_score_exempt = %s,
                rent_carry_forward_enabled = %s,
                inspection_default_item_status = %s,
                inspection_item_labels = %s,
                inspection_scoring_enabled = %s,
                inspection_lookback_months = %s,
                inspection_include_current_open_month = %s,
                inspection_score_passed = %s,
                inspection_needs_attention_enabled = %s,
                inspection_score_needs_attention = %s,
                inspection_score_failed = %s,
                inspection_passing_threshold = %s,
                inspection_band_green_min = %s,
                inspection_band_yellow_min = %s,
                inspection_band_orange_min = %s,
                inspection_band_red_max = %s,
                employment_income_module_enabled = %s,
                employment_income_graduation_minimum = %s,
                employment_income_band_green_min = %s,
                employment_income_band_yellow_min = %s,
                employment_income_band_orange_min = %s,
                employment_income_band_red_max = %s,
                income_weight_employment = %s,
                income_weight_ssi_ssdi_self = %s,
                income_weight_tanf = %s,
                income_weight_alimony = %s,
                income_weight_other_income = %s,
                income_weight_survivor_cutoff_months = %s,
                updated_at = %s
            WHERE LOWER(COALESCE(shelter, '')) = %s
            """
            if is_pg
            else
            """
            UPDATE shelter_operation_settings
            SET rent_late_day_of_month = ?,
                rent_score_paid = ?,
                rent_score_partially_paid = ?,
                rent_score_paid_late = ?,
                rent_score_not_paid = ?,
                rent_score_exempt = ?,
                rent_carry_forward_enabled = ?,
                inspection_default_item_status = ?,
                inspection_item_labels = ?,
                inspection_scoring_enabled = ?,
                inspection_lookback_months = ?,
                inspection_include_current_open_month = ?,
                inspection_score_passed = ?,
                inspection_needs_attention_enabled = ?,
                inspection_score_needs_attention = ?,
                inspection_score_failed = ?,
                inspection_passing_threshold = ?,
                inspection_band_green_min = ?,
                inspection_band_yellow_min = ?,
                inspection_band_orange_min = ?,
                inspection_band_red_max = ?,
                employment_income_module_enabled = ?,
                employment_income_graduation_minimum = ?,
                employment_income_band_green_min = ?,
                employment_income_band_yellow_min = ?,
                employment_income_band_orange_min = ?,
                employment_income_band_red_max = ?,
                income_weight_employment = ?,
                income_weight_ssi_ssdi_self = ?,
                income_weight_tanf = ?,
                income_weight_alimony = ?,
                income_weight_other_income = ?,
                income_weight_survivor_cutoff_months = ?,
                updated_at = ?
            WHERE LOWER(COALESCE(shelter, '')) = ?
            """,
            (
                late_day,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                carry_forward_enabled if is_pg else (1 if carry_forward_enabled else 0),
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled if is_pg else (1 if inspection_scoring_enabled else 0),
                inspection_lookback_months,
                inspection_include_current_open_month if is_pg else (1 if inspection_include_current_open_month else 0),
                inspection_score_passed,
                inspection_needs_attention_enabled if is_pg else (1 if inspection_needs_attention_enabled else 0),
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled if is_pg else (1 if employment_income_module_enabled else 0),
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_tanf,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                now,
                shelter,
            ),
        )

        flash(f"{current_section_meta['title']} updated.", "ok")
        return redirect(
            url_for("operations_settings.settings_section_page", section_key=current_section)
        )

    return render_template(
        "admin_operations_settings_section.html",
        **_build_settings_section_context(shelter, row, current_section),
    )
