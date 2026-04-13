from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from core.access import require_resident
from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.pass_rules import (
    gh_pass_rule_box,
    pass_type_options,
    shared_pass_rule_box,
    use_gh_pass_form,
)
from core.rate_limit import is_rate_limited
from core.runtime import init_db
from routes.resident_parts.pass_request_helpers import (
    extract_pass_form_data,
    flash_pass_request_restriction_if_blocked,
    insert_pass_request,
    load_pass_request_context,
    log_pass_insert_failure,
    today_chicago_iso,
    validate_pass_request_form,
)


def _client_ip() -> str:
    from flask import request

    return (request.remote_addr or "").strip() or "unknown"


def _render_pass_form(
    *,
    shelter: str,
    resident_level: str,
    resident_phone: str,
    hour_summary,
    form_data: dict | None = None,
):
    use_gh_form = use_gh_pass_form(shelter, resident_level)
    template_name = "resident_pass_request_gh.html" if use_gh_form else "resident_pass_request.html"
    rule_box = (
        gh_pass_rule_box(shelter, resident_level)
        if use_gh_form
        else shared_pass_rule_box(shelter, resident_level)
    )

    return render_template(
        template_name,
        shelter=shelter,
        resident_level=resident_level,
        resident_phone=resident_phone,
        hour_summary=hour_summary,
        pass_type_options=pass_type_options(),
        rule_box=rule_box,
        form_data=form_data or {},
    )


def _redirect_resident_signin(message: str):
    flash(message, "error")
    return redirect(url_for("resident_requests.resident_signin"))


def _render_form_with_errors(*, context, form, errors: list[str]):
    for error in errors:
        flash(error, "error")
    return (
        _render_pass_form(
            shelter=context.shelter,
            resident_level=context.resident_level,
            resident_phone=form.resident_phone,
            hour_summary=context.hour_summary,
            form_data=form.as_form_dict(),
        ),
        400,
    )


def _render_rate_limited_form(*, context, form):
    flash("Too many pass submissions. Please wait a few minutes and try again.", "error")
    return (
        _render_pass_form(
            shelter=context.shelter,
            resident_level=context.resident_level,
            resident_phone=form.resident_phone,
            hour_summary=context.hour_summary,
            form_data=form.as_form_dict(),
        ),
        429,
    )


def resident_pass_request_view():
    @require_resident
    def _inner():
        init_db()

        context = load_pass_request_context()
        if not context:
            return _redirect_resident_signin("Resident session is invalid. Please sign in again.")

        if flash_pass_request_restriction_if_blocked(context.resident_id):
            return redirect(url_for("resident_portal.home"))

        from flask import request

        if request.method == "GET":
            return _render_pass_form(
                shelter=context.shelter,
                resident_level=context.resident_level,
                resident_phone=context.resident_phone_from_db,
                hour_summary=context.hour_summary,
                form_data={"request_date": today_chicago_iso()},
            )

        form = extract_pass_form_data(context.resident_phone_from_db)

        rl_key = f"resident_pass_request:{_client_ip()}:{context.resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            return _render_rate_limited_form(context=context, form=form)

        if flash_pass_request_restriction_if_blocked(context.resident_id):
            return redirect(url_for("resident_portal.home"))

        validation = validate_pass_request_form(
            context=context,
            form=form,
        )
        if not validation.is_valid:
            return _render_form_with_errors(
                context=context,
                form=form,
                errors=validation.errors,
            )

        try:
            req_id = insert_pass_request(
                context=context,
                form=form,
                validation=validation,
            )
        except Exception as exc:
            log_pass_insert_failure(
                exc,
                resident_id=context.resident_id,
                shelter=context.shelter,
                pass_type=form.pass_type,
            )
            flash("Your pass request could not be submitted. Please try again.", "error")
            return (
                _render_pass_form(
                    shelter=context.shelter,
                    resident_level=context.resident_level,
                    resident_phone=form.resident_phone,
                    hour_summary=context.hour_summary,
                    form_data=form.as_form_dict(),
                ),
                500,
            )

        log_action(
            "pass",
            req_id,
            context.shelter,
            None,
            "create",
            f"Resident submitted {form.pass_type} pass request phone={form.resident_phone or ''}".strip(),
        )

        flash("Your pass request was submitted successfully.", "ok")
        return redirect(url_for("resident_portal.home"))

    return _inner()
    
