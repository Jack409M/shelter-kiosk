from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from core.audit import log_action
from core.db import db_fetchone
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    AA_NA_PARENT_ACTIVITY_LABEL,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    VOLUNTEER_PARENT_ACTIVITY_LABEL,
    load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter,
)
from core.kiosk_service import handle_checkin, handle_checkout
from core.runtime import get_all_shelters, get_client_ip, init_db

kiosk = Blueprint("kiosk", __name__)


def _kiosk_enabled() -> bool:
    row = db_fetchone("SELECT kiosk_intake_enabled FROM security_settings ORDER BY id ASC LIMIT 1")
    if row is None:
        return True
    return bool(row.get("kiosk_intake_enabled"))


def _resolve_shelter_or_404(shelter: str) -> str | None:
    normalized = (shelter or "").strip().lower()
    return next(
        (name for name in get_all_shelters() if str(name or "").strip().lower() == normalized),
        None,
    )


def _active_checkout_categories_for_shelter(shelter: str) -> list[dict[str, Any]]:
    shelter_key = (shelter or "").strip().lower()
    rows = load_kiosk_activity_categories_for_shelter(shelter_key)

    categories: list[dict[str, Any]] = []
    for row in rows or []:
        label = str(row.get("activity_label") or "").strip()
        if not label:
            continue
        if not row.get("active"):
            continue
        categories.append(dict(row))

    return categories


def _active_child_options_by_parent_for_shelter(
    shelter: str,
    checkout_categories: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    shelter_key = (shelter or "").strip().lower()
    parent_keys = {
        str(item.get("activity_key") or "").strip()
        for item in checkout_categories
        if str(item.get("activity_key") or "").strip()
    }

    child_options_by_parent: dict[str, list[dict[str, Any]]] = {}
    for parent_key in sorted(parent_keys):
        rows = load_active_kiosk_activity_child_options_for_shelter(
            shelter_key,
            parent_key,
        )

        options: list[dict[str, Any]] = []
        for row in rows or []:
            option_label = str(row.get("option_label") or "").strip()
            if not option_label:
                continue
            options.append(dict(row))

        if options:
            child_options_by_parent[parent_key] = options

    return child_options_by_parent


def _checkout_template_context(
    *,
    shelter: str,
    checkout_categories: list[dict[str, Any]],
    child_options_by_parent: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    aa_na_child_options = child_options_by_parent.get(AA_NA_PARENT_ACTIVITY_KEY, [])
    volunteer_child_options = child_options_by_parent.get(VOLUNTEER_PARENT_ACTIVITY_KEY, [])

    child_option_labels_by_parent = {
        parent_key: [str(item.get("option_label") or "").strip() for item in rows if str(item.get("option_label") or "").strip()]
        for parent_key, rows in child_options_by_parent.items()
    }

    return {
        "shelter": shelter,
        "checkout_categories": checkout_categories,
        "aa_na_parent_activity_key": AA_NA_PARENT_ACTIVITY_KEY,
        "aa_na_parent_activity_label": AA_NA_PARENT_ACTIVITY_LABEL,
        "aa_na_child_options": aa_na_child_options,
        "volunteer_parent_activity_key": VOLUNTEER_PARENT_ACTIVITY_KEY,
        "volunteer_parent_activity_label": VOLUNTEER_PARENT_ACTIVITY_LABEL,
        "volunteer_child_options": volunteer_child_options,
        "child_option_labels_by_parent": child_option_labels_by_parent,
    }


def _invalid_shelter_response() -> tuple[str, int]:
    return "Invalid shelter", 404


def _kiosk_disabled_response(*, shelter_key: str, ip: str) -> tuple[str, int]:
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        "kiosk_disabled_block",
        f"ip={ip}",
    )
    return "Kiosk intake is temporarily disabled.", 503


def _cooldown_key(shelter_key: str, ip: str) -> str:
    return f"kiosk_cooldown:{shelter_key}:{ip}"


def _resident_code_lock_key(shelter_key: str, code_key: str) -> str:
    return f"kiosk_resident_code_lock:{shelter_key}:{code_key}"


def _resident_code_fail_key(shelter_key: str, code_key: str) -> str:
    return f"kiosk_resident_code_fail:{shelter_key}:{code_key}"


def _checkin_ip_rate_key(shelter_key: str, ip: str) -> str:
    return f"kiosk_checkin_ip:{shelter_key}:{ip}"


def _checkout_ip_rate_key(shelter_key: str, ip: str) -> str:
    return f"kiosk_checkout_ip:{shelter_key}:{ip}"


def _checkin_cooldown_trigger_key(shelter_key: str, ip: str) -> str:
    return f"kiosk_checkin_cooldown_trigger:{shelter_key}:{ip}"


def _checkout_cooldown_trigger_key(shelter_key: str, ip: str) -> str:
    return f"kiosk_checkout_cooldown_trigger:{shelter_key}:{ip}"


def _render_checkin(
    *,
    shelter: str,
    actual_end_required: bool,
    prior_activity_label: str,
    resident_code_value: str = "",
    status_code: int = 200,
) -> tuple[str, int] | str:
    rendered = render_template(
        "kiosk_checkin.html",
        shelter=shelter,
        actual_end_required=actual_end_required,
        prior_activity_label=prior_activity_label,
        resident_code_value=resident_code_value,
    )
    if status_code == 200:
        return rendered
    return rendered, status_code


def _render_checkout(
    *,
    shelter: str,
    checkout_categories: list[dict[str, Any]],
    child_options_by_parent: dict[str, list[dict[str, Any]]],
    status_code: int = 200,
) -> tuple[str, int] | str:
    rendered = render_template(
        "kiosk_checkout.html",
        **_checkout_template_context(
            shelter=shelter,
            checkout_categories=checkout_categories,
            child_options_by_parent=child_options_by_parent,
        ),
    )
    if status_code == 200:
        return rendered
    return rendered, status_code


def _blocked_by_cooldown_response(
    *,
    shelter_key: str,
    ip: str,
    seconds_remaining: int,
    render_response: tuple[str, int] | str,
) -> tuple[str, int] | str:
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        "kiosk_cooldown_blocked",
        f"ip={ip} seconds_remaining={seconds_remaining}",
    )
    flash("System cooling down. Please wait 30 seconds before trying again.", "error")
    return render_response


