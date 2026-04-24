from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_transaction
from core.helpers import utcnow_iso
from routes.operations_settings_parts.access import (
    _director_allowed,
    _normalize_shelter_name,
)
from routes.rent_tracking_parts.RR_rent_config import (
    EDITABLE_UNIT_TYPES,
    UNIT_TYPE_FLAT,
    UNIT_TYPE_ONE_BEDROOM,
    UNIT_TYPE_TOWNHOME,
    UNIT_TYPE_TWO_BEDROOM,
    load_rr_rent_policy,
    load_rr_rent_rules,
    seed_default_rr_rent_config,
    unit_type_label,
)
from routes.rent_tracking_parts.utils import _float_value

RR_rent_admin = Blueprint(
    "RR_rent_admin",
    __name__,
    url_prefix="/staff/admin/rr-rent-config",
)

RULE_GROUPS = (
    {
        "title": "Levels 1 Through 4",
        "summary": "Flat rent amounts that do not depend on apartment type.",
        "rows": (
            ("1", UNIT_TYPE_FLAT),
            ("2", UNIT_TYPE_FLAT),
            ("3", UNIT_TYPE_FLAT),
            ("4", UNIT_TYPE_FLAT),
        ),
    },
    {
        "title": "Level 5",
        "summary": "Rent by apartment type.",
        "rows": (
            ("5", UNIT_TYPE_ONE_BEDROOM),
            ("5", UNIT_TYPE_TWO_BEDROOM),
            ("5", UNIT_TYPE_TOWNHOME),
        ),
    },
    {
        "title": "Level 6",
        "summary": "Rent by apartment type.",
        "rows": (
            ("6", UNIT_TYPE_ONE_BEDROOM),
            ("6", UNIT_TYPE_TWO_BEDROOM),
            ("6", UNIT_TYPE_TOWNHOME),
        ),
    },
    {
        "title": "Level 7",
        "summary": "Rent by apartment type.",
        "rows": (
            ("7", UNIT_TYPE_ONE_BEDROOM),
            ("7", UNIT_TYPE_TWO_BEDROOM),
            ("7", UNIT_TYPE_TOWNHOME),
        ),
    },
    {
        "title": "Level 8 Minimums",
        "summary": "Minimum rent by apartment type. Resident level 8 adjustments cannot go below these amounts.",
        "rows": (
            ("8", UNIT_TYPE_ONE_BEDROOM),
            ("8", UNIT_TYPE_TWO_BEDROOM),
            ("8", UNIT_TYPE_TOWNHOME),
        ),
    },
)


def _bool_for_db(value: bool):
    return value if g.get("db_kind") == "pg" else (1 if value else 0)


def _clamped_day(value: object, default: int) -> int:
    try:
        parsed = int(str(value or default).strip())
    except Exception:
        parsed = default
    return min(max(parsed, 1), 28)


def _money_from_form(name: str, default: float = 0.0) -> float:
    return max(round(_float_value(request.form.get(name) or default), 2), 0.0)


def _text_from_form(name: str, default: str = "") -> str:
    return (request.form.get(name) or default or "").strip()


def _rule_field_name(program_level: str, unit_type: str) -> str:
    return f"rent__{program_level}__{unit_type}"


def _rules_by_key(shelter: str) -> dict[tuple[str, str], dict]:
    return {
        (rule.program_level, rule.unit_type): {
            "program_level": rule.program_level,
            "unit_type": rule.unit_type,
            "monthly_rent": rule.monthly_rent,
            "is_minimum": rule.is_minimum,
            "is_active": rule.is_active,
            "field_name": _rule_field_name(rule.program_level, rule.unit_type),
            "unit_type_label": unit_type_label(rule.unit_type),
        }
        for rule in load_rr_rent_rules(shelter)
    }


