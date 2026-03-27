from __future__ import annotations

from typing import Any

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import yes_no_to_int
from routes.case_management_parts.needs import sync_enrollment_needs


def _insert_resident(data: dict[str, Any], shelter: str) -> tuple[int, str, str]:
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


def _insert_program_enrollment(resident_id: int, data: dict[str, Any], shelter: str) -> int:
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


def _insert_intake_assessment(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    dental_need = yes_no_to_int(data.get("dental_need"))
    vision_need = yes_no_to_int(data.get("vision_need"))
    parenting_class_needed = yes_no_to_int(data.get("parenting_class_needed"))
    warrants_unpaid = yes_no_to_int(data.get("warrants_unpaid"))
    mental_health_need = yes_no_to_int(data.get("mental_health_need"))
    medical_need = yes_no_to_int(data.get("medical_need"))
    has_drivers_license = yes_no_to_int(data.get("has_drivers_license"))
    has_social_security_card = yes_no_to_int(data.get("has_social_security_card"))

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                county,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                treatment_grad_date,
                sobriety_date,
                days_sober_at_entry,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                notes_basic,
                entry_notes,
                initial_snapshot_notes,
                trauma_notes,
                barrier_notes,
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
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                dwc_level_today,
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
                NOW(),
                NOW()
            )
            """,
            (
                enrollment_id,
                data.get("city"),
                data.get("county"),
                data.get("last_zipcode_residence"),
                data.get("length_of_time_in_amarillo"),
                data.get("income_at_entry"),
                data.get("education_at_entry"),
                data.get("treatment_grad_date"),
                data.get("sobriety_date"),
                data.get("days_sober_at_entry"),
                data.get("drug_of_choice"),
                data.get("ace_score"),
                data.get("grit_score"),
                yes_no_to_int(data.get("veteran")),
                data.get("disability") or "unknown",
                data.get("marital_status"),
                data.get("notes_basic"),
                data.get("entry_notes"),
                data.get("initial_snapshot_notes"),
                data.get("trauma_notes"),
                data.get("barrier_notes"),
                data.get("prior_living"),
                yes_no_to_int(data.get("felony_history")),
                yes_no_to_int(data.get("probation_parole")),
                yes_no_to_int(data.get("drug_court")),
                yes_no_to_int(data.get("sexual_survivor")),
                yes_no_to_int(data.get("domestic_violence_history")),
                yes_no_to_int(data.get("human_trafficking_history")),
                warrants_unpaid,
                yes_no_to_int(data.get("mh_exam_completed")),
                yes_no_to_int(data.get("med_exam_completed")),
                yes_no_to_int(data.get("car_at_entry")),
                yes_no_to_int(data.get("car_insurance_at_entry")),
                yes_no_to_int(data.get("pregnant")),
                dental_need,
                vision_need,
                data.get("employment_status"),
                mental_health_need,
                medical_need,
                yes_no_to_int(data.get("substance_use_need")),
                data.get("id_documents_status"),
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                data.get("dwc_level_today"),
            ),
        )
    else:
        db_execute(
            f"""
            INSERT INTO intake_assessments
            (
                enrollment_id,
                city,
                county,
                last_zipcode_residence,
                length_of_time_in_amarillo,
                income_at_entry,
                education_at_entry,
                treatment_grad_date,
                sobriety_date,
                days_sober_at_entry,
                drug_of_choice,
                ace_score,
                grit_score,
                veteran,
                disability,
                marital_status,
                notes_basic,
                entry_notes,
                initial_snapshot_notes,
                trauma_notes,
                barrier_notes,
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
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                dwc_level_today,
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
                data.get("city"),
                data.get("county"),
                data.get("last_zipcode_residence"),
                data.get("length_of_time_in_amarillo"),
                data.get("income_at_entry"),
                data.get("education_at_entry"),
                data.get("treatment_grad_date"),
                data.get("sobriety_date"),
                data.get("days_sober_at_entry"),
                data.get("drug_of_choice"),
                data.get("ace_score"),
                data.get("grit_score"),
                yes_no_to_int(data.get("veteran")),
                data.get("disability") or "unknown",
                data.get("marital_status"),
                data.get("notes_basic"),
                data.get("entry_notes"),
                data.get("initial_snapshot_notes"),
                data.get("trauma_notes"),
                data.get("barrier_notes"),
                data.get("prior_living"),
                yes_no_to_int(data.get("felony_history")),
                yes_no_to_int(data.get("probation_parole")),
                yes_no_to_int(data.get("drug_court")),
                yes_no_to_int(data.get("sexual_survivor")),
                yes_no_to_int(data.get("domestic_violence_history")),
                yes_no_to_int(data.get("human_trafficking_history")),
                warrants_unpaid,
                yes_no_to_int(data.get("mh_exam_completed")),
                yes_no_to_int(data.get("med_exam_completed")),
                yes_no_to_int(data.get("car_at_entry")),
                yes_no_to_int(data.get("car_insurance_at_entry")),
                yes_no_to_int(data.get("pregnant")),
                dental_need,
                vision_need,
                data.get("employment_status"),
                mental_health_need,
                medical_need,
                yes_no_to_int(data.get("substance_use_need")),
                data.get("id_documents_status"),
                has_drivers_license,
                has_social_security_card,
                parenting_class_needed,
                data.get("dwc_level_today"),
                now,
                now,
            ),
        )

    sync_enrollment_needs(
        enrollment_id,
        {
            "dental_need_at_entry": dental_need,
            "vision_need_at_entry": vision_need,
            "parenting_class_needed": parenting_class_needed,
            "warrants_unpaid": warrants_unpaid,
            "mental_health_need_at_entry": mental_health_need,
            "medical_need_at_entry": medical_need,
            "has_drivers_license": has_drivers_license,
            "has_social_security_card": has_social_security_card,
        },
    )


def _insert_family_snapshot(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO family_snapshots
        (
            enrollment_id,
            kids_at_dwc,
            kids_served_outside_under_18,
            kids_ages_0_5,
            kids_ages_6_11,
            kids_ages_12_17,
            kids_reunited_while_in_program,
            healthy_babies_born_at_dwc,
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
            enrollment_id,
            int(data.get("kids_at_dwc") or 0),
            int(data.get("kids_served_outside_under_18") or 0),
            int(data.get("kids_ages_0_5") or 0),
            int(data.get("kids_ages_6_11") or 0),
            int(data.get("kids_ages_12_17") or 0),
            int(data.get("kids_reunited_while_in_program") or 0),
            int(data.get("healthy_babies_born_at_dwc") or 0),
            now,
            now,
        ),
    )
