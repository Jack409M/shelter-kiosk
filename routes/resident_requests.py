from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.access import require_resident
from core.audit import log_action
from core.db import db_fetchone
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.residents import resident_session_start
from core.runtime import init_db
from routes.resident_parts.consent import (
    resident_consent_view,
    sms_consent_view,
)
from routes.resident_parts.helpers import parse_dt as _parse_dt
from routes.resident_parts.pass_request import resident_pass_request_view

resident_requests = Blueprint("resident_requests", __name__)

CHICAGO_TZ = ZoneInfo("America/Chicago")

ALLOWED_RESIDENT_NEXT_PATHS = {
    "/pass-request",
    "/transport",
    "/resident/home",
    "/resident/chores",
}


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _db_sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _resident_session_text(key: str) -> str:
    return str(session.get(key) or "").strip()


def _safe_next_url(candidate: str) -> str:
    next_url = (candidate or "").strip()
    if next_url in ALLOWED_RESIDENT_NEXT_PATHS:
        return next_url
    return "/resident/home"


def _signin_next_url() -> str:
    return _safe_next_url(request.args.get("next") or request.form.get("next") or "")


def _load_resident_by_code(resident_code: str):
    return db_fetchone(
        _db_sql(
            "SELECT * FROM residents WHERE resident_code = %s",
            "SELECT * FROM residents WHERE resident_code = ?",
        ),
        (resident_code,),
    )


def _parse_transport_needed_at(needed_raw: str) -> tuple[datetime | None, str | None]:
    try:
        needed_local = _parse_dt(needed_raw)
        needed_dt = needed_local.replace(tzinfo=CHICAGO_TZ).astimezone(UTC).replace(tzinfo=None)
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return int(row["id"])


def _resident_transport_session_context() -> dict[str, str]:
    return {
        "shelter": _resident_session_text("resident_shelter"),
        "resident_identifier": _resident_session_text("resident_identifier"),
        "first_name": _resident_session_text("resident_first"),
        "last_name": _resident_session_text("resident_last"),
    }


@resident_requests.route("/resident", methods=["GET", "POST"])
def resident_signin():
    init_db()

    next_url = _signin_next_url()

    if request.method == "GET":
        return render_template("resident_signin.html", next=next_url)

    ip = _client_ip()
    resident_code = (request.form.get("resident_code") or "").strip()
    safe_code = resident_code or "blank"

    if is_rate_limited(f"resident_signin:{ip}", limit=30, window_seconds=300):
        log_action(
            "security",
            None,
            None,
            None,
            "resident_signin_rate_limited",
            f"ip={ip} resident_code={safe_code} next={next_url}",
        )
        flash("Too many sign in attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_signin.html", next=next_url), 429

    row = _load_resident_by_code(resident_code)

    if not row:
        log_action(
            "security",
            None,
            None,
            None,
            "resident_signin_failed",
            f"reason=invalid_resident_code ip={ip} resident_code={safe_code} next={next_url}",
        )
        flash("Invalid Resident Code.", "error")
        return render_template("resident_signin.html", next=next_url), 401

    shelter = ((row.get("shelter") if isinstance(row, dict) else row[1]) or "").strip()

    session.clear()
    resident_session_start(row, shelter, resident_code)

    log_action(
        "security",
        None,
        shelter or None,
        None,
        "resident_signin_success",
        f"ip={ip} resident_code={resident_code}",
    )

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_requests.resident_consent", next=next_url))

    return redirect(next_url)


@resident_requests.get("/resident/home")
def resident_home_compat():
    return redirect(url_for("resident_portal.home"))


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

    resident_context = _resident_transport_session_context()
    shelter = resident_context["shelter"]

    if request.method == "GET":
        return render_template("resident_transport.html", shelter=shelter)

    resident_identifier = resident_context["resident_identifier"]
    first_name = resident_context["first_name"]
    last_name = resident_context["last_name"]

    ip = _client_ip()
    rl_key = f"resident_transport:{ip}:{resident_identifier or 'unknown'}"
    if is_rate_limited(rl_key, limit=6, window_seconds=900):
        flash(
            "Too many transportation submissions. Please wait a few minutes and try again.",
            "error",
        )
        return render_template("resident_transport.html", shelter=shelter), 429

    needed_raw = (request.form.get("needed_at") or "").strip()
    pickup_location = (request.form.get("pickup_location") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    callback_phone = (request.form.get("callback_phone") or "").strip()

    errors: list[str] = []

    if not first_name or not last_name or not needed_raw or not pickup_location or not destination:
        errors.append("Complete all required fields.")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        needed_dt, needed_error = _parse_transport_needed_at(needed_raw)

    if needed_error:
        errors.append(needed_error)

    if errors:
        for error in errors:
            flash(error, "error")
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


@resident_requests.route("/sms-consent", methods=["GET", "POST"], endpoint="sms_consent")
@resident_requests.route("/sms-consent/", methods=["GET", "POST"], endpoint="sms_consent")
def sms_consent_public_alias():
    return Response("OK", status=200)


@resident_requests.get("/resident/sms-consent")
def resident_sms_consent():
    return sms_consent_view()


@resident_requests.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    return resident_consent_view()
