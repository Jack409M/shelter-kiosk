from __future__ import annotations

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import yes_no_to_int


def _insert_resident(data: dict[str, object], shelter: str) -> tuple[int, str, str]:
    ph = placeholder()
    resident_identifier = generate_resident_identifier()
    resident_code = generate_resident_code()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO residents
            (
                resident_identifier,
                resident_code,
                first_name,
                last_name,
                birth_year,
                phone,
                email,
                emergency_contact_name,
                emergency_contact_relationship,
                emergency_contact_phone,
                shelter,
                gender,
                race,
                ethnicity,
                is_active,
                created_at
            )
            VALUES (
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                TRUE,
                NOW()
            )
            RETURNING id
            """,
            (
                resident_identifier,
                resident_code,
                data["first_name"],
                data["last_name"],
                data["birth_year"],
                data["phone"],
                data["email"],
                data["emergency_contact_name"],
                data["emergency_contact_relationship"],
                data["emergency_contact_phone"],
                shelter,
                data["gender"],
                data["race"],
                data["ethnicity"],
            ),
        )
        return int(row["id"]), resident_identifier, resident_code

    db_execute(
        f"""
        INSERT INTO residents
        (
            resident_identifier,
            resident_code,
            first_name,
            last_name,
            birth_year,
            phone,
            email,
            emergency_contact_name,
            emergency_contact_relationship,
            emergency_contact_phone,
            shelter,
            gender,
            race,
            ethnicity,
            is_active,
            created_at
        )
        VALUES (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            1,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_identifier,
            resident_code,
            data["first_name"],
            data["last_name"],
            data["birth_year"],
            data["phone"],
            data["email"],
            data["emergency_contact_name"],
            data["emergency_contact_relationship"],
            data["emergency_contact_phone"],
            shelter,
            data["gender"],
            data["race"],
            data["ethnicity"],
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"]), resident_identifier, resident_code


def _insert_program_enrollment(resident_id: int, data: dict[str, object], shelter: str) -> int:
    ph = placeholder()

    if g.get("db_kind") == "pg":
        row = db_fetchone(
            f"""
            INSERT INTO program_enrollments
            (
                resident_id,
                shelter,
                program_status,
                entry_date,
                created_at,
                updated_at
            )
            VALUES (
                {ph},
                {ph},
                {ph},
                {ph},
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                resident_id,
                shelter,
                data["program_status"] or "active",
                data["entry_date"],
            ),
        )
        return int(row["id"])

    db_execute(
        f"""
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            program_status,
            entry_date,
            created_at,
            updated_at
        )
        VALUES (
            {ph},
            {ph},
            {ph},
            {ph},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            resident_id,
            shelter,
            data["program_status"] or "active",
            data["entry_date"],
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _insert_intake_assessment(enrollment_id: int, data: dict[str, object]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                sobriety_date,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                place_staying_before_entry,
                entry_felony_conviction,
                entry_parole_probation,
                drug_court,
                sexual_survivor,
                dv_survivor,
                human_trafficking_survivor,
                warrants_unpaid,
                mh_exam_completed,
                med_exam_completed,
                car_at_entry,
                car_insurance_at_entry,
                pregnant_at_entry,
                dental_need_at_entry,
                vision_need_at_entry,
                employment_status_at_entry,
                mental_health_need_at_entry,
                medical_need_at_entry,
                substance_use_need_at_entry,
                id_documents_status_at_entry,
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
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
                {ph},
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
                enrollment_id,
                data["city"],
                data["last_zipcode_residence"],
                data["length_of_time_in_amarillo"],
                data["income_at_entry"],
                data["education_at_entry"],
                data["sobriety_date"],
                data["drug_of_choice"],
                data["ace_score"],
                data["grit_score"],
                yes_no_to_int(data["veteran"]),
                yes_no_to_int(data["disability"]),
                data["marital_status"],
                data["prior_living"],
                yes_no_to_int(data["felony_history"]),
                yes_no_to_int(data["probation_parole"]),
                yes_no_to_int(data["drug_court"]),
                yes_no_to_int(data["sexual_survivor"]),
                yes_no_to_int(data["domestic_violence_history"]),
                yes_no_to_int(data["human_trafficking_history"]),
                yes_no_to_int(data["warrants_unpaid"]),
                yes_no_to_int(data["mh_exam_completed"]),
                yes_no_to_int(data["med_exam_completed"]),
                yes_no_to_int(data["car_at_entry"]),
                yes_no_to_int(data["car_insurance_at_entry"]),
                yes_no_to_int(data["pregnant"]),
                yes_no_to_int(data["dental_need"]),
                yes_no_to_int(data["vision_need"]),
                data["employment_status"],
                yes_no_to_int(data["mental_health_need"]),
                yes_no_to_int(data["medical_need"]),
                yes_no_to_int(data["substance_use_need"]),
                data["id_documents_status"],
                now,
                now,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO intake_assessments
        (
            enrollment_id,
            city,
            last_zipcode_residence,
            length_of_time_in_amarillo,
            income_at_entry,
            education_at_entry,
            sobriety_date,
            drug_of_choice,
            ace_score,
            grit_score,
            veteran,
            disability,
            marital_status,
            place_staying_before_entry,
            entry_felony_conviction,
            entry_parole_probation,
            drug_court,
            sexual_survivor,
            dv_survivor,
            human_trafficking_survivor,
            warrants_unpaid,
            mh_exam_completed,
            med_exam_completed,
            car_at_entry,
            car_insurance_at_entry,
            pregnant_at_entry,
            dental_need_at_entry,
            vision_need_at_entry,
            employment_status_at_entry,
            mental_health_need_at_entry,
            medical_need_at_entry,
            substance_use_need_at_entry,
            id_documents_status_at_entry,
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
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
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
            enrollment_id,
            data["city"],
            data["last_zipcode_residence"],
            data["length_of_time_in_amarillo"],
            data["income_at_entry"],
            data["education_at_entry"],
            data["sobriety_date"],
            data["drug_of_choice"],
            data["ace_score"],
            data["grit_score"],
            yes_no_to_int(data["veteran"]),
            yes_no_to_int(data["disability"]),
            data["marital_status"],
            data["prior_living"],
            yes_no_to_int(data["felony_history"]),
            yes_no_to_int(data["probation_parole"]),
            yes_no_to_int(data["drug_court"]),
            yes_no_to_int(data["sexual_survivor"]),
            yes_no_to_int(data["domestic_violence_history"]),
            yes_no_to_int(data["human_trafficking_history"]),
            yes_no_to_int(data["warrants_unpaid"]),
            yes_no_to_int(data["mh_exam_completed"]),
            yes_no_to_int(data["med_exam_completed"]),
            yes_no_to_int(data["car_at_entry"]),
            yes_no_to_int(data["car_insurance_at_entry"]),
            yes_no_to_int(data["pregnant"]),
            yes_no_to_int(data["dental_need"]),
            yes_no_to_int(data["vision_need"]),
            data["employment_status"],
            yes_no_to_int(data["mental_health_need"]),
            yes_no_to_int(data["medical_need"]),
            yes_no_to_int(data["substance_use_need"]),
            data["id_documents_status"],
            now,
            now,
        ),
    )


def _insert_family_snapshot(enrollment_id: int, data: dict[str, object]) -> None:
    ph = placeholder()

    kids_at_dwc = data["children_count"] if data["has_children"] == "yes" and data["children_count"] is not None else 0
    healthy_babies_born_at_dwc = 1 if data["newborn_at_dwc"] == "yes" else 0

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO family_snapshots
            (
                enrollment_id,
                kids_at_dwc,
                healthy_babies_born_at_dwc,
                created_at,
                updated_at
            )
            VALUES
            (
                {ph},
                {ph},
                {ph},
                NOW(),
                NOW()
            )
            """,
            (
                enrollment_id,
                kids_at_dwc,
                healthy_babies_born_at_dwc,
            ),
        )
        return

    db_execute(
        f"""
        INSERT INTO family_snapshots
        (
            enrollment_id,
            kids_at_dwc,
            healthy_babies_born_at_dwc,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            enrollment_id,
            kids_at_dwc,
            healthy_babies_born_at_dwc,
        ),
    )


# ============================================================================
# Index and Intake Landing Routes
# ----------------------------------------------------------------------------
# Future extraction target:
# routes.case_management_parts.index
# ============================================================================

@case_management.get("/")
@require_login
@require_shelter
def index():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))

    residents = db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            is_active
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    return render_template(
        "case_management/index.html",
        residents=residents,
        shelter=shelter,
    )


