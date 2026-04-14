from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.residents import generate_resident_code, generate_resident_identifier

CHICAGO_TZ = ZoneInfo("America/Chicago")

DEMO_PREFIX = "demo-seed-20260406"
DEMO_NOTE = "Demo seed data created from the admin tools page."
DEMO_EMAIL_DOMAIN = "example.test"

SHELTERS = ["abba", "haven", "gratitude"]

FIRST_NAMES = [
    "Ava",
    "Mia",
    "Lena",
    "Grace",
    "Nora",
    "Ruby",
    "Ella",
    "Chloe",
    "Ivy",
    "Hannah",
    "Faith",
    "Jade",
    "Olivia",
    "Autumn",
    "Sophie",
    "Lucy",
    "Maya",
    "Claire",
    "Stella",
    "Naomi",
]

LAST_NAMES = [
    "Harper",
    "Brooks",
    "Collins",
    "Hayes",
    "Bennett",
    "Parker",
    "Foster",
    "Reed",
    "Morris",
    "Ward",
    "Cook",
    "Perry",
    "Ross",
    "Bell",
    "Bailey",
    "Cooper",
    "Sutton",
    "Powell",
    "Bryant",
    "Coleman",
]

GOAL_TEXTS = [
    "Complete weekly schedule and stay current with obligations",
    "Meet employment benchmark for the month",
    "Attend all required recovery meetings",
    "Save money for housing stability",
    "Complete case management action items",
    "Improve inspection readiness",
    "Maintain consistent transportation planning",
    "Increase work hours and productive hours",
]

APPOINTMENT_TYPES = [
    "Case Management",
    "Medical",
    "Counseling",
    "Employment Follow Up",
    "Legal",
    "Housing",
]

SERVICE_TYPES = [
    "Bus Pass",
    "Case Management",
    "Clothing",
    "Food Assistance",
    "Hygiene Kit",
    "Job Search Support",
    "Recovery Support",
]

CHILD_SERVICE_TYPES = [
    "School Support",
    "Clothing",
    "Transportation",
    "Food Assistance",
]

MEDICATION_NAMES = [
    "Sertraline",
    "Hydroxyzine",
    "Metformin",
    "Lisinopril",
    "Fluoxetine",
]

RESIDENT_NEEDS = [
    ("employment", "Employment"),
    ("identification", "Identification"),
    ("mental_health", "Mental Health"),
    ("transportation", "Transportation"),
    ("benefits", "Benefits"),
    ("medical", "Medical"),
]

CHORE_SEEDS = {
    "abba": [
        "Kitchen Sweep",
        "Laundry Room",
        "Hallway Check",
        "Trash Run",
    ],
    "haven": [
        "Day Room",
        "Bathroom Check",
        "Front Entry",
        "Trash Run",
    ],
    "gratitude": [
        "Shared Area Reset",
        "Laundry Check",
        "Kitchen Wipe Down",
        "Trash Run",
    ],
}


@dataclass
class DemoResidentPlan:
    shelter: str
    ordinal: int
    first_name: str
    last_name: str
    resident_identifier: str
    resident_code: str
    email: str
    phone: str
    birth_year: int
    program_level: str
    entry_date: str
    level_start_date: str
    sobriety_date: str
    is_active: bool
    status: str
    date_exit_dwc: str | None
    graduate_dwc: bool
    reason_for_exit: str | None
    employment_status_current: str
    employment_type_current: str | None
    employer_name: str | None
    monthly_income: float
    sponsor_name: str | None
    sponsor_active: bool
    step_current: int | None


def _now_local() -> datetime:
    return datetime.now(CHICAGO_TZ)


