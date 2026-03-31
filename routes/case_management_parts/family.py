from __future__ import annotations

from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _resident_in_scope(resident_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            r.shelter
        FROM residents r
        WHERE r.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (resident_id, shelter),
    )


def _child_in_scope(child_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            rc.id,
            rc.resident_id,
            rc.child_name,
            rc.birth_year,
            rc.relationship,
            rc.living_status,
            rc.is_active
        FROM resident_children rc
        JOIN residents r
          ON r.id = rc.resident_id
        WHERE rc.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (child_id, shelter),
    )


def _child_service_in_scope(service_id: int):
    ph = placeholder()
    shelter = _current_shelter()

    return db_fetchone(
        f"""
        SELECT
            cs.id,
            cs.resident_child_id,
            cs.enrollment_id,
            cs.service_date,
            cs.service_type,
            cs.outcome,
            cs.quantity,
            cs.unit,
            cs.notes,
            rc.resident_id
        FROM child_services cs
        JOIN resident_children rc
          ON rc.id = cs.resident_child_id
        JOIN residents r
          ON r.id = rc.resident_id
        WHERE cs.id = {ph}
          AND {shelter_equals_sql("r.shelter")}
        LIMIT 1
        """,
        (service_id, shelter),
    )


def _active_children_for_resident(resident_id: int):
    ph = placeholder()

    return db_fetchall(
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


def _latest_enrollment_for_resident(resident_id: int):
    return fetch_current_enrollment_for_resident(resident_id, columns="id")


def _parse_service_date(value: str | None) -> str | None:
    value = clean(value)
    if not value:
        return None

    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None

    return value


def _is_unique_constraint_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def family_intake_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    resident = _resident_in_scope(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    ph = placeholder()

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))

        if not child_name:
            children = _active_children_for_resident(resident_id)
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
            children = _active_children_for_resident(resident_id)
            flash("This child already exists for this resident.", "error")
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
                children=children,
            )

        now = datetime.utcnow().isoformat()

        try:
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
        except Exception as exc:
            if _is_unique_constraint_error(exc):
                children = _active_children_for_resident(resident_id)
                flash("This child already exists for this resident.", "error")
                return render_template(
                    "case_management/family_intake.html",
                    resident_id=resident_id,
                    children=children,
                )

            current_app.logger.exception(
                "Failed to add child for resident_id=%s",
                resident_id,
            )
            children = _active_children_for_resident(resident_id)
            flash("Unable to add child. Please try again or contact an administrator.", "error")
            return render_template(
                "case_management/family_intake.html",
                resident_id=resident_id,
                children=children,
            )

        flash("Child added.", "success")
        return redirect(url_for("case_management.family_intake", resident_id=resident_id))

    children = _active_children_for_resident(resident_id)

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

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]

    if request.method == "POST":
        child_name = clean(request.form.get("child_name"))
        birth_year = parse_int(request.form.get("birth_year"))
        relationship = clean(request.form.get("relationship"))
        living_status = clean(request.form.get("living_status"))

        if not child_name:
            flash("Child name is required.", "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

        ph = placeholder()
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

        try:
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
        except Exception as exc:
            if _is_unique_constraint_error(exc):
                flash("This child already exists for this resident.", "error")
                return redirect(url_for("case_management.edit_child", child_id=child_id))

            current_app.logger.exception(
                "Failed to edit child_id=%s resident_id=%s",
                child_id,
                resident_id,
            )
            flash("Unable to update child. Please try again or contact an administrator.", "error")
            return redirect(url_for("case_management.edit_child", child_id=child_id))

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

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]
    ph = placeholder()

    try:
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
    except Exception:
        current_app.logger.exception(
            "Failed to delete child_id=%s resident_id=%s",
            child_id,
            resident_id,
        )
        flash("Unable to remove child. Please try again or contact an administrator.", "error")
        return redirect(url_for("case_management.family_intake", resident_id=resident_id))

    flash("Child removed.", "success")
    return redirect(url_for("case_management.family_intake", resident_id=resident_id))


