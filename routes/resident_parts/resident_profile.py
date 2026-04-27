from flask import flash, redirect, render_template, request, url_for

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from routes.case_management_parts.helpers import placeholder


def edit_resident_profile_view(resident_id: int):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {ph}
        """,
        (resident_id,),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    if request.method == "POST":
        phone = (request.form.get("phone") or "").strip()
        birth_year = request.form.get("birth_year")

        db_execute(
            f"""
            UPDATE residents
            SET phone = {ph},
                birth_year = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (phone, birth_year or None, utcnow_iso(), resident_id),
        )

        flash("Resident profile updated.", "ok")
        return redirect(url_for("residents.edit_resident_profile", resident_id=resident_id))

    return render_template(
        "resident_profile_edit.html",
        resident=resident,
    )