def _utc_naive_iso_from_chicago(local_dt: datetime) -> str:
    return (
        local_dt.replace(tzinfo=CHICAGO_TZ)
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _insert_returning_id(sql: str, params: tuple) -> int:
    row = db_fetchone(sql, params)
    if not row or row.get("id") is None:
        raise RuntimeError("Insert did not return an id.")
    return int(row["id"])


def _load_staff_user_ids() -> list[int]:
    rows = db_fetchall(
        """
        SELECT id
        FROM staff_users
        WHERE is_active = TRUE
        ORDER BY
            CASE
                WHEN role = 'case_manager' THEN 0
                WHEN role = 'admin' THEN 1
                WHEN role = 'shelter_director' THEN 2
                WHEN role = 'staff' THEN 3
                ELSE 4
            END,
            id ASC
        """
    )
    ids = [int(row["id"]) for row in rows or []]
    if not ids:
        raise RuntimeError("No active staff users found.")
    return ids


def _load_activity_categories() -> dict[str, list[dict]]:
    rows = db_fetchall(
        """
        SELECT
            shelter,
            activity_label,
            counts_as_work_hours,
            counts_as_productive_hours,
            weekly_cap_hours
        FROM kiosk_activity_categories
        WHERE active = TRUE
        ORDER BY shelter ASC, sort_order ASC, id ASC
        """
    )

    bucket: dict[str, list[dict]] = {s: [] for s in SHELTERS}
    for row in rows or []:
        shelter = str(row.get("shelter") or "").strip().lower()
        if shelter not in bucket:
            continue
        bucket[shelter].append(
            {
                "activity_label": row.get("activity_label"),
                "counts_as_work_hours": bool(row.get("counts_as_work_hours")),
                "counts_as_productive_hours": bool(row.get("counts_as_productive_hours")),
                "weekly_cap_hours": (
                    float(row.get("weekly_cap_hours"))
                    if row.get("weekly_cap_hours") not in (None, "")
                    else None
                ),
            }
        )

    return bucket


def _load_required_hours() -> tuple[float, float]:
    row = db_fetchone(
        """
        SELECT
            COALESCE(pass_productive_required_hours, 35) AS productive_required_hours,
            COALESCE(pass_work_required_hours, 29) AS work_required_hours
        FROM shelter_operation_settings
        ORDER BY id ASC
        LIMIT 1
        """
    )
    if not row:
        return 35.0, 29.0
    return (
        float(row["productive_required_hours"] or 35),
        float(row["work_required_hours"] or 29),
    )


def _existing_demo_count() -> int:
    row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM residents
        WHERE resident_identifier LIKE %s
        """,
        (f"{DEMO_PREFIX}%",),
    )
    return int((row or {}).get("c") or 0)


def get_demo_seed_counts() -> dict[str, int]:
    resident_row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM residents
        WHERE resident_identifier LIKE %s
        """,
        (f"{DEMO_PREFIX}%",),
    )
    enrollment_row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM program_enrollments
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        """,
        (f"{DEMO_PREFIX}%",),
    )
    pass_row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM resident_passes
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        """,
        (f"{DEMO_PREFIX}%",),
    )
    weekly_row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM weekly_resident_summary
        WHERE enrollment_id IN (
            SELECT id
            FROM program_enrollments
            WHERE resident_id IN (
                SELECT id
                FROM residents
                WHERE resident_identifier LIKE %s
            )
        )
        """,
        (f"{DEMO_PREFIX}%",),
    )
    attendance_row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM attendance_events
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        """,
        (f"{DEMO_PREFIX}%",),
    )

    return {
        "resident_count": int((resident_row or {}).get("c") or 0),
        "enrollment_count": int((enrollment_row or {}).get("c") or 0),
        "pass_count": int((pass_row or {}).get("c") or 0),
        "weekly_summary_count": int((weekly_row or {}).get("c") or 0),
        "attendance_count": int((attendance_row or {}).get("c") or 0),
    }


def _ensure_no_existing_demo_data() -> None:
    if _existing_demo_count() > 0:
        raise RuntimeError(
            "Demo records already exist. Clear demo data first before seeding again."
        )