def edit_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"]
    resident_id = service["resident_id"]

    if request.method == "POST":
        service_type = clean(request.form.get("service_type"))
        outcome = clean(request.form.get("outcome"))
        quantity = parse_int(request.form.get("quantity"))
        unit = clean(request.form.get("unit"))
        notes = clean(request.form.get("notes"))
        service_date = _parse_service_date(request.form.get("service_date"))

        if request.form.get("service_date") and not service_date:
            flash("Service date must be valid.", "error")
            return redirect(url_for("case_management.edit_child_service", service_id=service_id))

        ph = placeholder()

        try:
            db_execute(
                f"""
                UPDATE child_services
                SET
                    service_type = {ph},
                    outcome = {ph},
                    quantity = {ph},
                    unit = {ph},
                    notes = {ph},
                    service_date = {ph},
                    updated_at = {ph}
                WHERE id = {ph}
                """,
                (
                    service_type,
                    outcome,
                    quantity,
                    unit,
                    notes,
                    service_date,
                    datetime.utcnow().isoformat(),
                    service_id,
                ),
            )
        except Exception:
            current_app.logger.exception(
                "Failed to edit child service_id=%s resident_id=%s",
                service_id,
                resident_id,
            )
            flash("Unable to update child service. Please try again or contact an administrator.", "error")
            return redirect(url_for("case_management.edit_child_service", service_id=service_id))

        flash("Service updated.", "success")
        return redirect(url_for("case_management.child_services", child_id=child_id))

    return render_template(
        "case_management/edit_child_service.html",
        service=service,
        resident_id=resident_id,
    )


def delete_child_service_view(service_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    service = _child_service_in_scope(service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("case_management.index"))

    child_id = service["resident_child_id"]
    ph = placeholder()

    try:
        now = datetime.utcnow().isoformat()
        db_execute(
            f"""
            UPDATE child_services
            SET
                is_deleted = TRUE,
                deleted_at = {ph},
                deleted_by_staff_user_id = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                now,
                session.get("staff_user_id"),
                now,
                service_id,
            ),
        )
    except Exception:
        current_app.logger.exception(
            "Failed to delete child service_id=%s child_id=%s",
            service_id,
            child_id,
        )
        flash("Unable to remove child service. Please try again or contact an administrator.", "error")
        return redirect(url_for("case_management.child_services", child_id=child_id))

    flash("Service deleted.", "success")
    return redirect(url_for("case_management.child_services", child_id=child_id))


def child_services_view(child_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    child = _child_in_scope(child_id)
    if not child:
        flash("Child not found.", "error")
        return redirect(url_for("case_management.index"))

    resident_id = child["resident_id"]
    enrollment = _latest_enrollment_for_resident(resident_id)

    if not enrollment:
        flash("No active enrollment found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]
    ph = placeholder()

    if request.method == "POST":
        service_type = clean(request.form.get("service_type"))
        outcome = clean(request.form.get("outcome"))
        quantity = parse_int(request.form.get("quantity"))
        unit = clean(request.form.get("unit"))
        notes = clean(request.form.get("notes"))
        service_date = _parse_service_date(request.form.get("service_date"))

        if request.form.get("service_date") and not service_date:
            flash("Service date must be valid.", "error")
            return redirect(url_for("case_management.child_services", child_id=child_id))

        now = datetime.utcnow().isoformat()

        try:
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
                    service_date or now,
                    service_type,
                    outcome,
                    quantity,
                    unit,
                    notes,
                    now,
                    now,
                ),
            )
        except Exception:
            current_app.logger.exception(
                "Failed to add child service for child_id=%s resident_id=%s enrollment_id=%s",
                child_id,
                resident_id,
                enrollment_id,
            )
            flash("Unable to add child service. Please try again or contact an administrator.", "error")
            return redirect(url_for("case_management.child_services", child_id=child_id))

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
          AND COALESCE(is_deleted, FALSE) = FALSE
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
