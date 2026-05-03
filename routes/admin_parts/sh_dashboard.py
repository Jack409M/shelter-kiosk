from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for

from core.admin_rbac import require_admin_role
from core.db import db_fetchall, db_fetchone
from core.enterprise_readiness import (
    build_enterprise_readiness_cards,
    sync_enterprise_readiness_alerts,
)
from core.helpers import utcnow_iso
from core.scheduler_job_history import count_recent_failed_job_runs, load_latest_job_run
from core.sh_events import latest_sh_event_by_status, recent_sh_events_by_status
from core.system_alerts import (
    acknowledge_system_alert,
    count_open_system_alerts_by_severity,
    create_system_alert,
    load_open_system_alerts,
    load_recent_system_alert_delivery_logs,
    resolve_system_alert,
    sync_system_health_alerts,
)
from core.timestamp_normalization import normalize_timestamp_columns

CHICAGO_TZ = ZoneInfo("America/Chicago")
PASS_CLEANUP_JOB_NAME = "pass_retention_cleanup"
RENT_POSTING_JOB_NAME = "monthly_rent_charge_posting"
PASS_CLEANUP_STALE_THRESHOLD = timedelta(hours=24)
RECENT_ERROR_ACTIVE_THRESHOLD = timedelta(minutes=15)
RUN_SLOTS = ((6, 0), (15, 0), (23, 0))


def _status(label: str, state: str, detail: str = "", meta: str = "") -> dict:
    return {
        "label": label,
        "state": state,
        "detail": detail,
        "meta": meta,
    }


def _parse_event_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        current_app.logger.warning("system_health_invalid_event_timestamp=%s", raw)
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(CHICAGO_TZ)


def _event_is_recent(value: object, threshold: timedelta = RECENT_ERROR_ACTIVE_THRESHOLD) -> bool:
    parsed = _parse_event_datetime(value)
    if parsed is None:
        return False
    return datetime.now(CHICAGO_TZ) - parsed <= threshold


def _load_job_metadata(row: dict | None) -> dict:
    if not row:
        return {}

    raw = str(row.get("metadata") or "").strip()
    if not raw:
        return {}

    try:
        value = json.loads(raw)
    except Exception:
        current_app.logger.warning("system_health_invalid_job_metadata=%s", raw[:250])
        return {}

    return value if isinstance(value, dict) else {}


def _next_pass_cleanup_run(now: datetime | None = None) -> datetime:
    current = now or datetime.now(CHICAGO_TZ)

    for hour, minute in RUN_SLOTS:
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > current:
            return candidate

    first_hour, first_minute = RUN_SLOTS[0]
    tomorrow = current + timedelta(days=1)
    return tomorrow.replace(hour=first_hour, minute=first_minute, second=0, microsecond=0)


def _latest_pass_cleanup_completed_at(row: dict | None) -> datetime | None:
    if not row:
        return None

    return _parse_event_datetime(row.get("finished_at") or row.get("started_at"))


def _pass_cleanup_is_stale(row: dict | None) -> bool:
    completed_at = _latest_pass_cleanup_completed_at(row)
    if completed_at is None:
        return False

    return datetime.now(CHICAGO_TZ) - completed_at >= PASS_CLEANUP_STALE_THRESHOLD


def _pass_cleanup_card() -> dict:
    latest = load_latest_job_run(PASS_CLEANUP_JOB_NAME)
    next_run = _next_pass_cleanup_run().isoformat(timespec="minutes")

    if not latest:
        return _status(
            "Last Pass Cleanup",
            "warn",
            "No database job run has been recorded yet.",
            f"Next scheduled run: {next_run}",
        )

    status = str(latest.get("status") or "").strip().lower()
    metadata = _load_job_metadata(latest)
    total_backfilled = int(metadata.get("total_backfilled", 0) or 0)
    total_deleted = int(metadata.get("total_deleted", 0) or 0)
    total_errors = int(metadata.get("total_errors", 0) or 0)
    failure_count = count_recent_failed_job_runs(
        job_name=PASS_CLEANUP_JOB_NAME,
        since_iso=(datetime.now(UTC) - timedelta(hours=24)).replace(microsecond=0).isoformat(),
    )
    stale = _pass_cleanup_is_stale(latest)
    finished_at = str(latest.get("finished_at") or latest.get("started_at") or "").strip()
    duration_ms = latest.get("duration_ms")

    if stale:
        return _status(
            "Last Pass Cleanup",
            "error",
            "Pass cleanup has not completed in over 24 hours.",
            f"Last recorded: {finished_at} | Failures last 24h: {failure_count} | Next scheduled run: {next_run}",
        )

    if status == "error":
        error_message = str(latest.get("error_message") or "Pass cleanup failed.").strip()
        return _status(
            "Last Pass Cleanup",
            "error",
            error_message,
            f"Last recorded: {finished_at} | Failures last 24h: {failure_count} | Next scheduled run: {next_run}",
        )

    if status == "skipped_lock":
        return _status(
            "Last Pass Cleanup",
            "ok",
            "Cleanup was skipped because another app instance held the database job lock.",
            f"Last skipped: {finished_at} | Failures last 24h: {failure_count} | Next scheduled run: {next_run}",
        )

    if status == "running":
        return _status(
            "Last Pass Cleanup",
            "warn",
            "Pass cleanup is currently recorded as running.",
            f"Started: {finished_at} | Failures last 24h: {failure_count} | Next scheduled run: {next_run}",
        )

    detail = f"Backfilled {total_backfilled} | Deleted {total_deleted} | Errors {total_errors}"
    if duration_ms is not None:
        detail = f"{detail} | Duration {duration_ms} ms"

    state = "error" if total_errors else "ok"
    return _status(
        "Last Pass Cleanup",
        state,
        detail,
        f"Finished: {finished_at} | Failures last 24h: {failure_count} | Next scheduled run: {next_run}",
    )


