from __future__ import annotations

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for

from core.db import db_fetchone
from core.sh_events import latest_sh_event_by_status, recent_sh_events_by_status
from core.system_alerts import (
    count_open_system_alerts_by_severity,
    create_system_alert,
    load_open_system_alerts,
    resolve_system_alert,
    sync_system_health_alerts,
)
from routes.admin_parts.helpers import require_admin_role

CHICAGO_TZ = ZoneInfo("America/Chicago")
PASS_CLEANUP_WARN_THRESHOLD = timedelta(hours=12)
PASS_CLEANUP_CRITICAL_THRESHOLD = timedelta(hours=24)


def _status(label: str, state: str, detail: str = "", meta: str = "") -> dict:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "meta": meta,
    }


def _pass_cleanup_card() -> dict:
    last = current_app.extensions.get("pass_retention_scheduler_last_result") or {}

    if not last:
        return _status(
            "Last Pass Cleanup",
            "warn",
            "No pass cleanup run recorded yet.",
            "Waiting for first scheduled run",
        )

    errors = int(last.get("total_errors", 0) or 0)
    state = "error" if errors else "ok"

    return _status(
        "Last Pass Cleanup",
        state,
        f"Backfilled {last.get('total_backfilled', 0)} | Deleted {last.get('total_deleted', 0)} | Errors {errors}",
        f"Finished: {last.get('finished_at', '')}",
    )


def _pass_cleanup_watchdog() -> None:
    last = current_app.extensions.get("pass_retention_scheduler_last_result") or {}
    finished_at = str(last.get("finished_at") or "").strip()

    if not finished_at:
        return

    try:
        last_dt = datetime.fromisoformat(finished_at)
    except Exception:
        current_app.logger.warning("pass_cleanup_watchdog_invalid_finished_at=%s", finished_at)
        return

    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=CHICAGO_TZ)

    now = datetime.now(CHICAGO_TZ)
    elapsed = now - last_dt.astimezone(CHICAGO_TZ)

    if elapsed >= PASS_CLEANUP_CRITICAL_THRESHOLD:
        create_system_alert(
            alert_type="scheduled_job",
            severity="critical",
            title="Pass cleanup has not run in over 24 hours",
            message="Pass cleanup job appears to be stalled.",
            source_module="pass_retention_watchdog",
            alert_key="pass_cleanup:stale:critical",
            metadata=f"last_run={finished_at}",
        )
        return

    if elapsed >= PASS_CLEANUP_WARN_THRESHOLD:
        create_system_alert(
            alert_type="scheduled_job",
            severity="warn",
            title="Pass cleanup has not run in over 12 hours",
            message="Pass cleanup may be delayed.",
            source_module="pass_retention_watchdog",
            alert_key="pass_cleanup:stale:warn",
            metadata=f"last_run={finished_at}",
        )


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
        current_app.logger.exception("system_health_database_check_failed")
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
    scheduler_status = str(
        current_app.extensions.get("pass_retention_scheduler_status") or ""
    ).strip()
    scheduler_schedule = str(
        current_app.extensions.get("pass_retention_scheduler_schedule") or ""
    ).strip()
    last_seen_at = str(
        current_app.extensions.get("pass_retention_scheduler_last_seen_at") or ""
    ).strip()
    last_finished_at = str(
        current_app.extensions.get("pass_retention_scheduler_last_finished_at") or ""
    ).strip()

    if scheduler_status == "running":
        meta_parts = [part for part in (scheduler_schedule, f"last_seen={last_seen_at}" if last_seen_at else "") if part]
        return _status(
            "Scheduler",
            "ok",
            "Pass retention scheduler is running.",
            " | ".join(meta_parts),
        )

    if scheduler_status == "disabled":
        return _status(
            "Scheduler",
            "warn",
            "Scheduler is disabled by configuration.",
            "SCHEDULER_ENABLED=false",
        )

    if scheduler_status == "testing_skipped":
        return _status(
            "Scheduler",
            "ok",
            "Scheduler is skipped during tests.",
            "TESTING=true",
        )

    if last_finished_at:
        return _status(
            "Scheduler",
            "warn",
            "Pass retention scheduler has run before, but current status is unknown.",
            f"last_finished={last_finished_at}",
        )

    return _status(
        "Scheduler",
        "error",
        "Pass retention scheduler is not reporting as running.",
        "No active scheduler state found",
    )


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
    detail = (
        "Current deployed version detected."
        if state == "ok"
        else "No deployed version value was found."
    )

    return _status("App Version", state, detail, display_version)


def _job_status_cards() -> list[dict]:
    latest_success = latest_sh_event_by_status("success")
    latest_error = latest_sh_event_by_status("error")

    success_card = _status(
        "Last Successful Event",
        "ok" if latest_success else "warn",
        latest_success.get("message", "")
        if latest_success
        else "No successful System Health events recorded yet.",
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


def resolve_system_health_alert_view(alert_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    note = request.form.get("resolution_note", "")
    if resolve_system_alert(alert_id, resolution_note=note):
        flash("System alert resolved.", "success")
    else:
        flash("System alert was not found.", "error")

    return redirect(url_for("admin.admin_system_health"))


def system_health_dashboard_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checked_at = datetime.now(CHICAGO_TZ).replace(microsecond=0).isoformat()

    cards = [
        _check_database_status(),
        _app_version_status(),
        _check_scheduler_status(),
        _check_sms_status(),
        _pass_cleanup_card(),
        *_job_status_cards(),
    ]

    _pass_cleanup_watchdog()
    sync_system_health_alerts(cards)
    alerts = load_open_system_alerts()
    alert_counts = count_open_system_alerts_by_severity()

    summary_state = "ok"
    if any(card["state"] == "error" for card in cards) or alert_counts.get("critical"):
        summary_state = "error"
    elif any(card["state"] == "warn" for card in cards) or alert_counts.get("error") or alert_counts.get("warn"):
        summary_state = "warn"

    return render_template(
        "sh_dashboard.html",
        title="System Health",
        cards=cards,
        alerts=alerts,
        alert_counts=alert_counts,
        summary_state=summary_state,
        checked_at=checked_at,
    )
