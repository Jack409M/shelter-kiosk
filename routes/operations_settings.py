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
    _default_pass_gh_rules_text,
    _default_pass_level_rules_text,
    _default_pass_shared_rules_text,
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
    context["default_pass_shared_rules_text"] = _default_pass_shared_rules_text()
    context["default_pass_gh_rules_text"] = _default_pass_gh_rules_text()
    context["default_pass_level_1_rules_text"] = _default_pass_level_rules_text("pass_level_1_rules_text")
    context["default_pass_level_2_rules_text"] = _default_pass_level_rules_text("pass_level_2_rules_text")
    context["default_pass_level_3_rules_text"] = _default_pass_level_rules_text("pass_level_3_rules_text")
    context["default_pass_level_4_rules_text"] = _default_pass_level_rules_text("pass_level_4_rules_text")
    context["default_pass_gh_level_5_rules_text"] = _default_pass_level_rules_text("pass_gh_level_5_rules_text")
    context["default_pass_gh_level_6_rules_text"] = _default_pass_level_rules_text("pass_gh_level_6_rules_text")
    context["default_pass_gh_level_7_rules_text"] = _default_pass_level_rules_text("pass_gh_level_7_rules_text")
    context["default_pass_gh_level_8_rules_text"] = _default_pass_level_rules_text("pass_gh_level_8_rules_text")

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
    current_section_type = (current_section_meta.get("type") or "form").strip().lower()

    if current_section_type == "group":
        if request.method == "POST":
            flash("This page is a menu only.", "error")
            return redirect(
                url_for("operations_settings.settings_section_page", section_key=current_section)
            )

        return render_template(
            "admin_operations_settings_section.html",
            **_build_settings_section_context(shelter, row, current_section),
        )

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

        hh_rent_amount = max(
            _merge_float(
                "hh_rent_amount",
                form,
                row.get("hh_rent_amount"),
                150.00,
            ),
            0.0,
        )
        hh_rent_due_day = min(
            max(
                _merge_int(
                    "hh_rent_due_day",
                    form,
                    row.get("hh_rent_due_day"),
                    1,
                ),
                1,
            ),
            28,
        )
        hh_rent_late_day = min(
            max(
                _merge_int(
                    "hh_rent_late_day",
                    form,
                    row.get("hh_rent_late_day"),
                    5,
                ),
                1,
            ),
            28,
        )
        hh_rent_late_fee_per_day = max(
            _merge_float(
                "hh_rent_late_fee_per_day",
                form,
                row.get("hh_rent_late_fee_per_day"),
                1.00,
            ),
            0.0,
        )
        hh_late_arrangement_required = _merge_bool(
            "hh_late_arrangement_required",
            form,
            row.get("hh_late_arrangement_required"),
            True,
        )
        hh_payment_methods_text = _merge_text(
            "hh_payment_methods_text",
            form,
            row.get("hh_payment_methods_text"),
            "Money order\nCashier check",
        ) or "Money order\nCashier check"
        hh_payment_accepted_by_roles_text = _merge_text(
            "hh_payment_accepted_by_roles_text",
            form,
            row.get("hh_payment_accepted_by_roles_text"),
            "Case managers only",
        ) or "Case managers only"
        hh_work_off_enabled = _merge_bool(
            "hh_work_off_enabled",
            form,
            row.get("hh_work_off_enabled"),
            True,
        )
        hh_work_off_hourly_rate = max(
            _merge_float(
                "hh_work_off_hourly_rate",
                form,
                row.get("hh_work_off_hourly_rate"),
                10.00,
            ),
            0.0,
        )
        hh_work_off_required_hours = max(
            _merge_int(
                "hh_work_off_required_hours",
                form,
                row.get("hh_work_off_required_hours"),
                15,
            ),
            0,
        )
        hh_work_off_deadline_day = min(
            max(
                _merge_int(
                    "hh_work_off_deadline_day",
                    form,
                    row.get("hh_work_off_deadline_day"),
                    10,
                ),
                1,
            ),
            28,
        )
        hh_work_off_location_text = _merge_text(
            "hh_work_off_location_text",
            form,
            row.get("hh_work_off_location_text"),
            "Thrift City",
        ) or "Thrift City"
        hh_work_off_notes_text = _merge_text(
            "hh_work_off_notes_text",
            form,
            row.get("hh_work_off_notes_text"),
            "If unemployed, resident may work off rent at 10 dollars per hour. Hours must be completed by the 10th unless arrangements are made in advance.",
        ) or "If unemployed, resident may work off rent at 10 dollars per hour. Hours must be completed by the 10th unless arrangements are made in advance."

        gh_rent_due_day = min(
            max(
                _merge_int(
                    "gh_rent_due_day",
                    form,
                    row.get("gh_rent_due_day"),
                    1,
                ),
                1,
            ),
            28,
        )
        gh_rent_late_fee_per_day = max(
            _merge_float(
                "gh_rent_late_fee_per_day",
                form,
                row.get("gh_rent_late_fee_per_day"),
                1.00,
            ),
            0.0,
        )
        gh_late_arrangement_required = _merge_bool(
            "gh_late_arrangement_required",
            form,
            row.get("gh_late_arrangement_required"),
            True,
        )
        gh_level_5_one_bedroom_rent = max(
            _merge_float(
                "gh_level_5_one_bedroom_rent",
                form,
                row.get("gh_level_5_one_bedroom_rent"),
                250.00,
            ),
            0.0,
        )
        gh_level_5_two_bedroom_rent = max(
            _merge_float(
                "gh_level_5_two_bedroom_rent",
                form,
                row.get("gh_level_5_two_bedroom_rent"),
                300.00,
            ),
            0.0,
        )
        gh_level_5_townhome_rent = max(
            _merge_float(
                "gh_level_5_townhome_rent",
                form,
                row.get("gh_level_5_townhome_rent"),
                300.00,
            ),
            0.0,
        )
        gh_level_8_sliding_scale_enabled = _merge_bool(
            "gh_level_8_sliding_scale_enabled",
            form,
            row.get("gh_level_8_sliding_scale_enabled"),
            True,
        )
        gh_level_8_sliding_scale_basis_text = _merge_text(
            "gh_level_8_sliding_scale_basis_text",
            form,
            row.get("gh_level_8_sliding_scale_basis_text"),
            "Sliding scale based on income, household size, and accepted expenses.",
        ) or "Sliding scale based on income, household size, and accepted expenses."
        gh_level_8_first_increase_amount = max(
            _merge_float(
                "gh_level_8_first_increase_amount",
                form,
                row.get("gh_level_8_first_increase_amount"),
                50.00,
            ),
            0.0,
        )
        gh_level_8_second_increase_amount = max(
            _merge_float(
                "gh_level_8_second_increase_amount",
                form,
                row.get("gh_level_8_second_increase_amount"),
                50.00,
            ),
            0.0,
        )
        gh_level_8_increase_schedule_text = _merge_text(
            "gh_level_8_increase_schedule_text",
            form,
            row.get("gh_level_8_increase_schedule_text"),
            "Increase a minimum of 50 the month after graduation, then another 50 one year later.",
        ) or "Increase a minimum of 50 the month after graduation, then another 50 one year later."

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

        pass_deadline_weekday = min(
            max(
                _merge_int(
                    "pass_deadline_weekday",
                    form,
                    row.get("pass_deadline_weekday"),
                    0,
                ),
                0,
            ),
            6,
        )
        pass_deadline_hour = min(
            max(
                _merge_int(
                    "pass_deadline_hour",
                    form,
                    row.get("pass_deadline_hour"),
                    8,
                ),
                0,
            ),
            23,
        )
        pass_deadline_minute = min(
            max(
                _merge_int(
                    "pass_deadline_minute",
                    form,
                    row.get("pass_deadline_minute"),
                    0,
                ),
                0,
            ),
            59,
        )
        pass_late_submission_block_enabled = _merge_bool(
            "pass_late_submission_block_enabled",
            form,
            row.get("pass_late_submission_block_enabled"),
            True,
        )
        pass_work_required_hours = max(
            _merge_int(
                "pass_work_required_hours",
                form,
                row.get("pass_work_required_hours"),
                29,
            ),
            0,
        )
        pass_productive_required_hours = max(
            _merge_int(
                "pass_productive_required_hours",
                form,
                row.get("pass_productive_required_hours"),
                35,
            ),
            0,
        )
        special_pass_bypass_hours_enabled = _merge_bool(
            "special_pass_bypass_hours_enabled",
            form,
            row.get("special_pass_bypass_hours_enabled"),
            True,
        )

        pass_shared_rules_text = _merge_text(
            "pass_shared_rules_text",
            form,
            row.get("pass_shared_rules_text"),
            _default_pass_shared_rules_text(),
        ) or _default_pass_shared_rules_text()

        pass_gh_rules_text = _merge_text(
            "pass_gh_rules_text",
            form,
            row.get("pass_gh_rules_text"),
            _default_pass_gh_rules_text(),
        ) or _default_pass_gh_rules_text()

        pass_level_1_rules_text = _merge_text(
            "pass_level_1_rules_text",
            form,
            row.get("pass_level_1_rules_text"),
            _default_pass_level_rules_text("pass_level_1_rules_text"),
        ) or _default_pass_level_rules_text("pass_level_1_rules_text")

        pass_level_2_rules_text = _merge_text(
            "pass_level_2_rules_text",
            form,
            row.get("pass_level_2_rules_text"),
            _default_pass_level_rules_text("pass_level_2_rules_text"),
        ) or _default_pass_level_rules_text("pass_level_2_rules_text")

        pass_level_3_rules_text = _merge_text(
            "pass_level_3_rules_text",
            form,
            row.get("pass_level_3_rules_text"),
            _default_pass_level_rules_text("pass_level_3_rules_text"),
        ) or _default_pass_level_rules_text("pass_level_3_rules_text")

        pass_level_4_rules_text = _merge_text(
            "pass_level_4_rules_text",
            form,
            row.get("pass_level_4_rules_text"),
            _default_pass_level_rules_text("pass_level_4_rules_text"),
        ) or _default_pass_level_rules_text("pass_level_4_rules_text")

        pass_gh_level_5_rules_text = _merge_text(
            "pass_gh_level_5_rules_text",
            form,
            row.get("pass_gh_level_5_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_5_rules_text"),
        ) or _default_pass_level_rules_text("pass_gh_level_5_rules_text")

        pass_gh_level_6_rules_text = _merge_text(
            "pass_gh_level_6_rules_text",
            form,
            row.get("pass_gh_level_6_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_6_rules_text"),
        ) or _default_pass_level_rules_text("pass_gh_level_6_rules_text")

        pass_gh_level_7_rules_text = _merge_text(
            "pass_gh_level_7_rules_text",
            form,
            row.get("pass_gh_level_7_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_7_rules_text"),
        ) or _default_pass_level_rules_text("pass_gh_level_7_rules_text")

        pass_gh_level_8_rules_text = _merge_text(
            "pass_gh_level_8_rules_text",
            form,
            row.get("pass_gh_level_8_rules_text"),
            _default_pass_level_rules_text("pass_gh_level_8_rules_text"),
        ) or _default_pass_level_rules_text("pass_gh_level_8_rules_text")

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
                hh_rent_amount = %s,
                hh_rent_due_day = %s,
                hh_rent_late_day = %s,
                hh_rent_late_fee_per_day = %s,
                hh_late_arrangement_required = %s,
                hh_payment_methods_text = %s,
                hh_payment_accepted_by_roles_text = %s,
                hh_work_off_enabled = %s,
                hh_work_off_hourly_rate = %s,
                hh_work_off_required_hours = %s,
                hh_work_off_deadline_day = %s,
                hh_work_off_location_text = %s,
                hh_work_off_notes_text = %s,
                gh_rent_due_day = %s,
                gh_rent_late_fee_per_day = %s,
                gh_late_arrangement_required = %s,
                gh_level_5_one_bedroom_rent = %s,
                gh_level_5_two_bedroom_rent = %s,
                gh_level_5_townhome_rent = %s,
                gh_level_8_sliding_scale_enabled = %s,
                gh_level_8_sliding_scale_basis_text = %s,
                gh_level_8_first_increase_amount = %s,
                gh_level_8_second_increase_amount = %s,
                gh_level_8_increase_schedule_text = %s,
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
                pass_deadline_weekday = %s,
                pass_deadline_hour = %s,
                pass_deadline_minute = %s,
                pass_late_submission_block_enabled = %s,
                pass_work_required_hours = %s,
                pass_productive_required_hours = %s,
                special_pass_bypass_hours_enabled = %s,
                pass_shared_rules_text = %s,
                pass_gh_rules_text = %s,
                pass_level_1_rules_text = %s,
                pass_level_2_rules_text = %s,
                pass_level_3_rules_text = %s,
                pass_level_4_rules_text = %s,
                pass_gh_level_5_rules_text = %s,
                pass_gh_level_6_rules_text = %s,
                pass_gh_level_7_rules_text = %s,
                pass_gh_level_8_rules_text = %s,
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
                hh_rent_amount = ?,
                hh_rent_due_day = ?,
                hh_rent_late_day = ?,
                hh_rent_late_fee_per_day = ?,
                hh_late_arrangement_required = ?,
                hh_payment_methods_text = ?,
                hh_payment_accepted_by_roles_text = ?,
                hh_work_off_enabled = ?,
                hh_work_off_hourly_rate = ?,
                hh_work_off_required_hours = ?,
                hh_work_off_deadline_day = ?,
                hh_work_off_location_text = ?,
                hh_work_off_notes_text = ?,
                gh_rent_due_day = ?,
                gh_rent_late_fee_per_day = ?,
                gh_late_arrangement_required = ?,
                gh_level_5_one_bedroom_rent = ?,
                gh_level_5_two_bedroom_rent = ?,
                gh_level_5_townhome_rent = ?,
                gh_level_8_sliding_scale_enabled = ?,
                gh_level_8_sliding_scale_basis_text = ?,
                gh_level_8_first_increase_amount = ?,
                gh_level_8_second_increase_amount = ?,
                gh_level_8_increase_schedule_text = ?,
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
                pass_deadline_weekday = ?,
                pass_deadline_hour = ?,
                pass_deadline_minute = ?,
                pass_late_submission_block_enabled = ?,
                pass_work_required_hours = ?,
                pass_productive_required_hours = ?,
                special_pass_bypass_hours_enabled = ?,
                pass_shared_rules_text = ?,
                pass_gh_rules_text = ?,
                pass_level_1_rules_text = ?,
                pass_level_2_rules_text = ?,
                pass_level_3_rules_text = ?,
                pass_level_4_rules_text = ?,
                pass_gh_level_5_rules_text = ?,
                pass_gh_level_6_rules_text = ?,
                pass_gh_level_7_rules_text = ?,
                pass_gh_level_8_rules_text = ?,
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
                hh_rent_amount,
                hh_rent_due_day,
                hh_rent_late_day,
                hh_rent_late_fee_per_day,
                hh_late_arrangement_required if is_pg else (1 if hh_late_arrangement_required else 0),
                hh_payment_methods_text,
                hh_payment_accepted_by_roles_text,
                hh_work_off_enabled if is_pg else (1 if hh_work_off_enabled else 0),
                hh_work_off_hourly_rate,
                hh_work_off_required_hours,
                hh_work_off_deadline_day,
                hh_work_off_location_text,
                hh_work_off_notes_text,
                gh_rent_due_day,
                gh_rent_late_fee_per_day,
                gh_late_arrangement_required if is_pg else (1 if gh_late_arrangement_required else 0),
                gh_level_5_one_bedroom_rent,
                gh_level_5_two_bedroom_rent,
                gh_level_5_townhome_rent,
                gh_level_8_sliding_scale_enabled if is_pg else (1 if gh_level_8_sliding_scale_enabled else 0),
                gh_level_8_sliding_scale_basis_text,
                gh_level_8_first_increase_amount,
                gh_level_8_second_increase_amount,
                gh_level_8_increase_schedule_text,
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
                pass_deadline_weekday,
                pass_deadline_hour,
                pass_deadline_minute,
                pass_late_submission_block_enabled if is_pg else (1 if pass_late_submission_block_enabled else 0),
                pass_work_required_hours,
                pass_productive_required_hours,
                special_pass_bypass_hours_enabled if is_pg else (1 if special_pass_bypass_hours_enabled else 0),
                pass_shared_rules_text,
                pass_gh_rules_text,
                pass_level_1_rules_text,
                pass_level_2_rules_text,
                pass_level_3_rules_text,
                pass_level_4_rules_text,
                pass_gh_level_5_rules_text,
                pass_gh_level_6_rules_text,
                pass_gh_level_7_rules_text,
                pass_gh_level_8_rules_text,
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