def _rent_posting_card() -> dict:
    latest = load_latest_job_run(RENT_POSTING_JOB_NAME)

    if not latest:
        return _status(
            "Last Rent Posting",
            "warn",
            "No monthly rent posting run has been recorded yet.",
            "Runs automatically during days 1 through 3 of each month in Chicago time.",
        )

    status = str(latest.get("status") or "").strip().lower()
    metadata = _load_job_metadata(latest)
    rent_month_label = str(metadata.get("rent_month_label") or "current month").strip()
    success_count = int(metadata.get("success_count", 0) or 0)
    error_count = int(metadata.get("error_count", 0) or 0)
    total_shelters = int(metadata.get("total_shelters", 0) or 0)
    finished_at = str(latest.get("finished_at") or latest.get("started_at") or "").strip()
    duration_ms = latest.get("duration_ms")
    failure_count = count_recent_failed_job_runs(
        job_name=RENT_POSTING_JOB_NAME,
        since_iso=(datetime.now(UTC) - timedelta(days=7)).replace(microsecond=0).isoformat(),
    )

    if status == "error":
        error_message = str(latest.get("error_message") or "Monthly rent posting failed.").strip()
        return _status(
            "Last Rent Posting",
            "error",
            error_message,
            f"Month: {rent_month_label} | Last recorded: {finished_at} | Failures last 7d: {failure_count}",
        )

    if status == "running":
        return _status(
            "Last Rent Posting",
            "warn",
            "Monthly rent posting is currently recorded as running.",
            f"Started: {finished_at} | Month: {rent_month_label}",
        )

    detail = (
        f"Checked {success_count} of {total_shelters} shelter(s); "
        f"Errors {error_count}"
    )
    if duration_ms is not None:
        detail = f"{detail} | Duration {duration_ms} ms"

    state = "error" if error_count else "ok"
    return _status(
        "Last Rent Posting",
        state,
        detail,
        f"Month: {rent_month_label} | Finished: {finished_at} | Failures last 7d: {failure_count}",
    )


def _timestamp_format_card() -> dict:
    try:
        result = normalize_timestamp_columns(apply=False)
    except Exception as err:
        current_app.logger.exception("timestamp_format_health_check_failed")
        return _status(
            "Timestamp Formats",
            "warn",
            "Timestamp format scan failed.",
            str(err),
        )

    dirty_count = int(result.would_update or 0)
    skipped_count = int(result.skipped or 0)

    if dirty_count > 0:
        return _status(
            "Timestamp Formats",
            "warn",
            f"{dirty_count} timestamp value(s) need normalization.",
            "Use Timestamp Cleanup from this page.",
        )

    if skipped_count > 0:
        return _status(
            "Timestamp Formats",
            "ok",
            "Timestamp formats are normalized. Some non parseable legacy values were safely skipped.",
            f"Skipped legacy values: {skipped_count}",
        )

    return _status(
        "Timestamp Formats",
        "ok",
        "Timestamp formats are normalized.",
        f"Scanned {result.scanned} values across {result.columns_discovered} columns",
    )


