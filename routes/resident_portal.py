from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, session, url_for

from core.db import db_fetchall
from core.runtime import init_db


resident_portal = Blueprint(
    "resident_portal",
    __name__,
    url_prefix="/resident",
)


@resident_portal.route("/home")
def home():
    if not session.get("resident_id"):
        return redirect(url_for("resident_requests.resident_signin"))

    init_db()

    resident_id = session.get("resident_id")
    shelter = (session.get("resident_shelter") or "").strip()

    pass_items = db_fetchall(
        """
        SELECT
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            created_at
        FROM resident_passes
        WHERE resident_id = %s
          AND shelter = %s
        ORDER BY created_at DESC
        LIMIT 10
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            created_at
        FROM resident_passes
        WHERE resident_id = ?
          AND shelter = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (resident_id, shelter),
    )

    transport_items = db_fetchall(
        """
        SELECT
            status,
            needed_at,
            destination,
            submitted_at
        FROM transport_requests
        WHERE resident_identifier = %s
          AND shelter = %s
        ORDER BY submitted_at DESC
        LIMIT 10
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            status,
            needed_at,
            destination,
            submitted_at
        FROM transport_requests
        WHERE resident_identifier = ?
          AND shelter = ?
        ORDER BY submitted_at DESC
        LIMIT 10
        """,
        ((session.get("resident_identifier") or "").strip(), shelter),
    )

    return render_template(
        "resident_home.html",
        pass_items=pass_items,
        transport_items=transport_items,
    )