@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_index():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    assessment_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            updated_at
        FROM assessment_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    return render_template(
        "intake_assessment/index.html",
        drafts=drafts,
        assessment_drafts=assessment_drafts,
        shelter=shelter,
    )


# ============================================================================
# Assessment Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.assessment
# ============================================================================

@case_management.get("/assessment/new")
@require_login
@require_shelter
def assessment_form():
    return assessment_form_view()


@case_management.post("/assessment/new")
@require_login
@require_shelter
def submit_assessment():
    return submit_assessment_view()


# ============================================================================
# Intake Routes
# ----------------------------------------------------------------------------
# These routes display the intake form, save intake drafts, detect duplicates,
# create the resident, create the enrollment, and insert the entry snapshot.
# ============================================================================

@case_management.get("/intake-assessment/new")
@require_login
@require_shelter
def intake_form():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    draft_id = parse_int(request.args.get("draft_id"))
    form_data: dict[str, Any] | None = None

    if draft_id is not None:
        form_data = _load_intake_draft(current_shelter, draft_id)
        if not form_data:
            flash("Intake draft not found.", "error")
            return redirect(url_for("case_management.intake_index"))

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
        ),
    )


@case_management.post("/intake-assessment/new")
@require_login
@require_shelter
def submit_intake_assessment():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "complete").strip().lower()
    draft_id = parse_int(request.form.get("draft_id"))

    if action == "save_draft":
        first_name = clean(request.form.get("first_name"))
        last_name = clean(request.form.get("last_name"))

        if not first_name or not last_name:
            flash("Save Draft requires at least first name and last name.", "error")
            return render_template(
                "case_management/intake_assessment.html",
                **_intake_template_context(
                    current_shelter=current_shelter,
                    form_data=request.form.to_dict(flat=True),
                ),
            )

        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=request.form,
            draft_id=draft_id,
        )

        flash("Intake draft saved.", "success")
        return redirect(url_for("case_management.intake_form", draft_id=saved_draft_id))

    data, errors = _validate_intake_form(request.form, current_shelter)

    duplicate = _find_possible_duplicate(
        first_name=data["first_name"],
        last_name=data["last_name"],
        birth_year=data["birth_year"],
        phone=data["phone"],
        email=data["email"],
        shelter=current_shelter,
        shelter_equals_sql=shelter_equals_sql,
    )

    if duplicate:
        duplicate_id = duplicate["id"] if isinstance(duplicate, dict) else duplicate[0]
        duplicate_identifier = duplicate["resident_identifier"] if isinstance(duplicate, dict) else duplicate[6]
        if duplicate_identifier:
            flash(
                f"Possible duplicate resident found. Existing Resident ID: {duplicate_identifier}. Review that profile before creating a new one.",
                "error",
            )
        else:
            flash(
                "Possible duplicate resident found. Review the existing profile before creating a new one.",
                "error",
            )
        return redirect(url_for("case_management.resident_case", resident_id=duplicate_id))

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/intake_assessment.html",
            **_intake_template_context(
                current_shelter=current_shelter,
                form_data=request.form.to_dict(flat=True),
            ),
        )

    resident_id, resident_identifier, resident_code = _insert_resident(data, current_shelter)
    enrollment_id = _insert_program_enrollment(resident_id, data, current_shelter)
    _insert_intake_assessment(enrollment_id, data)
    _insert_family_snapshot(enrollment_id, data)

    if draft_id is not None:
        _complete_intake_draft(draft_id)

    flash(
        f"Resident created successfully. Resident ID: {resident_identifier}. Resident Code: {resident_code}",
        "success",
    )
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - START
# ----------------------------------------------------------------------------
# PURPOSE:
# This temporary admin-only route wipes resident-related test data so intake
# can be retested from a clean state during development.
#
# IMPORTANT:
# Delete everything from the START comment above to the END comment below after
# testing is complete. Do not leave this route in production long term.
#
# WHAT IT DELETES:
# - family_snapshots
# - intake_assessments
# - assessment_drafts
# - intake_drafts
# - case_manager_updates
# - appointments
# - goals
# - resident_children
# - resident_substances
# - program_enrollments
# - residents
# ============================================================================

