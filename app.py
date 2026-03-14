from __future__ import annotations

import os
from datetime import timedelta

from flask import flash, redirect, render_template, request, session, url_for

from core.app_factory import create_app
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited
from core.request_security import register_request_security
from core.request_utils import client_ip
from core.runtime import init_db
from core.helpers import utcnow_iso


# ------------------------------------------------------------
# Create application
# ------------------------------------------------------------

app = create_app()


# ------------------------------------------------------------
# Request security wiring
# ------------------------------------------------------------

def _client_ip() -> str:
    return client_ip()


register_request_security(
    app,
    client_ip_func=_client_ip,
    is_ip_banned_func=is_ip_banned,
    is_rate_limited_func=is_rate_limited,
    ban_ip_func=ban_ip,
)


# ------------------------------------------------------------
# Secret key / session configuration
# ------------------------------------------------------------

secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
if not secret:
    raise RuntimeError("FLASK_SECRET_KEY is required and must be set in the environment.")

app.secret_key = secret
app.permanent_session_lifetime = timedelta(hours=8)

COOKIE_SECURE = (os.environ.get("COOKIE_SECURE") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

app.config.update(
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


# ------------------------------------------------------------
# CSRF
# ------------------------------------------------------------

import secrets


def _csrf_token() -> str:
    tok = session.get("_csrf_token")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["_csrf_token"] = tok
    return tok


app.jinja_env.globals["csrf_token"] = _csrf_token


def _csrf_protect():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    exempt_endpoints = {
        "resident_requests.sms_consent",
        "twilio.twilio_inbound",
        "twilio.twilio_status",
        "forms_ingest.jotform_webhook",
    }

    if request.endpoint in exempt_endpoints:
        return None

    sent = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf_token") or ""

    if not sent or not expected or sent != expected:
        flash("Session expired. Please retry.", "error")

        fallback = url_for("auth.staff_login")

        if request.endpoint and (
            str(request.endpoint).startswith("resident_")
            or str(request.endpoint).startswith("resident_requests.")
        ):
            fallback = url_for("resident_requests.resident_signin")

        return redirect(request.referrer or fallback)

    return None


@app.before_request
def _csrf_before_request():
    resp = _csrf_protect()
    if resp is not None:
        return resp


# ------------------------------------------------------------
# Error handlers
# ------------------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# ------------------------------------------------------------
# Dev entrypoint
# ------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        init_db()

    app.run(host="127.0.0.1", port=5000)