def _blocked_by_resident_code_lock_response(
    *,
    shelter_key: str,
    ip: str,
    code_key: str,
    seconds_remaining: int,
    render_response: tuple[str, int] | str,
) -> tuple[str, int] | str:
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        "kiosk_resident_code_locked",
        f"ip={ip} resident_code={code_key} seconds_remaining={seconds_remaining}",
    )
    flash("That Resident Code is temporarily locked. Please wait and try again.", "error")
    return render_response


def _start_kiosk_cooldown_response(
    *,
    shelter_key: str,
    ip: str,
    lock_key_value: str,
    lock_key_fn,
    render_response: tuple[str, int] | str,
) -> tuple[str, int] | str:
    lock_key_fn(lock_key_value, 30)
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        "kiosk_cooldown_started",
        f"ip={ip} seconds=30",
    )
    flash("System cooling down. Please wait 30 seconds before trying again.", "error")
    return render_response


def _rate_limited_response(
    *,
    shelter_key: str,
    ip: str,
    action_type: str,
    render_response: tuple[str, int] | str,
) -> tuple[str, int] | str:
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        action_type,
        f"ip={ip}",
    )
    flash("Too many attempts. Please wait and try again.", "error")
    return render_response


def _maybe_lock_failed_resident_code(
    *,
    shelter_key: str,
    ip: str,
    code_key: str,
    errors: list[str],
    is_rate_limited_fn,
    lock_key_fn,
) -> None:
    if "Invalid Resident Code." not in errors:
        return

    if is_rate_limited_fn(
        _resident_code_fail_key(shelter_key, code_key),
        limit=5,
        window_seconds=300,
    ):
        lock_key_fn(_resident_code_lock_key(shelter_key, code_key), 180)
        log_action(
            "kiosk",
            None,
            shelter_key,
            None,
            "kiosk_resident_code_lock_started",
            f"ip={ip} resident_code={code_key} seconds=180",
        )