def _ensure_chore_templates(now_iso: str) -> dict[str, list[int]]:
    template_ids: dict[str, list[int]] = {}

    for shelter, names in CHORE_SEEDS.items():
        ids: list[int] = []
        for index, name in enumerate(names, start=1):
            row = db_fetchone(
                """
                SELECT id
                FROM chore_templates
                WHERE LOWER(COALESCE(shelter, '')) = %s
                  AND LOWER(COALESCE(name, '')) = %s
                LIMIT 1
                """,
                (shelter, name.lower()),
            )
            if row:
                ids.append(int(row["id"]))
                continue

            template_id = _insert_returning_id(
                """
                INSERT INTO chore_templates
                (
                    shelter,
                    name,
                    when_time,
                    default_day,
                    description,
                    active,
                    sort_order,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    shelter,
                    name,
                    "09:00",
                    ["Monday", "Tuesday", "Wednesday", "Thursday"][index % 4],
                    DEMO_NOTE,
                    1,
                    index,
                    now_iso,
                ),
            )
            ids.append(template_id)
        template_ids[shelter] = ids

    return template_ids


def _build_resident_plan(shelter: str, ordinal: int) -> DemoResidentPlan:
    now_local = _now_local()
    first_name = FIRST_NAMES[(ordinal - 1) % len(FIRST_NAMES)]
    last_name = f"{LAST_NAMES[(ordinal - 1) % len(LAST_NAMES)]}Demo{ordinal:02d}"

    if shelter == "gratitude":
        level_choices = ["5", "5", "6", "6", "7", "7", "8", "8"]
    else:
        level_choices = ["1", "1", "2", "2", "3", "3", "4", "4"]

    program_level = random.choice(level_choices)
    entry_days_ago = random.randint(10, 180)
    entry_dt = now_local - timedelta(days=entry_days_ago)
    level_start_dt = entry_dt + timedelta(days=random.randint(0, min(30, entry_days_ago)))
    sobriety_dt = entry_dt - timedelta(days=random.randint(5, 90))

    is_exited = ordinal in {9, 10} and shelter != "gratitude"
    date_exit_dwc = None
    graduate_dwc = False
    reason_for_exit = None
    is_active = True
    status = "active"

    if is_exited:
        exit_dt = entry_dt + timedelta(days=random.randint(15, max(20, entry_days_ago - 1)))
        if exit_dt >= now_local:
            exit_dt = now_local - timedelta(days=random.randint(2, 10))
        date_exit_dwc = exit_dt.date().isoformat()
        graduate_dwc = random.choice([False, False, True])
        reason_for_exit = random.choice(
            [
                "Left by Choice",
                "Unknown / Lost Contact",
                "Permanent Housing",
                "Transferred to Another Program",
            ]
        )
        is_active = False
        status = "inactive"

    employed = ordinal not in {2, 5, 8}
    if shelter == "haven" and ordinal in {1, 2}:
        employer_name = "RAD Program"
        employment_status_current = "Active"
        employment_type_current = "Program"
        monthly_income = 0.0
    elif employed:
        employer_name = random.choice(
            [
                "Thrift City",
                "Northside Market",
                "City Laundry",
                "Amarillo Warehouse",
                "Sunrise Cafe",
            ]
        )
        employment_status_current = "Employed"
        employment_type_current = random.choice(["Full Time", "Part Time"])
        monthly_income = float(random.choice([960, 1200, 1480, 1760, 2200]))
    else:
        employer_name = None
        employment_status_current = "Unemployed"
        employment_type_current = None
        monthly_income = 0.0

    sponsor_name = random.choice(["Pat Lewis", "Dana Cole", "Marie Hall", None, None])
    sponsor_active = sponsor_name is not None
    step_current = random.choice([1, 2, 3, 4, 5, None])

    return DemoResidentPlan(
        shelter=shelter,
        ordinal=ordinal,
        first_name=first_name,
        last_name=last_name,
        resident_identifier=f"{DEMO_PREFIX}-{shelter}-{ordinal:02d}-{generate_resident_identifier()}",
        resident_code=generate_resident_code(),
        email=f"{DEMO_PREFIX}.{shelter}.{ordinal:02d}@{DEMO_EMAIL_DOMAIN}",
        phone=f"806555{ordinal:04d}"[-10:],
        birth_year=1968 + ((ordinal * 3) % 28),
        program_level=program_level,
        entry_date=entry_dt.date().isoformat(),
        level_start_date=level_start_dt.date().isoformat(),
        sobriety_date=sobriety_dt.date().isoformat(),
        is_active=is_active,
        status=status,
        date_exit_dwc=date_exit_dwc,
        graduate_dwc=graduate_dwc,
        reason_for_exit=reason_for_exit,
        employment_status_current=employment_status_current,
        employment_type_current=employment_type_current,
        employer_name=employer_name,
        monthly_income=monthly_income,
        sponsor_name=sponsor_name,
        sponsor_active=sponsor_active,
        step_current=step_current,
    )


def _insert_resident(plan: DemoResidentPlan, now_iso: str) -> int:
    return _insert_returning_id(
        """
        INSERT INTO residents
        (
            shelter,
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
            medical_alerts,
            medical_notes,
            program_level,
            level_start_date,
            sponsor_name,
            sponsor_active,
            sobriety_date,
            drug_of_choice,
            employer_name,
            employment_status_current,
            employment_type_current,
            unemployment_reason,
            employment_notes,
            monthly_income,
            employment_updated_at,
            step_current,
            step_work_active,
            step_changed_at,
            is_active,
            created_at,
            gender,
            race,
            ethnicity,
            veteran,
            disability,
            marital_status,
            city,
            last_zipcode_of_residence,
            place_staying_before_entry,
            length_of_time_in_amarillo_upon_entry,
            date_entered,
            date_exit_dwc,
            graduate_dwc,
            reason_for_exit,
            leave_ama_upon_exit,
            status,
            updated_at,
            sms_opt_in,
            sms_opt_in_at,
            sms_opt_in_source
        )
        VALUES
        (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            plan.shelter,
            plan.resident_identifier,
            plan.resident_code,
            plan.first_name,
            plan.last_name,
            plan.birth_year,
            plan.phone,
            plan.email,
            f"Emergency {plan.last_name}",
            "Family",
            "8065559090",
            "Demo medical alert",
            DEMO_NOTE,
            plan.program_level,
            plan.level_start_date,
            plan.sponsor_name,
            plan.sponsor_active,
            plan.sobriety_date,
            random.choice(["Alcohol", "Meth", "Opioids", "None Reported"]),
            plan.employer_name,
            plan.employment_status_current,
            plan.employment_type_current,
            "Seeking work" if plan.employment_status_current == "Unemployed" else None,
            DEMO_NOTE,
            plan.monthly_income,
            now_iso,
            plan.step_current,
            bool(plan.step_current),
            now_iso,
            plan.is_active,
            now_iso,
            random.choice(["Female", "Male"]),
            random.choice(["White", "Black", "Multi Racial", "Other"]),
            random.choice(["Non Hispanic", "Hispanic"]),
            random.choice([True, False]),
            random.choice([True, False]),
            random.choice(["Single", "Divorced", "Separated"]),
            "Amarillo",
            random.choice(["79106", "79107", "79109", "79110"]),
            random.choice(["Shelter", "Friend", "Street", "Hotel"]),
            random.choice(["Less than 30 days", "30 to 90 days", "Over 90 days"]),
            plan.entry_date,
            plan.date_exit_dwc,
            plan.graduate_dwc,
            plan.reason_for_exit,
            False,
            plan.status,
            now_iso,
            True,
            now_iso,
            "demo_seed",
        ),
    )


