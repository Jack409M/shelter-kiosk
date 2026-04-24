from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    AA_NA_PARENT_ACTIVITY_LABEL,
    LOCKED_PARENT_ACTIVITY_DEFINITIONS,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    VOLUNTEER_PARENT_ACTIVITY_LABEL,
    load_kiosk_activity_categories_for_shelter,
    load_kiosk_activity_child_options_for_shelter,
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
from routes.operations_settings_parts.employment_guidance import _employment_income_guidance
from routes.operations_settings_parts.employment_income_settings_controller import (
    save_employment_income_settings,
)
from routes.operations_settings_parts.inspection_settings_controller import (
    save_inspection_settings,
)
from routes.operations_settings_parts.kiosk_settings_controller import (
    handle_kiosk_settings_post,
    kiosk_child_section_parent_key,
)
from routes.operations_settings_parts.pass_settings_controller import save_pass_settings
from routes.operations_settings_parts.settings_store import (
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

SECTION_SAVE_HANDLERS = {
    "inspection_defaults": save_inspection_settings,
    "inspection_stability_scoring": save_inspection_settings,
    "inspection_color_bands": save_inspection_settings,
    "employment_income_graduation_settings": save_employment_income_settings,
    "employment_income_color_bands": save_employment_income_settings,
    "income_stability_weighting": save_employment_income_settings,
    "pass_general_rules": save_pass_settings,
    "pass_shared_house_rules": save_pass_settings,
    "pass_gratitude_house_rules": save_pass_settings,
}


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
    context["aa_na_parent_activity_key"] = AA_NA_PARENT_ACTIVITY_KEY
    context["aa_na_parent_activity_label"] = AA_NA_PARENT_ACTIVITY_LABEL
    context["volunteer_parent_activity_key"] = VOLUNTEER_PARENT_ACTIVITY_KEY
    context["volunteer_parent_activity_label"] = VOLUNTEER_PARENT_ACTIVITY_LABEL
    context["selected_kiosk_child_parent_key"] = ""
    context["selected_kiosk_child_parent_label"] = ""

    if current_section == "employment_income_guidance":
        context["employment_guidance"] = _employment_income_guidance(shelter, _placeholder())
    else:
        context["employment_guidance"] = None

    if current_section == "kiosk_activity_categories":
        context["kiosk_activity_categories"] = load_kiosk_activity_categories_for_shelter(shelter)
    else:
        context["kiosk_activity_categories"] = None

    child_parent_key = kiosk_child_section_parent_key(current_section)
    if child_parent_key:
        context["selected_kiosk_child_parent_key"] = child_parent_key
        context["selected_kiosk_child_parent_label"] = LOCKED_PARENT_ACTIVITY_DEFINITIONS[
            child_parent_key
        ]
        context["kiosk_activity_child_options"] = load_kiosk_activity_child_options_for_shelter(
            shelter,
            child_parent_key,
        )
    else:
        context["kiosk_activity_child_options"] = None

    return context


def _section_is_read_only(current_section: str) -> bool:
    return current_section == "employment_income_guidance"


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

        if _section_is_read_only(current_section):
            return redirect(
                url_for("operations_settings.settings_section_page", section_key=current_section)
            )

        kiosk_response = handle_kiosk_settings_post(shelter, current_section, form)
        if kiosk_response is not None:
            return kiosk_response

        handler = SECTION_SAVE_HANDLERS.get(current_section)
        if handler is None:
            flash("No save handler is configured for this section.", "error")
            return redirect(
                url_for("operations_settings.settings_section_page", section_key=current_section)
            )

        handler(shelter, row, form)

        flash(f"{current_section_meta['title']} updated.", "ok")
        return redirect(
            url_for("operations_settings.settings_section_page", section_key=current_section)
        )

    return render_template(
        "admin_operations_settings_section.html",
        **_build_settings_section_context(shelter, row, current_section),
    )
