from __future__ import annotations

from flask import flash, redirect, url_for

from core.kiosk_activity_categories import (
    LOCKED_PARENT_ACTIVITY_DEFINITIONS,
    reset_kiosk_activity_categories_for_shelter,
    reset_kiosk_activity_child_options_for_shelter,
    save_kiosk_activity_categories_for_shelter,
    save_kiosk_activity_child_options_for_shelter,
)


def kiosk_child_section_parent_key(current_section: str) -> str:
    prefix = "kiosk_child_options__"
    if not (current_section or "").startswith(prefix):
        return ""

    activity_key = (current_section or "")[len(prefix) :].strip()
    if activity_key in LOCKED_PARENT_ACTIVITY_DEFINITIONS:
        return activity_key

    return ""


def handle_kiosk_settings_post(shelter: str, current_section: str, form):
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

    child_parent_key = kiosk_child_section_parent_key(current_section)
    if child_parent_key:
        child_parent_label = LOCKED_PARENT_ACTIVITY_DEFINITIONS[child_parent_key]
        action = (form.get("kiosk_child_action") or "save").strip().lower()
        if action == "reset_defaults":
            reset_kiosk_activity_child_options_for_shelter(
                shelter,
                child_parent_key,
            )
            flash(f"{child_parent_label} Options reset to shelter defaults.", "ok")
        else:
            save_kiosk_activity_child_options_for_shelter(
                shelter,
                child_parent_key,
            )
            flash(f"{child_parent_label} Options updated.", "ok")

        return redirect(
            url_for("operations_settings.settings_section_page", section_key=current_section)
        )

    return None
