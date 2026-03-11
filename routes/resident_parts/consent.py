from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited


# Resident SMS consent flows
#
# Future extraction note
# If this area grows, split into:
# public_consent_pages.py
# resident_consent_flow.py
#
# Another future cleanup:
# stop importing shelter and init helpers from app.py
# by moving those into dedicated core or resident service modules.


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def sms_consent_public_alias_view():
    return redirect("/resident/sms-consent", code=302)


def sms_consent_public_alias_slash_view():
    return redirect("/sms-consent", code=301)


def sms_consent_view():
    return """
    <html>
        <head>
            <title>SMS Consent - Downtown Women’s Center</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
            <h2>SMS Updates from Downtown Women’s Center</h2>

            <p>
                To receive SMS updates regarding shelter leave approvals, transportation notifications,
                and service reminders, text <strong>JOIN</strong> to <strong>+1 806 639 4503</strong>.
            </p>

            <p>
                Message frequency varies. Message and data rates may apply.
                Reply STOP to opt out. Reply HELP for help.
            </p>

            <p>
                <a href="/privacy">Privacy Policy</a><br>
                <a href="/terms">Terms and Conditions</a>
            </p>
        </body>
    </html>
    """


def resident_consent_view():
    from app import get_all_shelters, init_db

    init_db()

    next_url = (request.args.get("next") or request.form.get("next") or "").strip()

    allowed_next = {
        url_for("resident_requests.resident_leave"),
        url_for("resident_requests.resident_transport"),
        url_for("resident_portal.home"),
    }

    if next_url not in allowed_next:
        next_url = url_for("resident_portal.home")

    resident_id = session.get("resident_id")
    resident_identifier = session.get("resident_identifier") or ""
    shelter = session.get("resident_shelter") or ""
    all_shelters = get_all_shelters()

    if not resident_id or shelter not in all_shelters:
        flash("Please sign in again.", "error")
        return redirect(url_for("resident_requests.resident_signin", next=next_url))

    if request.method == "GET":
        return render_template("resident_consent.html", next=next_url)

    ip = _client_ip()
    rl_key = f"resident_consent:{ip}:{resident_identifier or resident_id}"
    if is_rate_limited(rl_key, limit=10, window_seconds=300):
        flash("Too many consent attempts. Please wait a few minutes and try again.", "error")
        return render_template("resident_consent.html", next=next_url), 429

    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in ["accept", "decline"]:
        flash("Select accept or decline.", "error")
        return render_template("resident_consent.html", next=next_url), 400

    now = utcnow_iso()
    kind = g.get("db_kind")

    if choice == "accept":
        session["sms_consent_done"] = True
        session["sms_opt_in"] = True

        db_execute(
            """
            UPDATE residents
            SET sms_opt_in = %s, sms_opt_in_at = %s
            WHERE id = %s
            """
            if kind == "pg"
            else """
            UPDATE residents
            SET sms_opt_in = ?, sms_opt_in_at = ?
            WHERE id = ?
            """,
            (True if kind == "pg" else 1, now, resident_id),
        )

        log_action("resident", resident_id, shelter, None, "sms_opt_in", "Resident accepted SMS consent")
        flash("Thank you. SMS consent recorded.", "ok")
        return redirect(next_url)

    session["sms_consent_done"] = True
    session["sms_opt_in"] = False

    db_execute(
        """
        UPDATE residents
        SET sms_opt_in = %s, sms_opt_in_at = NULL
        WHERE id = %s
        """
        if kind == "pg"
        else """
        UPDATE residents
        SET sms_opt_in = ?, sms_opt_in_at = NULL
        WHERE id = ?
        """,
        (False if kind == "pg" else 0, resident_id),
    )

    log_action("resident", resident_id, shelter, None, "sms_opt_out", "Resident declined SMS consent")
    flash("Preference saved.", "ok")
    return redirect(next_url)