def _grouped_rules(shelter: str) -> list[dict]:
    rules = _rules_by_key(shelter)
    grouped: list[dict] = []

    for group in RULE_GROUPS:
        group_rows: list[dict] = []
        for program_level, unit_type in group["rows"]:
            row = rules.get((program_level, unit_type)) or {
                "program_level": program_level,
                "unit_type": unit_type,
                "monthly_rent": 0.0,
                "is_minimum": program_level == "8",
                "is_active": True,
                "field_name": _rule_field_name(program_level, unit_type),
                "unit_type_label": unit_type_label(unit_type),
            }
            group_rows.append(row)

        grouped.append(
            {
                "title": group["title"],
                "summary": group["summary"],
                "rows": group_rows,
            }
        )

    return grouped


def _update_rule(
    *,
    shelter: str,
    program_level: str,
    unit_type: str,
    monthly_rent: float,
    is_minimum: bool,
) -> None:
    now = utcnow_iso()

    db_execute(
        (
            """
            UPDATE rr_rent_rules
            SET monthly_rent = %s,
                is_minimum = %s,
                is_active = %s,
                updated_at = %s
            WHERE LOWER(COALESCE(shelter, '')) = %s
              AND program_level = %s
              AND unit_type = %s
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE rr_rent_rules
            SET monthly_rent = ?,
                is_minimum = ?,
                is_active = ?,
                updated_at = ?
            WHERE LOWER(COALESCE(shelter, '')) = ?
              AND program_level = ?
              AND unit_type = ?
            """
        ),
        (
            monthly_rent,
            _bool_for_db(is_minimum),
            _bool_for_db(True),
            now,
            shelter,
            program_level,
            unit_type,
        ),
    )


def _save_policy_settings(shelter: str) -> None:
    now = utcnow_iso()
    db_execute(
        (
            """
            UPDATE rr_rent_policy_settings
            SET rent_due_day = %s,
                rent_late_day = %s,
                rent_late_fee_per_day = %s,
                carry_forward_balance = %s,
                level_8_adjustment_guidance = %s,
                accepted_payment_methods = %s,
                payment_collector_roles = %s,
                updated_at = %s
            WHERE LOWER(COALESCE(shelter, '')) = %s
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE rr_rent_policy_settings
            SET rent_due_day = ?,
                rent_late_day = ?,
                rent_late_fee_per_day = ?,
                carry_forward_balance = ?,
                level_8_adjustment_guidance = ?,
                accepted_payment_methods = ?,
                payment_collector_roles = ?,
                updated_at = ?
            WHERE LOWER(COALESCE(shelter, '')) = ?
            """
        ),
        (
            _clamped_day(request.form.get("rent_due_day"), 1),
            _clamped_day(request.form.get("rent_late_day"), 6),
            _money_from_form("rent_late_fee_per_day", 1.00),
            _bool_for_db((request.form.get("carry_forward_balance") or "yes") == "yes"),
            _text_from_form(
                "level_8_adjustment_guidance",
                "Level 8 rent starts at the configured minimum and may be adjusted based on the income and expense ratio determined by the case manager.",
            ),
            _text_from_form("accepted_payment_methods", "Money order\nCashier check"),
            _text_from_form("payment_collector_roles", "Case managers only"),
            now,
            shelter,
        ),
    )


def _save_rent_rules(shelter: str) -> None:
    for group in RULE_GROUPS:
        for program_level, unit_type in group["rows"]:
            if unit_type not in EDITABLE_UNIT_TYPES:
                continue

            _update_rule(
                shelter=shelter,
                program_level=program_level,
                unit_type=unit_type,
                monthly_rent=_money_from_form(_rule_field_name(program_level, unit_type)),
                is_minimum=program_level == "8",
            )


@RR_rent_admin.route("", methods=["GET", "POST"])
@require_login
@require_shelter
def rent_config_page():
    if not _director_allowed(session):
        flash("Admin or shelter director access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    seed_default_rr_rent_config(shelter)

    if request.method == "POST":
        with db_transaction():
            _save_rent_rules(shelter)
            _save_policy_settings(shelter)

        flash("RR rent configuration updated.", "ok")
        return redirect(url_for("RR_rent_admin.rent_config_page"))

    return render_template(
        "RR_admin_rent_config.html",
        shelter=shelter,
        grouped_rules=_grouped_rules(shelter),
        policy=load_rr_rent_policy(shelter),
    )
