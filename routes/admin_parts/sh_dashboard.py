from __future__ import annotations

import os
from datetime import UTC, datetime

from flask import flash, jsonify, redirect, render_template, request, url_for

from core.db import db_fetchone
from core.sh_events import latest_sh_event_by_status, recent_sh_events_by_status
from routes.admin_parts.helpers import require_admin_role


def _status(label: str, state: str, detail: str = "", meta: str = "") -> dict:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "meta": meta,
    }


def _check_database_status() -> dict:
    try:
        row = db_fetchone("SELECT 1 AS ok")
        ok_value = row.get("ok") if row else None
        if int(ok_value or 0) == 1:
            return _status(
                "Database",
                "ok",
                "Connected and responding to a simple query.",
                "SELECT 1 completed",
            )
    except Exception as err:
        return _status("Database", "error", "Database check failed.", str(err))

    return _status("Database", "error", "Database returned an unexpected response.")


def _check_sms_status() -> dict:
    sms_system_enabled = os.environ.get("SMS_SYSTEM_ENABLED", "true").strip().lower() == "true"
    twilio_enabled = os.environ.get("TWILIO_ENABLED", "false").strip().lower() == "true"
    has_sid = bool((os.environ.get("TWILIO_ACCOUNT_SID") or "").strip())
    has_token = bool((os.environ.get("TWILIO_AUTH_TOKEN") or "").strip())
    has_from = bool((os.environ.get("TWILIO_FROM_NUMBER") or "").strip())

    if not sms_system_enabled:
        return _status("SMS", "warn", "SMS master switch is disabled.", "SMS_SYSTEM_ENABLED=false")

    if not twilio_enabled:
        return _status("SMS", "warn", "Twilio sending is disabled.", "TWILIO_ENABLED=false")

    missing = []
    if not has_sid:
        missing.append("TWILIO_ACCOUNT_SID")
    if not has_token:
        missing.append("TWILIO_AUTH_TOKEN")
    if not has_from:
        missing.append("TWILIO_FROM_NUMBER")

    if missing:
        return _status(
            "SMS",
            "error",
            "Twilio sending is enabled, but required settings are missing.",
            ", ".join(missing),
        )

    return _status("SMS", "ok", "SMS sending appears configured.", "Twilio enabled")


def _check_scheduler_status() -> dict:
    scheduler_enabled = os.environ.get("SCHEDULER_ENABLED", "").strip().lower()
    if scheduler_enabled in {"true", "1", "yes", "on"}:
        return _status("Scheduler", "ok", "Scheduler flag is enabled.", "SCHEDULER_ENABLED=true")
    if scheduler_enabled in {"false", "0", "no", "off"}:
        return _status("Scheduler", "warn", "Scheduler flag is disabled.", "SCHEDULER_ENABLED=false")
    return _status("Scheduler", "warn", "Scheduler status is not configured yet.", "No scheduler flag found")


def _app_version_status() -> dict:
    version = (
        os.environ.get("APP_VERSION")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        or os.environ.get("SOURCE_VERSION")
        or "unknown"
    )

    display_version = version[:12] if version and version != "unknown" else "unknown"
    state = "ok" if display_version != "unknown" else "warn"
    detail = "Current deployed version detected." if state == "ok" else "No deployed version value was found."

    return _status("App Version", state, detail, display_version)


def _job_status_cards() -> list[dict]:
    latest_success = latest_sh_event_by_status("success")
    latest_error = latest_sh_event_by_status("error")

    success_card = _status(
        "Last Successful Event",
        "ok" if latest_success else "warn",
        latest_success.get("message", "") if latest_success else "No successful System Health events recorded yet.",
        latest_success.get("created_at", "") if latest_success else "Waiting for first event",
    )

    error_card = _status(
        "Last Error",
        "error" if latest_error else "ok",
        latest_error.get("message", "") if latest_error else "No System Health errors recorded.",
        latest_error.get("created_at", "") if latest_error else "No errors found",
    )

    return [success_card, error_card]


def system_health_events_api():
    if not require_admin_role():
        return jsonify([]), 403

    status = request.args.get("status", "success")
    rows = recent_sh_events_by_status(status)
    return jsonify(rows)


def system_health_dashboard_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    cards = [
        _check_database_status(),
        _app_version_status(),
        _check_scheduler_status(),
        _check_sms_status(),
        *_job_status_cards(),
    ]

    summary_state = "ok"
    if any(card["state"] == "error" for card in cards):
        summary_state = "error"
    elif any(card["state"] == "warn" for card in cards):
        summary_state = "warn"

    return render_template(
        "sh_dashboard.html",
        title="System Health",
        cards=cards,
        summary_state=summary_state,
        checked_at=checked_at,
    )
