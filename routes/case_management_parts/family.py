from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder


def family_intake_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))

        if not child_name:
            children = db_fetchall(
                f"""
                SELECT
                    id,
                    resident_id,
                    child_name,
                    birth_year,
                    relationship,
                    living_status
                FROM resident_children
                WHERE resident_id = {ph}
                  AND is_active = TRUE
                ORDER BY id ASC
                """,
                (resident_id,),
            )

            flash("Child name is required.", "error")
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
                children=children,
            )

        existing_child = db_fetchone(
            f"""
            SELECT id
            FROM resident_children
            WHERE resident_id = {ph}
              AND LOWER(child_name) = LOWER({ph})
              AND (
                    (birth_year IS NULL AND {ph} IS NULL)
                    OR birth_year = {ph}
                  )
              AND is_active = TRUE
            LIMIT 1
            """,
            (
                resident_id,
                child_name,
                birth_year,
                birth_year,
            ),
        )

        if existing_child:
            children = db_fetchall(
                f"""
                SELECT
                    id,
                    resident_id,
                    child_name,
                    birth_year,
                    relationship,
                    living_status
                FROM resident_children
                WHERE resident_id = {ph}
                  AND is_active = TRUE
                ORDER BY id ASC
                """,
                (resident_id,),
            )

            flash("This child already exists for this resident.", "error")
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
                children=children,
            )

        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            INSERT INTO resident_children
            (
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                is_active,
                created_at,
                updated_at
            )
            VALUES
            (
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                TRUE,
                {ph},
                {ph}
            )
            """,
            (
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                now,
                now,
            ),
        )

        flash("Child added.", "success")
        return redirect(url_for("case_management.family_intake", resident_id=resident_id))

    children = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            child_name,
            birth_year,
            relationship,
            living_status
        FROM resident_children
        WHERE resident_id = {ph}
          AND is_active = TRUE
        ORDER BY id ASC
        """,
        (resident_id,),
    )

    return render_template(
        "case_management/family_intake.html",
        resident_id=resident_id,
        children=children,
    )


def edit_child_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    child = db_fetchone(
        f"""
        SELECT
            id,
            resident_id,
            child_name,
            birth_year,
            relationship,
            living_status
        FROM resident_children
        WHERE id = {ph}
        """,
        (child_id,),
    )

    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))
        resident_id = child["resident_id"] if isinstance(child, dict) else child[1]

        existing_child = db_fetchone(
            f"""
            SELECT id
            FROM resident_children
            WHERE resident_id = {ph}
              AND LOWER(child_name) = LOWER({ph})
              AND (
                    (birth_year IS NULL AND {ph} IS NULL)
                    OR birth_year = {ph}
                  )
              AND is_active = TRUE
              AND id <> {ph}
            LIMIT 1
            """,
            (
                resident_id,
                child_name,
                birth_year,
                birth_year,
                child_id,
            ),
        )

        if existing_child:
            flash("This child already exists for this resident.", "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

        db_execute(
            f"""
            UPDATE resident_children
            SET
                child_name = {ph},
                birth_year = {ph},
                relationship = {ph},
                living_status = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                child_name,
                birth_year,
                relationship,
                living_status,
                datetime.utcnow().isoformat(),
                child_id,
            ),
        )

        flash("Child updated.", "success")
        return redirect(url_for("case_management.family_intake", resident_id=resident_id))

    return render_template(
        "case_management/edit_child.html",
        child=child,
    )


def delete_child_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    child = db_fetchone(
        f"""
        SELECT
            id,
            resident_id
        FROM resident_children
        WHERE id = {ph}
        """,
        (child_id,),
    )

    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"] if isinstance(child, dict) else child[1]

    db_execute(
        f"""
        UPDATE resident_children
        SET
            is_active = FALSE,
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            datetime.utcnow().isoformat(),
            child_id,
        ),
    )

    flash("Child removed.", "success")
    return redirect(url_for("case_management.family_intake", resident_id=resident_id))


def edit_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    service = db_fetchone(
        f"""
        SELECT
            id,
            resident_child_id,
            service_type,
            outcome,
            quantity,
            unit,
            notes,
            service_date
        FROM child_services
        WHERE id = {ph}
        """,
        (service_id,),
    )

    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    if request.method == "POST":
        service_type = clean(request.form.get("service_type"))
        outcome = clean(request.form.get("outcome"))
        quantity = parse_int(request.form.get("quantity"))
        unit = clean(request.form.get("unit"))
        notes = clean(request.form.get("notes"))
        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            UPDATE child_services
            SET
                service_type = {ph},
                outcome = {ph},
                quantity = {ph},
                unit = {ph},
                notes = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                service_type,
                outcome,
                quantity,
                unit,
                notes,
                now,
                service_id,
            ),
        )

        child_id = service["resident_child_id"] if isinstance(service, dict) else service[1]

        flash("Service updated.", "success")
        return redirect(url_for("case_management.child_services", child_id=child_id))

    return render_template(
        "case_management/edit_child_service.html",
        service=service,
    )


def delete_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    service = db_fetchone(
        f"""
        SELECT resident_child_id
        FROM child_services
        WHERE id = {ph}
        """,
        (service_id,),
    )

    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"] if isinstance(service, dict) else service[0]

    db_execute(
        f"""
        DELETE FROM child_services
        WHERE id = {ph}
        """,
        (service_id,),
    )

    flash("Service deleted.", "success")
    return redirect(url_for("case_management.child_services", child_id=child_id))


def child_services_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    ph = placeholder()

    child = db_fetchone(
        f"""
        SELECT
            id,
            resident_id
        FROM resident_children
        WHERE id = {ph}
        """,
        (child_id,),
    )

    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"] if isinstance(child, dict) else child[1]

    enrollment = db_fetchone(
        f"""
        SELECT
            id
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    if not enrollment:
        flash("No active enrollment found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    if request.method == "POST":
        service_type = clean(request.form.get("service_type"))
        outcome = clean(request.form.get("outcome"))
        quantity = parse_int(request.form.get("quantity"))
        unit = clean(request.form.get("unit"))
        notes = clean(request.form.get("notes"))
        now = datetime.utcnow().isoformat()

        db_execute(
            f"""
            INSERT INTO child_services
            (
                resident_child_id,
                enrollment_id,
                service_date,
                service_type,
                outcome,
                quantity,
                unit,
                notes,
                created_at,
                updated_at
            )
            VALUES
            (
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph}
            )
            """,
            (
                child_id,
                enrollment_id,
                now,
                service_type,
                outcome,
                quantity,
                unit,
                notes,
                now,
                now,
            ),
        )

        flash("Child service added.", "success")
        return redirect(url_for("case_management.child_services", child_id=child_id))

    services = db_fetchall(
        f"""
        SELECT
            id,
            service_date,
            service_type,
            quantity,
            unit,
            outcome,
            notes
        FROM child_services
        WHERE resident_child_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (child_id,),
    )

    return render_template(
        "case_management/child_services.html",
        child_id=child_id,
        resident_id=resident_id,
        services=services,
    )
