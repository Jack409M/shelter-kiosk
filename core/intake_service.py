from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.db import db_execute, db_fetchone, db_transaction
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident, placeholder
from routes.case_management_parts.intake_drafts import _complete_intake_draft, _save_intake_draft
from routes.case_management_parts.intake_income_support import (
    load_intake_income_support,
    upsert_intake_income_support,
)
from routes.case_management_parts.intake_inserts import (
    _build_family_snapshot_payload,
    _build_intake_assessment_payload,
    _insert_family_snapshot,
    _insert_intake_assessment,
    _insert_program_enrollment,
    _insert_resident,
)
from routes.case_management_parts.needs import (
    build_triggered_needs,
    list_enrollment_need_keys,
    sync_enrollment_needs,
)


@dataclass(slots=True)
class IntakeDuplicateStop:
    draft_id: int
    duplicate_identifier: str | None
    duplicate_first_name: str
    duplicate_last_name: str


@dataclass(slots=True)
class IntakeReviewResult:
    duplicate_stop: IntakeDuplicateStop | None = None
    approved_draft_id: int | None = None


@dataclass(slots=True)
class IntakeCreateResult:
    resident_id: int
    resident_identifier: str
    resident_code: str


@dataclass(slots=True)
class IntakeUpdateResult:
    resident_id: int
    enrollment_id: int


def duplicate_identity(duplicate: Any) -> tuple[str | None, str, str]:
    duplicate_identifier = (
        duplicate["resident_identifier"] if isinstance(duplicate, dict) else duplicate[6]
    )
    duplicate_first_name = duplicate["first_name"] if isinstance(duplicate, dict) else duplicate[2]
    duplicate_last_name = duplicate["last_name"] if isinstance(duplicate, dict) else duplicate[3]
    return duplicate_identifier, duplicate_first_name or "", duplicate_last_name or ""


def resident_enrollment_in_scope(resident_id: int, current_shelter: str):
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT *
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (resident_id, current_shelter),
    )

    if not resident:
        return None, None

    enrollment = fetch_current_enrollment_for_resident(resident_id)
    return resident, enrollment


