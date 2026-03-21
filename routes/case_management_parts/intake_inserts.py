from __future__ import annotations

from typing import Any

from flask import g

from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import yes_no_to_int


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
                days_sober_at_entry,
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
                NOW(),
                NOW()
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
                data["days_sober_at_entry"],
                data["drug_of_choice"],
                data["ace_score"],
                data["grit_score"],
                yes_no_to_int(data["veteran"]),
                data["disability"],
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
                yes_no_to_int(data["pregnant"]),
                yes_no_to_int(data["dental_need"]),
                yes_no_to_int(data["vision_need"]),
                data["employment_status"],
                yes_no_to_int(data["mental_health_need"]),
                yes_no_to_int(data["medical_need"]),
                yes_no_to_int(data["substance_use_need"]),
                data["id_documents_status"],
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
            days_sober_at_entry,
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
            data["days_sober_at_entry"],
            data["drug_of_choice"],
            data["ace_score"],
            data["grit_score"],
            yes_no_to_int(data["veteran"]),
            data["disability"],
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


def _insert_family_snapshot(enrollment_id: int, data: dict[str, Any]) -> None:
    ph = placeholder()
    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO family_snapshots
        (
            enrollment_id,
            has_children,
            children_count,
            newborn_born_at_dwc,
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
            {ph}
        )
        """,
        (
            enrollment_id,
            yes_no_to_int(data["has_children"]),
            data["children_count"],
            yes_no_to_int(data["newborn_at_dwc"]),
            now,
            now,
        ),
    )