def _log_kiosk_failure(
    *,
    shelter_key: str,
    action_type: str,
    ip: str,
    code_key: str,
    errors: list[str],
) -> None:
    log_action(
        "kiosk",
        None,
        shelter_key,
        None,
        action_type,
        f"ip={ip} resident_code={code_key} errors={' | '.join(errors)}",
    )


@kiosk.route("/kiosk/<shelter>")
def kiosk_home(shelter: str):
    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return _invalid_shelter_response()

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()

    try:
        kiosk_enabled = _kiosk_enabled()
    except Exception:
        current_app.logger.exception(
            "Failed to load kiosk enabled state for shelter=%s", shelter_key
        )
        return "Kiosk is temporarily unavailable.", 503

    if not kiosk_enabled:
        return _kiosk_disabled_response(shelter_key=shelter_key, ip=ip)

    return render_template("kiosk_home.html", shelter=display_shelter)


@kiosk.route("/kiosk/<shelter>/checkin", methods=["GET", "POST"])
def kiosk_checkin(shelter: str):
    from core.rate_limit import (
        get_key_lock_seconds_remaining,
        is_key_locked,
        is_rate_limited,
        lock_key,
    )

    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return _invalid_shelter_response()

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()

    try:
        kiosk_enabled = _kiosk_enabled()
    except Exception:
        current_app.logger.exception(
            "Failed to load kiosk enabled state for shelter=%s", shelter_key
        )
        return "Kiosk is temporarily unavailable.", 503

    if not kiosk_enabled:
        return _kiosk_disabled_response(shelter_key=shelter_key, ip=ip)

    if request.method == "GET":
        return _render_checkin(
            shelter=display_shelter,
            actual_end_required=False,
            prior_activity_label="",
        )

    resident_code = str(request.form.get("resident_code") or "").strip()
    code_key = resident_code if resident_code else "blank"

    actual_end_hour = str(request.form.get("actual_end_hour") or "").strip()
    actual_end_minute = str(request.form.get("actual_end_minute") or "").strip()
    actual_end_ampm = str(request.form.get("actual_end_ampm") or "").strip().upper()

    kiosk_cooldown_key = _cooldown_key(shelter_key, ip)
    resident_code_lock_key = _resident_code_lock_key(shelter_key, code_key)

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        return _blocked_by_cooldown_response(
            shelter_key=shelter_key,
            ip=ip,
            seconds_remaining=seconds_remaining,
            render_response=_render_checkin(
                shelter=display_shelter,
                actual_end_required=False,
                prior_activity_label="",
                status_code=429,
            ),
        )

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        return _blocked_by_resident_code_lock_response(
            shelter_key=shelter_key,
            ip=ip,
            code_key=code_key,
            seconds_remaining=seconds_remaining,
            render_response=_render_checkin(
                shelter=display_shelter,
                actual_end_required=False,
                prior_activity_label="",
                status_code=429,
            ),
        )

    if is_rate_limited(
        _checkin_cooldown_trigger_key(shelter_key, ip),
        limit=30,
        window_seconds=30,
    ):
        return _start_kiosk_cooldown_response(
            shelter_key=shelter_key,
            ip=ip,
            lock_key_value=kiosk_cooldown_key,
            lock_key_fn=lock_key,
            render_response=_render_checkin(
                shelter=display_shelter,
                actual_end_required=False,
                prior_activity_label="",
                status_code=429,
            ),
        )

    if is_rate_limited(_checkin_ip_rate_key(shelter_key, ip), limit=15, window_seconds=60):
        return _rate_limited_response(
            shelter_key=shelter_key,
            ip=ip,
            action_type="kiosk_checkin_rate_limited",
            render_response=_render_checkin(
                shelter=display_shelter,
                actual_end_required=False,
                prior_activity_label="",
                status_code=429,
            ),
        )

    service_result = handle_checkin(
        shelter=shelter_key,
        resident_code=resident_code,
        actual_end_hour=actual_end_hour,
        actual_end_minute=actual_end_minute,
        actual_end_ampm=actual_end_ampm,
    )

    if not service_result.success:
        if service_result.needs_actual_end_prompt:
            return _render_checkin(
                shelter=display_shelter,
                actual_end_required=True,
                prior_activity_label=service_result.prior_activity_label,
                resident_code_value=resident_code,
            )

        for error_message in service_result.errors:
            flash(error_message, "error")

        _maybe_lock_failed_resident_code(
            shelter_key=shelter_key,
            ip=ip,
            code_key=code_key,
            errors=service_result.errors,
            is_rate_limited_fn=is_rate_limited,
            lock_key_fn=lock_key,
        )

        _log_kiosk_failure(
            shelter_key=shelter_key,
            action_type="kiosk_checkin_failed",
            ip=ip,
            code_key=code_key,
            errors=service_result.errors,
        )

        return _render_checkin(
            shelter=display_shelter,
            actual_end_required=service_result.actual_end_required,
            prior_activity_label=service_result.prior_activity_label,
            resident_code_value=resident_code if service_result.actual_end_required else "",
            status_code=service_result.status_code,
        )

    log_action(
        "attendance",
        service_result.resident_id,
        shelter_key,
        None,
        "kiosk_check_in",
        service_result.log_note,
    )

    flash("Checked in.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter_key))


@kiosk.route("/kiosk/<shelter>/checkout", methods=["GET", "POST"])
def kiosk_checkout(shelter: str):
    from core.rate_limit import (
        get_key_lock_seconds_remaining,
        is_key_locked,
        is_rate_limited,
        lock_key,
    )

    init_db()

    matched_shelter = _resolve_shelter_or_404(shelter)
    if not matched_shelter:
        return _invalid_shelter_response()

    display_shelter = matched_shelter
    shelter_key = matched_shelter.strip().lower()
    ip = get_client_ip()

    try:
        kiosk_enabled = _kiosk_enabled()
        checkout_categories = _active_checkout_categories_for_shelter(shelter_key)
        child_options_by_parent = _active_child_options_by_parent_for_shelter(
            shelter_key,
            checkout_categories,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to load kiosk checkout dependencies for shelter=%s", shelter_key
        )
        return "Kiosk is temporarily unavailable.", 503

    if not kiosk_enabled:
        return _kiosk_disabled_response(shelter_key=shelter_key, ip=ip)

    if request.method == "GET":
        return _render_checkout(
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            child_options_by_parent=child_options_by_parent,
        )

    resident_code = str(request.form.get("resident_code") or "").strip()
    destination = str(request.form.get("destination") or "").strip()
    aa_na_meeting_1 = str(request.form.get("aa_na_meeting_1") or "").strip()
    aa_na_meeting_2 = str(request.form.get("aa_na_meeting_2") or "").strip()
    volunteer_community_service_option = str(
        request.form.get("volunteer_community_service_option") or ""
    ).strip()
    child_option_value = str(request.form.get("child_option_value") or "").strip()

    start_time_hour = str(request.form.get("start_time_hour") or "").strip()
    start_time_minute = str(request.form.get("start_time_minute") or "").strip()
    start_time_ampm = str(request.form.get("start_time_ampm") or "").strip().upper()

    end_time_hour = str(request.form.get("end_time_hour") or "").strip()
    end_time_minute = str(request.form.get("end_time_minute") or "").strip()
    end_time_ampm = str(request.form.get("end_time_ampm") or "").strip().upper()

    expected_back_hour = str(request.form.get("expected_back_hour") or "").strip()
    expected_back_minute = str(request.form.get("expected_back_minute") or "").strip()
    expected_back_ampm = str(request.form.get("expected_back_ampm") or "").strip().upper()

    note = str(request.form.get("note") or "").strip()

    code_key = resident_code if resident_code else "blank"
    kiosk_cooldown_key = _cooldown_key(shelter_key, ip)
    resident_code_lock_key = _resident_code_lock_key(shelter_key, code_key)

    if is_key_locked(kiosk_cooldown_key):
        seconds_remaining = get_key_lock_seconds_remaining(kiosk_cooldown_key)
        return _blocked_by_cooldown_response(
            shelter_key=shelter_key,
            ip=ip,
            seconds_remaining=seconds_remaining,
            render_response=_render_checkout(
                shelter=display_shelter,
                checkout_categories=checkout_categories,
                child_options_by_parent=child_options_by_parent,
                status_code=429,
            ),
        )

    if is_key_locked(resident_code_lock_key):
        seconds_remaining = get_key_lock_seconds_remaining(resident_code_lock_key)
        return _blocked_by_resident_code_lock_response(
            shelter_key=shelter_key,
            ip=ip,
            code_key=code_key,
            seconds_remaining=seconds_remaining,
            render_response=_render_checkout(
                shelter=display_shelter,
                checkout_categories=checkout_categories,
                child_options_by_parent=child_options_by_parent,
                status_code=429,
            ),
        )

    if is_rate_limited(
        _checkout_cooldown_trigger_key(shelter_key, ip),
        limit=30,
        window_seconds=30,
    ):
        return _start_kiosk_cooldown_response(
            shelter_key=shelter_key,
            ip=ip,
            lock_key_value=kiosk_cooldown_key,
            lock_key_fn=lock_key,
            render_response=_render_checkout(
                shelter=display_shelter,
                checkout_categories=checkout_categories,
                child_options_by_parent=child_options_by_parent,
                status_code=429,
            ),
        )

    if is_rate_limited(_checkout_ip_rate_key(shelter_key, ip), limit=15, window_seconds=60):
        return _rate_limited_response(
            shelter_key=shelter_key,
            ip=ip,
            action_type="kiosk_checkout_rate_limited",
            render_response=_render_checkout(
                shelter=display_shelter,
                checkout_categories=checkout_categories,
                child_options_by_parent=child_options_by_parent,
                status_code=429,
            ),
        )

    service_result = handle_checkout(
        shelter=shelter_key,
        resident_code=resident_code,
        destination=destination,
        aa_na_meeting_1=aa_na_meeting_1,
        aa_na_meeting_2=aa_na_meeting_2,
        volunteer_community_service_option=volunteer_community_service_option,
        child_option_value=child_option_value,
        start_time_hour=start_time_hour,
        start_time_minute=start_time_minute,
        start_time_ampm=start_time_ampm,
        end_time_hour=end_time_hour,
        end_time_minute=end_time_minute,
        end_time_ampm=end_time_ampm,
        expected_back_hour=expected_back_hour,
        expected_back_minute=expected_back_minute,
        expected_back_ampm=expected_back_ampm,
        note=note,
        checkout_categories=checkout_categories,
        child_options_by_parent=child_options_by_parent,
        aa_na_parent_activity_key=AA_NA_PARENT_ACTIVITY_KEY,
        volunteer_parent_activity_key=VOLUNTEER_PARENT_ACTIVITY_KEY,
    )

    if not service_result.success:
        for error_message in service_result.errors:
            flash(error_message, "error")

        _maybe_lock_failed_resident_code(
            shelter_key=shelter_key,
            ip=ip,
            code_key=code_key,
            errors=service_result.errors,
            is_rate_limited_fn=is_rate_limited,
            lock_key_fn=lock_key,
        )

        _log_kiosk_failure(
            shelter_key=shelter_key,
            action_type="kiosk_checkout_failed",
            ip=ip,
            code_key=code_key,
            errors=service_result.errors,
        )

        return _render_checkout(
            shelter=display_shelter,
            checkout_categories=checkout_categories,
            child_options_by_parent=child_options_by_parent,
            status_code=service_result.status_code,
        )

    log_action(
        "attendance",
        service_result.resident_id,
        shelter_key,
        None,
        "kiosk_check_out",
        (
            f"destination={service_result.destination_value or ''} "
            f"activity_key={service_result.selected_activity_key or ''} "
            f"meeting_1={service_result.aa_na_meeting_1 or ''} "
            f"meeting_2={service_result.aa_na_meeting_2 or ''} "
            f"meeting_count={service_result.meeting_count} "
            f"is_recovery_meeting={service_result.is_recovery_meeting_value} "
            f"volunteer_option={service_result.volunteer_community_service_option or ''} "
            f"child_option={service_result.child_option_value or ''} "
            f"start={service_result.obligation_start_value or ''} "
            f"end={service_result.obligation_end_value or ''} "
            f"expected_back={service_result.expected_back_value or ''}"
        ).strip(),
    )

    flash("Checked out.", "ok")
    return redirect(url_for("kiosk.kiosk_home", shelter=shelter_key))