def latest_intake_for_enrollment(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT *
        FROM intake_assessments
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


def intake_edit_form_data(
    *,
    resident: dict[str, Any],
    enrollment: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    enrollment_id = int(enrollment["id"])

    intake = db_fetchone(
        f"""
        SELECT *
        FROM intake_assessments
        WHERE enrollment_id = {placeholder()}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    family = db_fetchone(
        f"""
        SELECT *
        FROM family_snapshots
        WHERE enrollment_id = {placeholder()}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    income_support = load_intake_income_support(enrollment_id)

    form_data: dict[str, Any] = {}
    form_data.update(dict(resident))
    form_data.update(dict(enrollment))

    if intake:
        form_data.update(dict(intake))

    if family:
        form_data.update(dict(family))

    if income_support:
        form_data.update(dict(income_support))

    selected_need_keys = list_enrollment_need_keys(enrollment_id)

    if not selected_need_keys and intake:
        selected_need_keys = [
            need["need_key"] for need in build_triggered_needs(intake_row=dict(intake))
        ]

    return form_data, selected_need_keys


def save_intake_review_decision(
    *,
    current_shelter: str,
    form: Any,
    draft_id: int | None,
    data: dict[str, Any],
    duplicate: Any | None,
) -> IntakeReviewResult:
    if duplicate:
        duplicate_identifier, duplicate_first_name, duplicate_last_name = duplicate_identity(
            duplicate
        )
        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=form,
            draft_id=draft_id,
            status="pending_duplicate_review",
        )
        return IntakeReviewResult(
            duplicate_stop=IntakeDuplicateStop(
                draft_id=saved_draft_id,
                duplicate_identifier=duplicate_identifier,
                duplicate_first_name=duplicate_first_name,
                duplicate_last_name=duplicate_last_name,
            )
        )

    review_form = form.copy()
    review_form["review_passed"] = "1"

    saved_draft_id = _save_intake_draft(
        current_shelter=current_shelter,
        form=review_form,
        draft_id=draft_id,
        status="draft",
    )

    return IntakeReviewResult(approved_draft_id=saved_draft_id)


def create_intake(
    *,
    current_shelter: str,
    data: dict[str, Any],
    draft_id: int | None,
) -> IntakeCreateResult:
    with db_transaction():
        new_resident_id, resident_identifier, resident_code = _insert_resident(
            data,
            current_shelter,
        )
        enrollment_id = _insert_program_enrollment(
            new_resident_id,
            data,
            current_shelter,
        )
        _insert_intake_assessment(enrollment_id, data)
        _insert_family_snapshot(enrollment_id, data)
        upsert_intake_income_support(enrollment_id, data)
        sync_enrollment_needs(
            enrollment_id,
            selected_need_keys=data.get("entry_need_keys", []),
        )

        if draft_id is not None:
            _complete_intake_draft(draft_id)

    return IntakeCreateResult(
        resident_id=new_resident_id,
        resident_identifier=resident_identifier,
        resident_code=resident_code,
    )


def create_intake_for_existing_resident(
    *,
    current_shelter: str,
    existing_resident_id: int,
    data: dict[str, Any],
    draft_id: int | None,
) -> int:
    with db_transaction():
        enrollment_id = _insert_program_enrollment(
            existing_resident_id,
            data,
            current_shelter,
        )
        _insert_intake_assessment(enrollment_id, data)
        _insert_family_snapshot(enrollment_id, data)
        upsert_intake_income_support(enrollment_id, data)
        sync_enrollment_needs(
            enrollment_id,
            selected_need_keys=data.get("entry_need_keys", []),
        )

        if draft_id is not None:
            _complete_intake_draft(draft_id)

    return enrollment_id


def update_intake(
    *,
    resident_id: int,
    enrollment_id: int,
    data: dict[str, Any],
) -> IntakeUpdateResult:
    existing_intake = latest_intake_for_enrollment(enrollment_id)
    if not existing_intake:
        raise LookupError("No intake assessment found for update.")

    intake_assessment_id = int(existing_intake["id"])
    now = datetime.utcnow().isoformat()
    ph = placeholder()
    intake_payload = _build_intake_assessment_payload(data)
    family_payload = _build_family_snapshot_payload(data)

    with db_transaction():
        db_execute(
            f"""
            UPDATE residents
            SET
                first_name = {ph},
                last_name = {ph},
                birth_year = {ph},
                phone = {ph},
                email = {ph},
                emergency_contact_name = {ph},
                emergency_contact_relationship = {ph},
                emergency_contact_phone = {ph},
                gender = {ph},
                race = {ph},
                ethnicity = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                data.get("first_name"),
                data.get("last_name"),
                data.get("birth_year"),
                data.get("phone"),
                data.get("email"),
                data.get("emergency_contact_name"),
                data.get("emergency_contact_relationship"),
                data.get("emergency_contact_phone"),
                data.get("gender"),
                data.get("race"),
                data.get("ethnicity"),
                now,
                resident_id,
            ),
        )

        db_execute(
            f"""
            UPDATE program_enrollments
            SET
                entry_date = {ph},
                program_status = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                data.get("entry_date"),
                data.get("program_status"),
                now,
                enrollment_id,
            ),
        )

        db_execute(
            f"""
            UPDATE intake_assessments
            SET
                city = {ph},
                county = {ph},
                last_zipcode_residence = {ph},
                length_of_time_in_amarillo = {ph},
                income_at_entry = {ph},
                education_at_entry = {ph},
                treatment_grad_date = {ph},
                sobriety_date = {ph},
                days_sober_at_entry = {ph},
                drug_of_choice = {ph},
                ace_score = {ph},
                grit_score = {ph},
                veteran = {ph},
                disability = {ph},
                marital_status = {ph},
                notes_basic = {ph},
                entry_notes = {ph},
                initial_snapshot_notes = {ph},
                trauma_notes = {ph},
                barrier_notes = {ph},
                place_staying_before_entry = {ph},
                entry_felony_conviction = {ph},
                entry_parole_probation = {ph},
                drug_court = {ph},
                sexual_survivor = {ph},
                dv_survivor = {ph},
                human_trafficking_survivor = {ph},
                warrants_unpaid = {ph},
                mh_exam_completed = {ph},
                med_exam_completed = {ph},
                car_at_entry = {ph},
                car_insurance_at_entry = {ph},
                pregnant_at_entry = {ph},
                dental_need_at_entry = {ph},
                vision_need_at_entry = {ph},
                employment_status_at_entry = {ph},
                mental_health_need_at_entry = {ph},
                medical_need_at_entry = {ph},
                substance_use_need_at_entry = {ph},
                id_documents_status_at_entry = {ph},
                has_drivers_license = {ph},
                has_social_security_card = {ph},
                parenting_class_needed = {ph},
                dwc_level_today = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                intake_payload["city"],
                intake_payload["county"],
                intake_payload["last_zipcode_residence"],
                intake_payload["length_of_time_in_amarillo"],
                intake_payload["income_at_entry"],
                intake_payload["education_at_entry"],
                intake_payload["treatment_grad_date"],
                intake_payload["sobriety_date"],
                intake_payload["days_sober_at_entry"],
                intake_payload["drug_of_choice"],
                intake_payload["ace_score"],
                intake_payload["grit_score"],
                intake_payload["veteran"],
                intake_payload["disability"],
                intake_payload["marital_status"],
                intake_payload["notes_basic"],
                intake_payload["entry_notes"],
                intake_payload["initial_snapshot_notes"],
                intake_payload["trauma_notes"],
                intake_payload["barrier_notes"],
                intake_payload["place_staying_before_entry"],
                intake_payload["entry_felony_conviction"],
                intake_payload["entry_parole_probation"],
                intake_payload["drug_court"],
                intake_payload["sexual_survivor"],
                intake_payload["dv_survivor"],
                intake_payload["human_trafficking_survivor"],
                intake_payload["warrants_unpaid"],
                intake_payload["mh_exam_completed"],
                intake_payload["med_exam_completed"],
                intake_payload["car_at_entry"],
                intake_payload["car_insurance_at_entry"],
                intake_payload["pregnant_at_entry"],
                intake_payload["dental_need_at_entry"],
                intake_payload["vision_need_at_entry"],
                intake_payload["employment_status_at_entry"],
                intake_payload["mental_health_need_at_entry"],
                intake_payload["medical_need_at_entry"],
                intake_payload["substance_use_need_at_entry"],
                intake_payload["id_documents_status_at_entry"],
                intake_payload["has_drivers_license"],
                intake_payload["has_social_security_card"],
                intake_payload["parenting_class_needed"],
                intake_payload["dwc_level_today"],
                now,
                intake_assessment_id,
            ),
        )

        existing_family = db_fetchone(
            f"""
            SELECT id
            FROM family_snapshots
            WHERE enrollment_id = {ph}
            ORDER BY id DESC
            LIMIT 1
            """,
            (enrollment_id,),
        )

        if existing_family:
            db_execute(
                f"""
                UPDATE family_snapshots
                SET
                    kids_at_dwc = {ph},
                    kids_served_outside_under_18 = {ph},
                    kids_ages_0_5 = {ph},
                    kids_ages_6_11 = {ph},
                    kids_ages_12_17 = {ph},
                    kids_reunited_while_in_program = {ph},
                    healthy_babies_born_at_dwc = {ph},
                    updated_at = {ph}
                WHERE enrollment_id = {ph}
                """,
                (
                    family_payload["kids_at_dwc"],
                    family_payload["kids_served_outside_under_18"],
                    family_payload["kids_ages_0_5"],
                    family_payload["kids_ages_6_11"],
                    family_payload["kids_ages_12_17"],
                    family_payload["kids_reunited_while_in_program"],
                    family_payload["healthy_babies_born_at_dwc"],
                    now,
                    enrollment_id,
                ),
            )
        else:
            _insert_family_snapshot(enrollment_id, data)

        upsert_intake_income_support(enrollment_id, data)

        sync_enrollment_needs(
            enrollment_id,
            selected_need_keys=data.get("entry_need_keys", []),
        )

    return IntakeUpdateResult(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
    )
