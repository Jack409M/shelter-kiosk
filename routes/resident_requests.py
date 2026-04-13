from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.audit import log_action
from core.data_integrity import check_resident_integrity
from core.db import db_fetchone
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.runtime import init_db
from routes.resident_parts.consent import (
    resident_consent_view,
    sms_consent_public_alias_slash_view,
    sms_consent_public_alias_view,
    sms_consent_view,
)
from routes.resident_parts.helpers import parse_dt as _parse_dt
from routes.resident_parts.pass_request import resident_pass_request_view


resident_requests = Blueprint("resident_requests", __name__)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _resident_session_int(key: str) -> int | None:
    value = session.get(key)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resident_session_text(key: str) -> str:
    return _clean_text(session.get(key))


def _allowed_resident_next_urls() -> set[str]:
    return {
        url_for("resident_requests.resident_pass_request"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
        url_for("resident_portal.resident_chores"),
    }


def _safe_next_url(candidate: str) -> str:
    next_url = _clean_text(candidate)
    if next_url in _allowed_resident_next_urls():
        return next_url
    return url_for("resident_portal.home")


def _load_resident_by_code(resident_code: str) -> dict[str, Any] | None:
    normalized_code = _clean_text(resident_code)
    if not normalized_code:
        return None

    return db_fetchone(
        """
        SELECT *
        FROM residents
        WHERE resident_code = %s
          AND is_active = TRUE
        LIMIT 1
        """,
        (normalized_code,),
    )


def _parse_transport_needed_at(needed_raw: str) -> tuple[datetime | None, str | None]:
    try:
        needed_local = _parse_dt(needed_raw)
        needed_dt = (
            needed_local.replace(tzinfo=CHICAGO_TZ)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
    except Exception:
        return None, "Invalid needed date or time."

    if needed_dt < datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1):
        return None, "Needed time cannot be in the past."

    return needed_dt, None


def _insert_transport_request(
    *,
    shelter: str,
    resident_identifier: str,
    first_name: str,
    last_name: str,
    needed_iso: str,
    pickup_location: str,
    destination: str,
    reason: str | None,
    resident_notes: str | None,
    callback_phone: str | None,
    submitted_at: str,
) -> int:
    row = db_fetchone(
        """
        INSERT INTO transport_requests (
            shelter,
            resident_identifier,
            first_name,
            last_name,
            needed_at,
            pickup_location,
            destination,
            reason,
            resident_notes,
            callback_phone,
            status,
            submitted_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            shelter,
            resident_identifier,
            first_name,
            last_name,
            needed_iso,
            pickup_location,
            destination,
            reason,
            resident_notes,
            callback_phone,
            "pending",
            submitted_at,
        ),
    )

    if row is None or row.get("id") is None:
        raise RuntimeError("Transport request insert did not return an id.")

    return int(row["id"])


def _resident_signin_details(ip: str, resident_code: str, next_url: str) -> str:
    safe_code = resident_code or "blank"
    return f"ip={ip} resident_code={safe_code} next={next_url or ''}"


def _clear_resident_session_and_redirect():
    session.clear()
    flash("Your session ended. Please sign in again.", "error")
    return redirect(url_for("resident_requests.resident_signin"))


def _enforce_resident_integrity_after_signin(resident_id: int):
    integrity_result = check_resident_integrity(resident_id)

    warning_messages = [
        issue.message
        for issue in integrity_result.issues
        if issue.severity == "warning"
    ]
    if warning_messages:
        current_app.logger.warning(
            "resident_signin integrity warnings resident_id=%s warnings=%s",
            resident_id,
            warning_messages,
        )

    if integrity_result.ok:
        return None

    error_messages = [
        issue.message
        for issue in integrity_result.issues
        if issue.severity == "error"
    ]

    current_app.logger.error(
        "resident_signin integrity failure resident_id=%s errors=%s",
        resident_id,
        error_messages,
    )

    session.clear()
    flash("We could not load your account safely. Please contact staff.", "error")
    return redirect(url_for("resident_requests.resident_signin"))


def _validate_transport_session_context() -> tuple[int | None, str, str, str, str]:
    resident_id = _resident_session_int("resident_id")
    shelter = _resident_session_text("resident_shelter")
    resident_identifier = _resident_session_text("resident_identifier")
    first_name = _resident_session_text("resident_first")
    last_name = _resident_session_text("resident_last")

    return resident_id, shelter, resident_identifier, first_name, last_name


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    from core.residents import resident_session_start

    init_db()

    next_url = _safe_next_url(request.args.get("next") or request.form.get("next") or "")

    if request.method == "GET":
        return render_template("resident_signin.html")

    ip = _client_ip()
    resident_code = _clean_text(request.form.get("resident_code"))

    if is_rate_limited(f"resident_signin:{ip}", limit=30, window_seconds=300):
        log_action(
            "security",
            None,
            None,
            None,
            "resident_signin_rate_limited",
            _resident_signin_details(ip, resident_code, next_url),
        )
        flash("Too many sign in attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_signin.html"), 429

    row = _load_resident_by_code(resident_code)

    if row is None:
        log_action(
            "security",
            None,
            None,
            None,
            "resident_signin_failed",
            f"reason=invalid_resident_code {_resident_signin_details(ip, resident_code, next_url)}",
        )
        flash("Invalid Resident Code.", "error")
        return render_template("resident_signin.html"), 401

    resident_id_value = row.get("id")
    resident_id = int(resident_id_value) if resident_id_value is not None else None
    shelter = _clean_text(row.get("shelter"))

    if resident_id is None or not shelter:
        current_app.logger.error(
            "resident_signin missing critical resident fields resident_id=%s shelter=%s",
            resident_id,
            shelter,
        )
        flash("We could not load your account safely. Please contact staff.", "error")
        return render_template("resident_signin.html"), 403

    session.clear()
    resident_session_start(row, shelter, resident_code)

    integrity_response = _enforce_resident_integrity_after_signin(resident_id)
    if integrity_response is not None:
        return integrity_response

    log_action(
        "security",
        None,
        shelter,
        None,
        "resident_signin_success",
        f"ip={ip} resident_code={resident_code}",
    )

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_requests.resident_consent", next=next_url))

    return redirect(next_url)


@resident_requests.get("/resident/logout")
def resident_logout():
    session.clear()
    return redirect(url_for("public.public_home"))


@resident_requests.route("/pass-request", methods=["GET", "POST"])
def resident_pass_request():
    return resident_pass_request_view()


@resident_requests.route("/transport", methods=["GET", "POST"])
@require_resident
def resident_transport():
    init_db()

    resident_id, shelter, resident_identifier, first_name, last_name = (
        _validate_transport_session_context()
    )

    if resident_id is None or not shelter or not resident_identifier:
        return _clear_resident_session_and_redirect()

    integrity_response = _enforce_resident_integrity_after_signin(resident_id)
    if integrity_response is not None:
        return integrity_response

    if request.method == "GET":
        return render_template("resident_transport.html", shelter=shelter)

    ip = _client_ip()
    rl_key = f"resident_transport:{ip}:{resident_identifier}"
    if is_rate_limited(rl_key, limit=6, window_seconds=900):
        flash("Too many transportation submissions. Please wait a few minutes and try again.", "error")
        return render_template("resident_transport.html", shelter=shelter), 429

    needed_raw = _clean_text(request.form.get("needed_at"))
    pickup_location = _clean_text(request.form.get("pickup_location"))
    destination = _clean_text(request.form.get("destination"))
    reason = _clean_text(request.form.get("reason"))
    resident_notes = _clean_text(request.form.get("resident_notes"))
    callback_phone = _clean_text(request.form.get("callback_phone"))

    errors: list[str] = []

    if not first_name or not last_name or not needed_raw or not pickup_location or not destination:
        errors.append("Complete all required fields.")

    needed_dt, needed_error = _parse_transport_needed_at(needed_raw)
    if needed_error:
        errors.append(needed_error)

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("resident_transport.html", shelter=shelter), 400

    if needed_dt is None:
        flash("Invalid needed date or time.", "error")
        return render_template("resident_transport.html", shelter=shelter), 400

    needed_iso = needed_dt.replace(microsecond=0).isoformat()
    submitted_at = utcnow_iso()

    req_id = _insert_transport_request(
        shelter=shelter,
        resident_identifier=resident_identifier,
        first_name=first_name,
        last_name=last_name,
        needed_iso=needed_iso,
        pickup_location=pickup_location,
        destination=destination,
        reason=reason or None,
        resident_notes=resident_notes or None,
        callback_phone=callback_phone or None,
        submitted_at=submitted_at,
    )

    log_action("transport", req_id, shelter, None, "create", "Resident submitted transport request")
    flash("Your transportation request was submitted successfully.", "ok")
    return redirect(url_for("resident_portal.home"))


@resident_requests.get("/sms-consent")
def sms_consent_public_alias():
    return sms_consent_public_alias_view()


@resident_requests.get("/sms-consent/")
def sms_consent_public_alias_slash():
    return sms_consent_public_alias_slash_view()


@resident_requests.get("/resident/sms-consent")
def sms_consent():
    return sms_consent_view()


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    return resident_consent_view()