def _pass_cleanup_watchdog() -> None:
    latest = load_latest_job_run(PASS_CLEANUP_JOB_NAME)
    if not latest or not _pass_cleanup_is_stale(latest):
        return

    finished_at = str(latest.get("finished_at") or latest.get("started_at") or "").strip()
    create_system_alert(
        alert_type="scheduled_job",
        severity="critical",
        title="Pass cleanup has not run in over 24 hours",
        message="Pass cleanup job appears to be stalled.",
        source_module="pass_retention_watchdog",
        alert_key="pass_cleanup:stale:critical",
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


def _check_backup_status() -> dict:
    return _status(
        "Backup System",
        "ok",
        "Daily Railway backups and daily local computer backups are in place. Restore testing is required before any production recovery.",
        "Policy documented at /staff/admin/backup-documentation",
    )


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
    latest = load_latest_job_run(PASS_CLEANUP_JOB_NAME)
    latest_started_at = str(latest.get("started_at") or "").strip() if latest else ""
    enablement = (os.environ.get("ENABLE_PASS_RETENTION_SCHEDULER") or "").strip()

    if scheduler_status == "running":
        meta_parts = [
            part
            for part in (
                scheduler_schedule,
                f"last_seen={last_seen_at}" if last_seen_at else "",
                f"last_db_run={latest_started_at}" if latest_started_at else "",
            )
            if part
        ]
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
            f"ENABLE_PASS_RETENTION_SCHEDULER={enablement or 'not set'}",
        )

    if scheduler_status == "testing_skipped":
        return _status(
            "Scheduler",
            "ok",
            "Scheduler is skipped during tests.",
            "TESTING=true",
        )

    if latest_started_at:
        return _status(
            "Scheduler",
            "warn",
            "Pass retention has database run history, but current scheduler process status is unknown.",
            f"last_db_run={latest_started_at} | ENABLE_PASS_RETENTION_SCHEDULER={enablement or 'not set'}",
        )

    return _status(
        "Scheduler",
        "error",
        "Pass retention scheduler is not reporting as running.",
        f"ENABLE_PASS_RETENTION_SCHEDULER={enablement or 'not set'}",
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

    if latest_error:
        error_created_at = latest_error.get("created_at", "")
        error_is_recent = _event_is_recent(error_created_at)
        error_card = _status(
            "Last Error",
            "error" if error_is_recent else "ok",
            latest_error.get("message", ""),
            (
                f"Active recent error at {error_created_at}"
                if error_is_recent
                else f"Historical error only: {error_created_at}"
            ),
        )
    else:
        error_card = _status(
            "Last Error",
            "ok",
            "No System Health errors recorded.",
            "No errors found",
        )

    return [success_card, error_card]


def system_health_events_api():
    if not require_admin_role():
        return jsonify([]), 403

    status = request.args.get("status", "success")
    rows = recent_sh_events_by_status(status)
    return jsonify(rows)


def acknowledge_system_health_alert_view(alert_id: int):
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    note = request.form.get("acknowledgement_note", "")
    if acknowledge_system_alert(alert_id, acknowledgement_note=note):
        flash("System alert acknowledged.", "success")
    else:
        flash("System alert was not found.", "error")

    return redirect(url_for("admin.admin_system_health"))


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


def sms_log_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    rows = db_fetchall(
        """
        SELECT
            id,
            to_number_raw,
            to_number_e164,
            status,
            reason,
            twilio_sid,
            enforce_consent,
            created_at
        FROM sms_attempt_log
        ORDER BY id DESC
        LIMIT 100
        """
    )

    return render_template(
        "sms_log.html",
        title="SMS Log",
        rows=rows or [],
    )


def system_health_dashboard_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    checked_at = datetime.now(CHICAGO_TZ).replace(microsecond=0).isoformat()

    runtime_cards = [
        _check_database_status(),
        _app_version_status(),
        _check_scheduler_status(),
        _check_sms_status(),
        _check_backup_status(),
        _pass_cleanup_card(),
        _rent_posting_card(),
        _timestamp_format_card(),
        *_job_status_cards(),
    ]
    enterprise_cards = build_enterprise_readiness_cards()
    cards = [*runtime_cards, *enterprise_cards]

    _pass_cleanup_watchdog()
    alertable_runtime_cards = [
        card for card in runtime_cards
        if card.get("label") not in {"Last Error", "Last Successful Event", "SMS", "Last Pass Cleanup", "Last Rent Posting"}
    ]
    sync_system_health_alerts(alertable_runtime_cards)
    sync_enterprise_readiness_alerts(enterprise_cards)
    alerts = load_open_system_alerts()
    alert_counts = count_open_system_alerts_by_severity()
    delivery_logs = load_recent_system_alert_delivery_logs()

    summary_state = "ok"
    if any(card["state"] == "error" for card in cards) or alert_counts.get("critical"):
        summary_state = "error"
    elif any(card["state"] == "warn" for card in cards) or alert_counts.get("error") or alert_counts.get("warn"):
        summary_state = "warn"

    return render_template(
        "sh_dashboard.html",
        title="System Health",
        cards=cards,
        runtime_cards=runtime_cards,
        enterprise_cards=enterprise_cards,
        alerts=alerts,
        alert_counts=alert_counts,
        delivery_logs=delivery_logs,
        summary_state=summary_state,
        checked_at=checked_at,
    )