def _insert_enrollment(
    resident_id: int, plan: DemoResidentPlan, staff_user_id: int, now_iso: str
) -> int:
    return _insert_returning_id(
        """
        INSERT INTO program_enrollments
        (
            resident_id,
            shelter,
            entry_date,
            exit_date,
            program_status,
            case_manager_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            resident_id,
            plan.shelter,
            plan.entry_date,
            plan.date_exit_dwc,
            "active" if plan.is_active else "exited",
            staff_user_id,
            now_iso,
            plan.date_exit_dwc or now_iso,
        ),
    )


def _maybe_insert_children(
    resident_id: int, enrollment_id: int, plan: DemoResidentPlan, staff_user_id: int, now_iso: str
) -> list[int]:
    child_ids: list[int] = []
    if plan.ordinal % 3 != 0:
        return child_ids

    child_count = 2 if plan.ordinal % 6 == 0 else 1
    current_year = _now_local().year

    for index in range(child_count):
        child_birth_year = min(plan.birth_year + 20 + index, current_year - 1)
        child_id = _insert_returning_id(
            """
            INSERT INTO resident_children
            (
                resident_id,
                child_name,
                birth_year,
                relationship,
                living_status,
                receives_survivor_benefit,
                survivor_benefit_amount,
                survivor_benefit_notes,
                is_active,
                notes,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                resident_id,
                f"Child Demo {plan.ordinal:02d}{index + 1}",
                child_birth_year,
                "Child",
                random.choice(["With Resident", "With Family", "Shared Custody"]),
                index == 0,
                125.0 if index == 0 else None,
                DEMO_NOTE if index == 0 else None,
                True,
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )
        child_ids.append(child_id)

        if index == 0:
            db_execute(
                """
                INSERT INTO resident_child_income_supports
                (
                    child_id,
                    support_type,
                    monthly_amount,
                    notes,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    child_id,
                    "Survivor Benefit",
                    125.0,
                    DEMO_NOTE,
                    True,
                    now_iso,
                    now_iso,
                ),
            )

        db_execute(
            """
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
                is_deleted,
                deleted_at,
                deleted_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                child_id,
                enrollment_id,
                (_now_local() - timedelta(days=random.randint(5, 40))).date().isoformat(),
                random.choice(CHILD_SERVICE_TYPES),
                "Completed",
                1,
                "visit",
                DEMO_NOTE,
                False,
                None,
                None,
                now_iso,
                now_iso,
            ),
        )

    return child_ids


def _insert_substances(resident_id: int, now_iso: str) -> None:
    primary = random.choice(["Alcohol", "Meth", "Opioids", "Cocaine"])
    db_execute(
        """
        INSERT INTO resident_substances
        (
            resident_id,
            substance,
            is_primary,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (resident_id, primary, True, now_iso, now_iso),
    )

    if random.choice([True, False]):
        db_execute(
            """
            INSERT INTO resident_substances
            (
                resident_id,
                substance,
                is_primary,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                random.choice(["Nicotine", "Marijuana", "Benzodiazepines"]),
                False,
                now_iso,
                now_iso,
            ),
        )


