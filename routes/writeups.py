from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


bp = Blueprint("writeups", __name__, url_prefix="/writeups")


@bp.route("/")
@require_login
@require_shelter
def writeups_list():
    rows = db_fetchall(
        """
        SELECT *
        FROM writeups
        ORDER BY created_at DESC
        """
    )
    return render_template("writeups/list.html", rows=rows)


@bp.route("/create", methods=["GET", "POST"])
@require_login
@require_shelter
def writeups_create():
    if request.method == "POST":
        resident_id = request.form.get("resident_id")
        notes = request.form.get("notes")

        db_execute(
            """
            INSERT INTO writeups (
                resident_id,
                notes,
                created_at,
                created_by
            )
            VALUES (?, ?, ?, ?)
            """,
            (resident_id, notes, utcnow_iso(), g.user["id"]),
        )

        flash("Write-up created", "success")
        return redirect(url_for("writeups.writeups_list"))

    return render_template("writeups/create.html")


@bp.route("/<int:writeup_id>")
@require_login
@require_shelter
def writeups_detail(writeup_id: int):
    row = db_fetchone(
        """
        SELECT *
        FROM writeups
        WHERE id = ?
        """,
        (writeup_id,),
    )

    if not row:
        flash("Write-up not found", "warning")
        return redirect(url_for("writeups.writeups_list"))

    return render_template("writeups/detail.html", row=row)