@case_management.route("/admin/wipe-test-residents", methods=["GET", "POST"])
@require_login
@require_shelter
def wipe_test_residents():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("case_management.index"))

    init_db()

    try:
        db_execute("DELETE FROM family_snapshots")
        db_execute("DELETE FROM intake_assessments")
        db_execute("DELETE FROM assessment_drafts")
        db_execute("DELETE FROM intake_drafts")
        db_execute("DELETE FROM case_manager_updates")
        db_execute("DELETE FROM appointments")
        db_execute("DELETE FROM goals")
        db_execute("DELETE FROM resident_transfers")
        db_execute("DELETE FROM resident_children")
        db_execute("DELETE FROM resident_substances")
        db_execute("DELETE FROM program_enrollments")
        db_execute("DELETE FROM residents")

        flash("All resident-related test data was wiped.", "success")
    except Exception as e:
        flash(f"Wipe failed: {e}", "error")

    return redirect(url_for("case_management.index"))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - END
# ============================================================================


# ============================================================================
# Resident Case Page
# ----------------------------------------------------------------------------
# This route shows the resident summary page with:
# - latest enrollment
# - goals
# - appointments
# - case manager notes
# ============================================================================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = None
    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    goals = []
    appointments = []
    notes = []

    if enrollment_id:
        goals = db_fetchall(
            f"""
            SELECT
                goal_text,
                status,
                target_date,
                created_at
            FROM goals
            WHERE enrollment_id = {ph}
            ORDER BY created_at DESC
            """,
            (enrollment_id,),
        )

        appointments = db_fetchall(
            f"""
            SELECT
                appointment_date,
                appointment_type,
                notes
            FROM appointments
            WHERE enrollment_id = {ph}
            ORDER BY appointment_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        notes = db_fetchall(
            f"""
            SELECT
                meeting_date,
                notes,
                progress_notes,
                action_items,
                created_at
            FROM case_manager_updates
            WHERE enrollment_id = {ph}
            ORDER BY meeting_date DESC, id DESC
            """,
            (enrollment_id,),
        )

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        goals=goals,
        appointments=appointments,
        notes=notes,
    )