def _current_week_monday_local() -> datetime:
    now_local = _now_local()
    return (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _week_start_local(weeks_ago: int) -> datetime:
    return _current_week_monday_local() - timedelta(days=7 * weeks_ago)


def _choose_week_targets(
    ordinal: int, productive_required: float, work_required: float
) -> tuple[float, float]:
    bucket = ordinal % 5
    if bucket == 0:
        return round(productive_required + random.uniform(2, 9), 1), round(
            work_required + random.uniform(2, 8), 1
        )
    if bucket == 1:
        return round(productive_required + random.uniform(0, 3), 1), round(
            work_required + random.uniform(0, 3), 1
        )
    if bucket == 2:
        return round(productive_required - random.uniform(1, 4), 1), round(
            work_required - random.uniform(1, 4), 1
        )
    if bucket == 3:
        return round(productive_required - random.uniform(6, 14), 1), round(
            work_required - random.uniform(6, 10), 1
        )
    return round(productive_required + random.uniform(1, 6), 1), round(
        work_required + random.uniform(0, 4), 1
    )


def _split_hours(total_hours: float, parts: int) -> list[float]:
    if total_hours <= 0 or parts <= 0:
        return []
    base = round(total_hours / parts, 2)
    values = [base for _ in range(parts)]
    diff = round(total_hours - sum(values), 2)

    index = 0
    while abs(diff) >= 0.01:
        step = 0.25 if diff > 0 else -0.25
        values[index % parts] = round(max(0.5, values[index % parts] + step), 2)
        diff = round(total_hours - sum(values), 2)
        index += 1
        if index > 200:
            break

    return values


def _insert_attendance_event(
    resident_id: int,
    shelter: str,
    staff_user_id: int,
    destination: str,
    start_local: datetime,
    duration_hours: float,
    note: str,
) -> None:
    end_local = start_local + timedelta(hours=duration_hours)
    start_iso = _utc_naive_iso_from_chicago(start_local)
    end_iso = _utc_naive_iso_from_chicago(end_local)

    db_execute(
        """
        INSERT INTO attendance_events
        (
            resident_id,
            shelter,
            event_type,
            event_time,
            staff_user_id,
            note,
            expected_back_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            shelter,
            "check_out",
            start_iso,
            staff_user_id,
            note,
            end_iso,
            destination,
            start_iso,
            end_iso,
            end_iso,
        ),
    )


def _seed_attendance_and_weekly_summary(
    resident_id: int,
    enrollment_id: int,
    shelter: str,
    ordinal: int,
    weeks: int,
    staff_user_id: int,
    activity_map: dict[str, list[dict]],
    productive_required: float,
    work_required: float,
    now_iso: str,
) -> None:
    categories = activity_map.get(shelter) or []
    if not categories:
        return

    employment_label = next(
        (row["activity_label"] for row in categories if row["activity_label"] == "Employment"),
        categories[0]["activity_label"],
    )
    productive_only_labels = [
        row["activity_label"]
        for row in categories
        if row["counts_as_productive_hours"] and not row["counts_as_work_hours"]
    ]
    capped_lookup = {row["activity_label"]: row["weekly_cap_hours"] for row in categories}

    for weeks_ago in range(1, weeks + 1):
        start_of_week = _week_start_local(weeks_ago)
        target_productive, target_work = _choose_week_targets(
            ordinal + weeks_ago,
            productive_required,
            work_required,
        )

        work_hours = max(0.0, min(target_work, target_productive))
        productive_extra = max(0.0, round(target_productive - work_hours, 1))

        work_blocks = _split_hours(work_hours, 5 if work_hours >= 20 else 4)
        for day_index, block_hours in enumerate(work_blocks):
            start_local = start_of_week + timedelta(days=day_index, hours=8 + (day_index % 2))
            _insert_attendance_event(
                resident_id=resident_id,
                shelter=shelter,
                staff_user_id=staff_user_id,
                destination=employment_label,
                start_local=start_local,
                duration_hours=block_hours,
                note=DEMO_NOTE,
            )

        remaining_extra = productive_extra
        meeting_count = 0
        day_offset = 0

        for label in productive_only_labels:
            if remaining_extra <= 0:
                break
            suggested_hours = capped_lookup.get(label) or (
                1.5
                if label in {"AA or NA Meeting", "Church"}
                else 1.0
                if label in {"Counseling", "Doctor Appointment", "Sponsor Meeting"}
                else 2.0
                if label == "Job Search"
                else 1.0
            )
            hours = round(min(remaining_extra, float(suggested_hours)), 2)
            if hours <= 0:
                continue
            start_local = start_of_week + timedelta(days=min(day_offset, 6), hours=17)
            _insert_attendance_event(
                resident_id=resident_id,
                shelter=shelter,
                staff_user_id=staff_user_id,
                destination=label,
                start_local=start_local,
                duration_hours=hours,
                note=DEMO_NOTE,
            )
            remaining_extra = round(remaining_extra - hours, 2)
            day_offset += 1
            if label in {"AA or NA Meeting", "Church", "Sponsor Meeting"}:
                meeting_count += 1

        week_start_text = start_of_week.date().isoformat()
        submitted_at = _utc_naive_iso_from_chicago(start_of_week + timedelta(days=6, hours=18))
        payload = {
            "demo_seed": True,
            "resident_id": resident_id,
            "enrollment_id": enrollment_id,
            "shelter": shelter,
            "week_start": week_start_text,
            "productive_hours": round(target_productive, 2),
            "work_hours": round(work_hours, 2),
            "meeting_count": meeting_count,
            "note": DEMO_NOTE,
        }

        submission_id = _insert_returning_id(
            """
            INSERT INTO resident_form_submissions
            (
                resident_id,
                enrollment_id,
                form_type,
                form_source,
                source_form_id,
                source_submission_id,
                submitted_at,
                raw_payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                resident_id,
                enrollment_id,
                "weekly_compliance",
                "demo_seed",
                "demo_seed_form",
                f"{DEMO_PREFIX}-submission-{resident_id}-{weeks_ago}",
                submitted_at,
                json.dumps(payload),
                now_iso,
            ),
        )

        db_execute(
            """
            INSERT INTO weekly_resident_summary
            (
                enrollment_id,
                submission_id,
                week_start,
                productive_hours,
                work_hours,
                meeting_count,
                submitted_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                enrollment_id,
                submission_id,
                week_start_text,
                round(target_productive, 2),
                round(work_hours, 2),
                meeting_count,
                submitted_at,
                now_iso,
                now_iso,
            ),
        )


def _seed_case_management(
    resident_id: int,
    enrollment_id: int,
    child_ids: list[int],
    plan: DemoResidentPlan,
    staff_user_id: int,
    now_iso: str,
) -> None:
    note_dates = [
        (_now_local() - timedelta(days=45)).date().isoformat(),
        (_now_local() - timedelta(days=21)).date().isoformat(),
        (_now_local() - timedelta(days=7)).date().isoformat(),
    ]

    for note_date in note_dates:
        case_update_id = _insert_returning_id(
            """
            INSERT INTO case_manager_updates
            (
                enrollment_id,
                staff_user_id,
                meeting_date,
                notes,
                progress_notes,
                setbacks_or_incidents,
                action_items,
                next_appointment,
                overall_summary,
                updated_grit,
                parenting_class_completed,
                warrants_or_fines_paid,
                ready_for_next_level,
                recommended_next_level,
                blocker_reason,
                override_or_exception,
                staff_review_note,
                created_at,
                updated_at
            )
            VALUES
            (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                enrollment_id,
                staff_user_id,
                note_date,
                f"Case note for {plan.first_name} {plan.last_name}. {DEMO_NOTE}",
                random.choice(
                    [
                        "Resident stayed engaged this week",
                        "Resident followed through on assigned tasks",
                        "Resident needs more consistency with scheduling",
                    ]
                ),
                random.choice(
                    [None, "Minor attendance lapse", "Needed reminder about responsibilities"]
                ),
                "Follow up on appointments and work schedule",
                (_now_local() + timedelta(days=random.randint(2, 14))).date().isoformat(),
                "Demo seeded update",
                random.randint(1, 10),
                random.choice([0, 1]),
                random.choice([0, 1]),
                random.choice([True, False]),
                str(min(8, int(plan.program_level) + 1)) if plan.program_level.isdigit() else None,
                None,
                None,
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )

        db_execute(
            """
            INSERT INTO case_manager_update_summary
            (
                case_manager_update_id,
                change_group,
                change_type,
                item_key,
                item_label,
                old_value,
                new_value,
                detail,
                sort_order,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                case_update_id,
                "progress",
                "status",
                "program_level",
                "Program Level",
                plan.program_level,
                plan.program_level,
                DEMO_NOTE,
                1,
                now_iso,
            ),
        )

        db_execute(
            """
            INSERT INTO client_services
            (
                enrollment_id,
                case_manager_update_id,
                service_type,
                service_date,
                quantity,
                unit,
                notes,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                enrollment_id,
                case_update_id,
                random.choice(SERVICE_TYPES),
                note_date,
                1,
                "item",
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )

    need_key, need_label = random.choice(RESIDENT_NEEDS)
    db_execute(
        """
        INSERT INTO resident_needs
        (
            enrollment_id,
            need_key,
            need_label,
            source_field,
            source_value,
            status,
            resolution_note,
            resolved_at,
            resolved_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            enrollment_id,
            need_key,
            need_label,
            "demo_seed",
            "demo_seed",
            random.choice(["open", "open", "resolved"]),
            None,
            None,
            None,
            now_iso,
            now_iso,
        ),
    )

    db_execute(
        """
        INSERT INTO resident_medications
        (
            resident_id,
            enrollment_id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by,
            started_on,
            ended_on,
            is_active,
            notes,
            created_by_staff_user_id,
            updated_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            enrollment_id,
            random.choice(MEDICATION_NAMES),
            "10 mg",
            "Daily",
            "Demo purpose",
            "Demo Provider",
            (_now_local() - timedelta(days=60)).date().isoformat(),
            None,
            True,
            DEMO_NOTE,
            staff_user_id,
            staff_user_id,
            now_iso,
            now_iso,
        ),
    )

    db_execute(
        """
        INSERT INTO resident_ua_log
        (
            resident_id,
            enrollment_id,
            ua_date,
            result,
            substances_detected,
            administered_by_staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            enrollment_id,
            (_now_local() - timedelta(days=random.randint(3, 35))).date().isoformat(),
            random.choice(["negative", "negative", "negative", "positive"]),
            None,
            staff_user_id,
            DEMO_NOTE,
            now_iso,
            now_iso,
        ),
    )

    db_execute(
        """
        INSERT INTO resident_living_area_inspections
        (
            resident_id,
            enrollment_id,
            inspection_date,
            passed,
            inspected_by_staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            enrollment_id,
            (_now_local() - timedelta(days=random.randint(3, 20))).date().isoformat(),
            random.choice([True, True, False]),
            staff_user_id,
            DEMO_NOTE,
            now_iso,
            now_iso,
        ),
    )

    db_execute(
        """
        INSERT INTO resident_budget_sessions
        (
            resident_id,
            enrollment_id,
            session_date,
            staff_user_id,
            notes,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            enrollment_id,
            (_now_local() - timedelta(days=random.randint(10, 50))).date().isoformat(),
            staff_user_id,
            DEMO_NOTE,
            now_iso,
            now_iso,
        ),
    )

    if child_ids:
        db_execute(
            """
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
                is_deleted,
                deleted_at,
                deleted_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                child_ids[0],
                enrollment_id,
                (_now_local() - timedelta(days=8)).date().isoformat(),
                random.choice(CHILD_SERVICE_TYPES),
                "Completed",
                1,
                "item",
                DEMO_NOTE,
                False,
                None,
                None,
                now_iso,
                now_iso,
            ),
        )


def _seed_goals_and_appointments(enrollment_id: int, now_iso: str) -> None:
    for index in range(2):
        created_at = (_now_local() - timedelta(days=30 - (index * 10))).date().isoformat()
        target_date = (_now_local() + timedelta(days=20 + (index * 10))).date().isoformat()
        completed_date = (
            None if index == 1 else (_now_local() - timedelta(days=5)).date().isoformat()
        )

        db_execute(
            """
            INSERT INTO goals
            (
                enrollment_id,
                goal_text,
                status,
                target_date,
                completed_date,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                enrollment_id,
                random.choice(GOAL_TEXTS),
                "completed" if completed_date else "active",
                target_date,
                completed_date,
                created_at,
                now_iso,
            ),
        )

    for _ in range(2):
        appointment_date = (_now_local() + timedelta(days=random.randint(2, 20))).date().isoformat()
        db_execute(
            """
            INSERT INTO appointments
            (
                enrollment_id,
                appointment_type,
                appointment_date,
                notes,
                reminder_sent,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                enrollment_id,
                random.choice(APPOINTMENT_TYPES),
                appointment_date,
                DEMO_NOTE,
                0,
                now_iso,
                now_iso,
            ),
        )


def _seed_requests_and_passes(
    resident_id: int, plan: DemoResidentPlan, staff_user_id: int, now_iso: str
) -> None:
    if plan.ordinal % 2 == 0:
        leave_start_local = _now_local() + timedelta(days=3, hours=10)
        leave_end_local = leave_start_local + timedelta(hours=4)
        db_execute(
            """
            INSERT INTO leave_requests
            (
                shelter,
                resident_identifier,
                first_name,
                last_name,
                resident_phone,
                destination,
                reason,
                resident_notes,
                leave_at,
                return_at,
                status,
                submitted_at,
                decided_at,
                decided_by,
                decision_note,
                check_in_at,
                check_in_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                plan.shelter,
                plan.resident_identifier,
                plan.first_name,
                plan.last_name,
                plan.phone,
                "Doctor Visit",
                "Appointment",
                DEMO_NOTE,
                _utc_naive_iso_from_chicago(leave_start_local),
                _utc_naive_iso_from_chicago(leave_end_local),
                random.choice(["pending", "approved", "returned"]),
                now_iso,
                now_iso if plan.ordinal % 4 == 0 else None,
                staff_user_id if plan.ordinal % 4 == 0 else None,
                DEMO_NOTE if plan.ordinal % 4 == 0 else None,
                None,
                None,
            ),
        )

    if plan.ordinal % 3 == 0:
        needed_local = _now_local() + timedelta(days=2, hours=9)
        db_execute(
            """
            INSERT INTO transport_requests
            (
                shelter,
                resident_identifier,
                first_name,
                last_name,
                needed_at,
                pickup_location,
                destination,
                reason,
                resident_notes,
                callback_phone,
                status,
                submitted_at,
                scheduled_at,
                scheduled_by,
                driver_name,
                staff_notes,
                completed_at,
                completed_by,
                cancelled_at,
                cancelled_by,
                cancel_reason
            )
            VALUES
            (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.shelter,
                plan.resident_identifier,
                plan.first_name,
                plan.last_name,
                _utc_naive_iso_from_chicago(needed_local),
                "DWC",
                "Medical Office",
                "Appointment",
                DEMO_NOTE,
                plan.phone,
                random.choice(["pending", "scheduled", "completed"]),
                now_iso,
                now_iso if plan.ordinal % 6 == 0 else None,
                staff_user_id if plan.ordinal % 6 == 0 else None,
                "Demo Driver" if plan.ordinal % 6 == 0 else None,
                DEMO_NOTE if plan.ordinal % 6 == 0 else None,
                None,
                None,
                None,
                None,
                None,
            ),
        )

    pass_type = random.choice(["pass", "overnight", "special"])
    status = random.choice(["pending", "approved", "denied"])

    start_at = None
    end_at = None
    start_date = None
    end_date = None

    if pass_type in {"pass", "overnight"}:
        leave_local = _now_local() + timedelta(days=5, hours=10)
        return_local = leave_local + timedelta(hours=6 if pass_type == "pass" else 28)
        start_at = _utc_naive_iso_from_chicago(leave_local)
        end_at = _utc_naive_iso_from_chicago(return_local)
    else:
        special_start = (_now_local() + timedelta(days=5)).date()
        special_end = special_start + timedelta(days=1)
        start_date = special_start.isoformat()
        end_date = special_end.isoformat()

    pass_id = _insert_returning_id(
        """
        INSERT INTO resident_passes
        (
            resident_id,
            shelter,
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            reason,
            resident_notes,
            staff_notes,
            approved_by,
            approved_at,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            resident_id,
            plan.shelter,
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            "Family Visit",
            "Demo pass request",
            DEMO_NOTE,
            DEMO_NOTE if status != "pending" else None,
            staff_user_id if status == "approved" else None,
            now_iso if status == "approved" else None,
            now_iso,
            now_iso,
        ),
    )

    db_execute(
        """
        INSERT INTO resident_pass_request_details
        (
            pass_id,
            resident_phone,
            request_date,
            resident_level,
            requirements_acknowledged,
            requirements_not_met_explanation,
            reason_for_request,
            who_with,
            destination_address,
            destination_phone,
            companion_names,
            companion_phone_numbers,
            budgeted_amount,
            approved_amount,
            reviewed_by_user_id,
            reviewed_by_name,
            reviewed_at,
            created_at,
            updated_at
        )
        VALUES
        (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            pass_id,
            plan.phone,
            _now_local().date().isoformat(),
            plan.program_level,
            "yes",
            None,
            "Demo pass request",
            "Family",
            "123 Demo St",
            "8065552222",
            "Demo Companion",
            "8065553333",
            "40",
            "40" if status == "approved" else None,
            staff_user_id if status != "pending" else None,
            "Demo Reviewer" if status != "pending" else None,
            now_iso if status != "pending" else None,
            now_iso,
            now_iso,
        ),
    )


def _seed_chore_assignments(
    resident_id: int, shelter: str, chore_template_ids: dict[str, list[int]], now_iso: str
) -> None:
    template_ids = chore_template_ids.get(shelter, [])
    for offset, template_id in enumerate(template_ids[:2]):
        db_execute(
            """
            INSERT INTO chore_assignments
            (
                resident_id,
                chore_id,
                assigned_date,
                status,
                notes,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                template_id,
                (_now_local() - timedelta(days=offset * 7)).date().isoformat(),
                random.choice(["assigned", "completed", "assigned"]),
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )


def _seed_transfer_history(resident_id: int, shelter: str, now_iso: str) -> None:
    prior = "abba" if shelter == "haven" else "haven" if shelter == "gratitude" else "gratitude"
    if random.choice([True, False]):
        db_execute(
            """
            INSERT INTO resident_transfers
            (
                resident_id,
                from_shelter,
                to_shelter,
                transferred_by,
                transferred_at,
                note
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                prior,
                shelter,
                "demo_seed",
                now_iso,
                DEMO_NOTE,
            ),
        )


def run_demo_seed(per_shelter: int = 10, weeks: int = 12) -> dict[str, int]:
    _ensure_no_existing_demo_data()

    now_iso = utcnow_iso()
    staff_user_ids = _load_staff_user_ids()
    activity_map = _load_activity_categories()
    productive_required, work_required = _load_required_hours()
    chore_template_ids = _ensure_chore_templates(now_iso)

    total_residents = 0

    with db_transaction():
        for shelter in SHELTERS:
            for ordinal in range(1, per_shelter + 1):
                plan = _build_resident_plan(shelter, ordinal)
                staff_user_id = staff_user_ids[(ordinal - 1) % len(staff_user_ids)]

                resident_id = _insert_resident(plan, now_iso)
                enrollment_id = _insert_enrollment(resident_id, plan, staff_user_id, now_iso)
                child_ids = _maybe_insert_children(
                    resident_id, enrollment_id, plan, staff_user_id, now_iso
                )

                _insert_substances(resident_id, now_iso)
                _seed_attendance_and_weekly_summary(
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                    shelter=shelter,
                    ordinal=ordinal,
                    weeks=weeks,
                    staff_user_id=staff_user_id,
                    activity_map=activity_map,
                    productive_required=productive_required,
                    work_required=work_required,
                    now_iso=now_iso,
                )
                _seed_case_management(
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                    child_ids=child_ids,
                    plan=plan,
                    staff_user_id=staff_user_id,
                    now_iso=now_iso,
                )
                _seed_goals_and_appointments(enrollment_id, now_iso)
                _seed_requests_and_passes(resident_id, plan, staff_user_id, now_iso)
                _seed_chore_assignments(resident_id, shelter, chore_template_ids, now_iso)
                _seed_transfer_history(resident_id, shelter, now_iso)

                total_residents += 1

    return {
        "resident_count": total_residents,
        "weeks_per_resident": weeks,
    }


def clear_demo_seed() -> dict[str, int]:
    resident_rows = db_fetchall(
        """
        SELECT id, resident_identifier
        FROM residents
        WHERE resident_identifier LIKE %s
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    if not resident_rows:
        return {
            "resident_count": 0,
        }

    resident_ids = [int(row["id"]) for row in resident_rows]
    resident_identifiers = [str(row["resident_identifier"]) for row in resident_rows]

    enrollment_rows = db_fetchall(
        """
        SELECT id
        FROM program_enrollments
        WHERE resident_id = ANY(%s)
        ORDER BY id ASC
        """,
        (resident_ids,),
    )
    enrollment_ids = [int(row["id"]) for row in enrollment_rows or []]

    child_rows = db_fetchall(
        """
        SELECT id
        FROM resident_children
        WHERE resident_id = ANY(%s)
        ORDER BY id ASC
        """,
        (resident_ids,),
    )
    child_ids = [int(row["id"]) for row in child_rows or []]

    pass_rows = db_fetchall(
        """
        SELECT id
        FROM resident_passes
        WHERE resident_id = ANY(%s)
        ORDER BY id ASC
        """,
        (resident_ids,),
    )
    pass_ids = [int(row["id"]) for row in pass_rows or []]

    submission_rows = db_fetchall(
        """
        SELECT id
        FROM resident_form_submissions
        WHERE resident_id = ANY(%s)
        ORDER BY id ASC
        """,
        (resident_ids,),
    )
    submission_ids = [int(row["id"]) for row in submission_rows or []]

    case_update_rows = db_fetchall(
        """
        SELECT id
        FROM case_manager_updates
        WHERE enrollment_id = ANY(%s)
        ORDER BY id ASC
        """,
        (enrollment_ids or [0],),
    )
    case_update_ids = [int(row["id"]) for row in case_update_rows or []]

    with db_transaction():
        if pass_ids:
            db_execute(
                "DELETE FROM resident_pass_request_details WHERE pass_id = ANY(%s)",
                (pass_ids,),
            )

        if submission_ids:
            db_execute(
                "DELETE FROM weekly_resident_summary WHERE submission_id = ANY(%s)",
                (submission_ids,),
            )

        if case_update_ids:
            db_execute(
                "DELETE FROM case_manager_update_summary WHERE case_manager_update_id = ANY(%s)",
                (case_update_ids,),
            )

        if child_ids:
            db_execute(
                "DELETE FROM resident_child_income_supports WHERE child_id = ANY(%s)",
                (child_ids,),
            )
            db_execute(
                "DELETE FROM child_services WHERE resident_child_id = ANY(%s)",
                (child_ids,),
            )

        if enrollment_ids:
            db_execute(
                "DELETE FROM weekly_resident_summary WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_form_submissions WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM client_services WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM case_manager_updates WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_needs WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_medications WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_ua_log WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_living_area_inspections WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM resident_budget_sessions WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM goals WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM appointments WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )
            db_execute(
                "DELETE FROM child_services WHERE enrollment_id = ANY(%s)",
                (enrollment_ids,),
            )

        if resident_identifiers:
            db_execute(
                "DELETE FROM leave_requests WHERE resident_identifier = ANY(%s)",
                (resident_identifiers,),
            )
            db_execute(
                "DELETE FROM transport_requests WHERE resident_identifier = ANY(%s)",
                (resident_identifiers,),
            )

        if resident_ids:
            db_execute("DELETE FROM resident_passes WHERE resident_id = ANY(%s)", (resident_ids,))
            db_execute("DELETE FROM attendance_events WHERE resident_id = ANY(%s)", (resident_ids,))
            db_execute(
                "DELETE FROM resident_transfers WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute(
                "DELETE FROM resident_form_submissions WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute(
                "DELETE FROM resident_medications WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute("DELETE FROM resident_ua_log WHERE resident_id = ANY(%s)", (resident_ids,))
            db_execute(
                "DELETE FROM resident_living_area_inspections WHERE resident_id = ANY(%s)",
                (resident_ids,),
            )
            db_execute(
                "DELETE FROM resident_budget_sessions WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute("DELETE FROM chore_assignments WHERE resident_id = ANY(%s)", (resident_ids,))
            db_execute(
                "DELETE FROM resident_substances WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute("DELETE FROM resident_children WHERE resident_id = ANY(%s)", (resident_ids,))
            db_execute(
                "DELETE FROM program_enrollments WHERE resident_id = ANY(%s)", (resident_ids,)
            )
            db_execute("DELETE FROM residents WHERE id = ANY(%s)", (resident_ids,))

    return {
        "resident_count": len(resident_ids),
    }
