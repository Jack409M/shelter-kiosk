from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from core.app_factory import create_app
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction, get_db
from core.helpers import utcnow_iso
from core.residents import generate_resident_code
from core.runtime import init_db

CHICAGO_TZ = ZoneInfo("America/Chicago")

DEMO_PREFIX = "demo-seed-20260406"
DEMO_EMAIL_DOMAIN = "example.test"
DEMO_NOTE = "Demo seed data. Safe to remove."
DEFAULT_WEEKS = 12
DEFAULT_PER_SHELTER = 10

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
    "Improve apartment inspection readiness",
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

UA_RESULTS = [
    "negative",
    "negative",
    "negative",
    "negative",
    "positive",
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

HARD_CODED_ACTIVITY_MAP = {
    "abba": [
        {
            "activity_label": "Employment",
            "counts_as_work_hours": True,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Job Search",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "AA or NA Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Church",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Doctor Appointment",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Counseling",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Step Work",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 2.0,
        },
        {
            "activity_label": "Sponsor Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 1.0,
        },
        {
            "activity_label": "Volunteer or Community Service",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "School",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Legal Obligation",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
    ],
    "haven": [
        {
            "activity_label": "Employment",
            "counts_as_work_hours": True,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "RAD",
            "counts_as_work_hours": True,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Job Search",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "AA or NA Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Church",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Doctor Appointment",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Counseling",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Step Work",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 2.0,
        },
        {
            "activity_label": "Sponsor Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 1.0,
        },
        {
            "activity_label": "Volunteer or Community Service",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "School",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Legal Obligation",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
    ],
    "gratitude": [
        {
            "activity_label": "Employment",
            "counts_as_work_hours": True,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Job Search",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "AA or NA Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Church",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Doctor Appointment",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Counseling",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Step Work",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 2.0,
        },
        {
            "activity_label": "Sponsor Meeting",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": 1.0,
        },
        {
            "activity_label": "Volunteer or Community Service",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "School",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
        {
            "activity_label": "Legal Obligation",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": True,
            "weekly_cap_hours": None,
        },
    ],
}


@dataclass
class SeedResident:
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
    status: str
    is_active: bool
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


def iso_local_to_utc(local_dt: datetime) -> str:
    return (
        (
            local_dt.astimezone(CHICAGO_TZ)
            .astimezone(tz=datetime.now().astimezone().tzinfo)
            .astimezone(CHICAGO_TZ)
            .astimezone(datetime.now().astimezone().tzinfo)
        )
        and (local_dt.astimezone(CHICAGO_TZ).astimezone().astimezone(CHICAGO_TZ).astimezone())
        and (
            local_dt.astimezone(CHICAGO_TZ)
            .astimezone()
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
        )
    )


def chicago_local_to_utc_naive_iso(local_dt: datetime) -> str:
    return (
        local_dt.replace(tzinfo=CHICAGO_TZ)
        .astimezone(datetime.utcnow().astimezone().tzinfo)
        .astimezone(CHICAGO_TZ)
        .astimezone()
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def utcnow_chicago_date() -> datetime:
    return datetime.now(CHICAGO_TZ)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo residents and workflow data")
    parser.add_argument("--per-shelter", type=int, default=DEFAULT_PER_SHELTER)
    parser.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    return parser.parse_args()


def fetch_scalar_ids(sql: str, params: tuple = ()) -> list[int]:
    rows = db_fetchall(sql, params)
    values: list[int] = []
    for row in rows or []:
        if isinstance(row, dict):
            values.append(int(next(iter(row.values()))))
        else:
            values.append(int(row[0]))
    return values


def insert_returning_id(sql: str, params: tuple) -> int:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return int(row[0])


def ensure_no_existing_demo_data() -> None:
    row = db_fetchone(
        """
        SELECT COUNT(*) AS c
        FROM residents
        WHERE resident_identifier LIKE %s
        """,
        (f"{DEMO_PREFIX}%",),
    )
    count = int(row["c"] or 0)
    if count > 0:
        raise RuntimeError(
            f"Found {count} existing demo residents with prefix {DEMO_PREFIX}. "
            "Run scripts/clear_demo_data.py first."
        )


def load_staff_user_ids() -> list[int]:
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
        raise RuntimeError(
            "No active staff users were found. Seed or create at least one staff user first."
        )
    return ids


def load_activity_categories() -> dict[str, list[dict]]:
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

    bucket: dict[str, list[dict]] = {"abba": [], "haven": [], "gratitude": []}

    for row in rows or []:
        shelter = str(row["shelter"] or "").strip().lower()
        if shelter not in bucket:
            continue
        bucket[shelter].append(
            {
                "activity_label": row["activity_label"],
                "counts_as_work_hours": bool(row["counts_as_work_hours"]),
                "counts_as_productive_hours": bool(row["counts_as_productive_hours"]),
                "weekly_cap_hours": (
                    float(row["weekly_cap_hours"])
                    if row["weekly_cap_hours"] not in (None, "")
                    else None
                ),
            }
        )

    for shelter in SHELTERS:
        if not bucket[shelter]:
            bucket[shelter] = list(HARD_CODED_ACTIVITY_MAP[shelter])

    return bucket


def load_pass_requirements() -> tuple[float, float]:
    row = db_fetchone(
        """
        SELECT
            COALESCE(pass_productive_required_hours, 35) AS productive_hours,
            COALESCE(pass_work_required_hours, 29) AS work_hours
        FROM shelter_operation_settings
        WHERE LOWER(COALESCE(shelter, '')) = %s
        LIMIT 1
        """,
        ("abba",),
    )
    if not row:
        return 35.0, 29.0
    return float(row["productive_hours"]), float(row["work_hours"])


def ensure_chore_templates(now_iso: str) -> dict[str, list[int]]:
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

            template_id = insert_returning_id(
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
                    True,
                    index,
                    now_iso,
                ),
            )
            ids.append(template_id)
        template_ids[shelter] = ids

    return template_ids


def build_seed_resident(shelter: str, ordinal: int, today_local: datetime) -> SeedResident:
    index = ordinal - 1
    first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
    last_name = f"{LAST_NAMES[index % len(LAST_NAMES)]}Demo{ordinal:02d}"
    resident_identifier = f"{DEMO_PREFIX}-{shelter}-{ordinal:02d}"
    resident_code = generate_resident_code()
    email = f"{resident_identifier}@{DEMO_EMAIL_DOMAIN}"
    phone = f"806555{ordinal:04d}"[-10:]
    birth_year = 1968 + ((ordinal * 3) % 28)

    if shelter == "gratitude":
        level_choices = ["5", "5", "6", "6", "7", "7", "8", "8"]
    else:
        level_choices = ["1", "1", "2", "2", "3", "3", "4", "4", "5"]

    program_level = random.choice(level_choices)

    entry_days_ago = random.randint(7, 180)
    entry_dt = today_local - timedelta(days=entry_days_ago)
    level_start_dt = entry_dt + timedelta(
        days=random.randint(0, max(1, min(30, entry_days_ago // 2)))
    )
    sobriety_dt = max(
        entry_dt - timedelta(days=random.randint(10, 200)), entry_dt - timedelta(days=30)
    )

    is_exited = ordinal in {9, 10} and shelter != "gratitude"
    date_exit_dwc = None
    graduate_dwc = False
    reason_for_exit = None
    is_active = True
    status = "active"

    if is_exited:
        exit_dt = entry_dt + timedelta(days=random.randint(15, max(20, entry_days_ago - 1)))
        if exit_dt >= today_local:
            exit_dt = today_local - timedelta(days=random.randint(2, 10))
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

    return SeedResident(
        shelter=shelter,
        ordinal=ordinal,
        first_name=first_name,
        last_name=last_name,
        resident_identifier=resident_identifier,
        resident_code=resident_code,
        email=email,
        phone=phone,
        birth_year=birth_year,
        program_level=program_level,
        entry_date=entry_dt.date().isoformat(),
        level_start_date=level_start_dt.date().isoformat(),
        sobriety_date=sobriety_dt.date().isoformat(),
        status=status,
        is_active=is_active,
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


def insert_resident(seed: SeedResident, now_iso: str) -> int:
    return insert_returning_id(
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
            treatment_graduation_date,
            employer_name,
            employment_status_current,
            employment_type_current,
            supervisor_name,
            supervisor_phone,
            unemployment_reason,
            employment_notes,
            monthly_income,
            current_job_start_date,
            continuous_employment_start_date,
            previous_job_end_date,
            upward_job_change,
            job_change_notes,
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
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            seed.shelter,
            seed.resident_identifier,
            seed.resident_code,
            seed.first_name,
            seed.last_name,
            seed.birth_year,
            seed.phone,
            seed.email,
            f"Emergency {seed.last_name}",
            "Family",
            "8065559090",
            "Demo medical alert",
            DEMO_NOTE,
            seed.program_level,
            seed.level_start_date,
            seed.sponsor_name,
            seed.sponsor_active,
            seed.sobriety_date,
            random.choice(["Alcohol", "Meth", "Opioids", "None Reported"]),
            None,
            seed.employer_name,
            seed.employment_status_current,
            seed.employment_type_current,
            "Supervisor Demo" if seed.employer_name else None,
            "8065553131" if seed.employer_name else None,
            "Seeking work" if seed.employment_status_current == "Unemployed" else None,
            DEMO_NOTE,
            seed.monthly_income,
            seed.entry_date if seed.employer_name else None,
            seed.entry_date if seed.employer_name else None,
            None,
            random.choice([True, False]),
            DEMO_NOTE,
            now_iso,
            seed.step_current,
            bool(seed.step_current),
            now_iso,
            seed.is_active,
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
            seed.entry_date,
            seed.date_exit_dwc,
            seed.graduate_dwc,
            seed.reason_for_exit,
            False,
            seed.status,
            now_iso,
            True,
            now_iso,
            "demo_seed",
        ),
    )


def insert_program_enrollment(
    resident_id: int, seed: SeedResident, staff_user_id: int, now_iso: str
) -> int:
    program_status = "exited" if not seed.is_active else "active"
    updated_at = seed.date_exit_dwc or now_iso

    return insert_returning_id(
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
            seed.shelter,
            seed.entry_date,
            seed.date_exit_dwc,
            program_status,
            staff_user_id,
            now_iso,
            updated_at,
        ),
    )


def maybe_insert_children(
    resident_id: int,
    enrollment_id: int,
    seed: SeedResident,
    now_iso: str,
    staff_user_id: int,
) -> list[int]:
    child_ids: list[int] = []

    if seed.ordinal % 3 != 0:
        return child_ids

    child_count = 2 if seed.ordinal % 6 == 0 else 1

    for index in range(child_count):
        child_birth_year = min(seed.birth_year + 18 + index, datetime.now(CHICAGO_TZ).year - 1)
        child_id = insert_returning_id(
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
                f"Child Demo {seed.ordinal:02d}{index + 1}",
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
                (datetime.now(CHICAGO_TZ) - timedelta(days=random.randint(5, 40)))
                .date()
                .isoformat(),
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


def insert_substances(resident_id: int, now_iso: str) -> None:
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
        (
            resident_id,
            primary,
            True,
            now_iso,
            now_iso,
        ),
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


def week_start_local(weeks_ago: int) -> datetime:
    now_local = datetime.now(CHICAGO_TZ)
    monday_this_week = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return monday_this_week - timedelta(days=7 * weeks_ago)


def utc_naive_iso_from_chicago(local_dt: datetime) -> str:
    return (
        local_dt.replace(tzinfo=CHICAGO_TZ)
        .astimezone(tz=None)
        .astimezone()
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def choose_week_targets(
    shelter: str, ordinal: int, productive_required: float, work_required: float
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

    if shelter == "gratitude":
        return round(productive_required + random.uniform(4, 10), 1), round(
            work_required + random.uniform(1, 6), 1
        )
    return round(productive_required + random.uniform(1, 6), 1), round(
        work_required + random.uniform(0, 4), 1
    )


def split_hours(total_hours: float, parts: int) -> list[float]:
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


def attendance_insert(
    resident_id: int,
    shelter: str,
    staff_user_id: int,
    destination: str,
    start_local: datetime,
    duration_hours: float,
    note: str,
) -> None:
    end_local = start_local + timedelta(hours=duration_hours)
    start_iso = utc_naive_iso_from_chicago(start_local)
    end_iso = utc_naive_iso_from_chicago(end_local)

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


def seed_attendance_and_weekly_summary(
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
    categories = activity_map[shelter]
    employment_label = next(
        (row["activity_label"] for row in categories if row["activity_label"] == "Employment"),
        "Employment",
    )
    productive_only_labels = [
        row["activity_label"]
        for row in categories
        if row["counts_as_productive_hours"] and not row["counts_as_work_hours"]
    ]

    capped_lookup = {row["activity_label"]: row["weekly_cap_hours"] for row in categories}

    for weeks_ago in range(1, weeks + 1):
        start_of_week = week_start_local(weeks_ago)
        target_productive, target_work = choose_week_targets(
            shelter,
            ordinal + weeks_ago,
            productive_required,
            work_required,
        )

        work_hours = max(0.0, min(target_work, target_productive))
        productive_extra = max(0.0, round(target_productive - work_hours, 1))

        work_blocks = split_hours(work_hours, 5 if work_hours >= 20 else 4)
        for day_index, block_hours in enumerate(work_blocks):
            start_local = start_of_week + timedelta(days=day_index, hours=8 + (day_index % 2))
            attendance_insert(
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

        candidate_blocks = []
        for label in productive_only_labels:
            cap = capped_lookup.get(label)
            if cap is None:
                if label == "AA or NA Meeting" or label == "Church":
                    candidate_blocks.append((label, 1.5))
                elif label == "Counseling" or label == "Doctor Appointment":
                    candidate_blocks.append((label, 1.0))
                elif label == "Job Search":
                    candidate_blocks.append((label, 2.0))
                else:
                    candidate_blocks.append((label, 1.0))
            else:
                candidate_blocks.append((label, float(cap)))

        day_offset = 0
        for label, suggested_hours in candidate_blocks:
            if remaining_extra <= 0:
                break
            hours = round(min(remaining_extra, suggested_hours), 2)
            if hours <= 0:
                continue
            start_local = start_of_week + timedelta(days=min(day_offset, 6), hours=17)
            attendance_insert(
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
        submitted_at = utc_naive_iso_from_chicago(start_of_week + timedelta(days=6, hours=18))

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

        submission_id = insert_returning_id(
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


def seed_case_management(
    resident_id: int,
    enrollment_id: int,
    child_ids: list[int],
    seed: SeedResident,
    staff_user_id: int,
    now_iso: str,
) -> None:
    note_dates = [
        (datetime.now(CHICAGO_TZ) - timedelta(days=45)).date().isoformat(),
        (datetime.now(CHICAGO_TZ) - timedelta(days=21)).date().isoformat(),
        (datetime.now(CHICAGO_TZ) - timedelta(days=7)).date().isoformat(),
    ]

    case_update_ids: list[int] = []

    for note_date in note_dates:
        case_update_id = insert_returning_id(
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
                f"Case note for {seed.first_name} {seed.last_name}. {DEMO_NOTE}",
                random.choice(
                    [
                        "Resident stayed engaged this week",
                        "Resident followed through on assigned tasks",
                        "Resident needs more consistency with scheduling",
                    ]
                ),
                random.choice(
                    [
                        None,
                        "Minor attendance lapse",
                        "Needed reminder about responsibilities",
                    ]
                ),
                "Follow up on appointments and work schedule",
                (datetime.now(CHICAGO_TZ) + timedelta(days=random.randint(2, 14)))
                .date()
                .isoformat(),
                "Demo seeded update",
                random.randint(1, 10),
                random.choice([0, 1]),
                random.choice([0, 1]),
                random.choice([True, False]),
                str(min(8, int(seed.program_level) + 1)) if seed.program_level.isdigit() else None,
                None,
                None,
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )
        case_update_ids.append(case_update_id)

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
                seed.program_level,
                seed.program_level,
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
            (datetime.now(CHICAGO_TZ) - timedelta(days=60)).date().isoformat(),
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
            (datetime.now(CHICAGO_TZ) - timedelta(days=random.randint(3, 35))).date().isoformat(),
            random.choice(UA_RESULTS),
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
            (datetime.now(CHICAGO_TZ) - timedelta(days=random.randint(3, 20))).date().isoformat(),
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
            (datetime.now(CHICAGO_TZ) - timedelta(days=random.randint(10, 50))).date().isoformat(),
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
                (datetime.now(CHICAGO_TZ) - timedelta(days=8)).date().isoformat(),
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


def seed_goals_and_appointments(enrollment_id: int, now_iso: str) -> None:
    for index in range(2):
        created_at = (
            (datetime.now(CHICAGO_TZ) - timedelta(days=30 - (index * 10))).date().isoformat()
        )
        target_date = (
            (datetime.now(CHICAGO_TZ) + timedelta(days=20 + (index * 10))).date().isoformat()
        )
        completed_date = (
            None
            if index == 1
            else (datetime.now(CHICAGO_TZ) - timedelta(days=5)).date().isoformat()
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
        appointment_date = (
            (datetime.now(CHICAGO_TZ) + timedelta(days=random.randint(2, 20))).date().isoformat()
        )
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


def seed_requests_and_passes(
    resident_id: int,
    seed: SeedResident,
    staff_user_id: int,
    now_iso: str,
) -> None:
    resident_phone = seed.phone

    if seed.ordinal % 2 == 0:
        leave_start_local = datetime.now(CHICAGO_TZ) + timedelta(days=3, hours=10)
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
                seed.shelter,
                seed.resident_identifier,
                seed.first_name,
                seed.last_name,
                resident_phone,
                "Doctor Visit",
                "Appointment",
                DEMO_NOTE,
                utc_naive_iso_from_chicago(leave_start_local),
                utc_naive_iso_from_chicago(leave_end_local),
                random.choice(["pending", "approved", "returned"]),
                now_iso,
                now_iso if seed.ordinal % 4 == 0 else None,
                staff_user_id if seed.ordinal % 4 == 0 else None,
                DEMO_NOTE if seed.ordinal % 4 == 0 else None,
                None,
                None,
            ),
        )

    if seed.ordinal % 3 == 0:
        needed_local = datetime.now(CHICAGO_TZ) + timedelta(days=2, hours=9)
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
                seed.shelter,
                seed.resident_identifier,
                seed.first_name,
                seed.last_name,
                utc_naive_iso_from_chicago(needed_local),
                "DWC",
                "Medical Office",
                "Appointment",
                DEMO_NOTE,
                resident_phone,
                random.choice(["pending", "scheduled", "completed"]),
                now_iso,
                now_iso if seed.ordinal % 6 == 0 else None,
                staff_user_id if seed.ordinal % 6 == 0 else None,
                "Demo Driver" if seed.ordinal % 6 == 0 else None,
                DEMO_NOTE if seed.ordinal % 6 == 0 else None,
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
        leave_local = datetime.now(CHICAGO_TZ) + timedelta(days=5, hours=10)
        return_local = leave_local + timedelta(hours=6 if pass_type == "pass" else 28)
        start_at = utc_naive_iso_from_chicago(leave_local)
        end_at = utc_naive_iso_from_chicago(return_local)
    else:
        special_start = (datetime.now(CHICAGO_TZ) + timedelta(days=5)).date()
        special_end = special_start + timedelta(days=1)
        start_date = special_start.isoformat()
        end_date = special_end.isoformat()

    pass_id = insert_returning_id(
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
            seed.shelter,
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
            resident_phone,
            datetime.now(CHICAGO_TZ).date().isoformat(),
            seed.program_level,
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


def seed_chore_assignments(
    resident_id: int,
    shelter: str,
    chore_template_ids: dict[str, list[int]],
    now_iso: str,
) -> None:
    template_ids = chore_template_ids.get(shelter, [])
    if not template_ids:
        return

    for offset, template_id in enumerate(template_ids[:2]):
        assigned_date = (datetime.now(CHICAGO_TZ) - timedelta(days=offset * 7)).date().isoformat()
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
                assigned_date,
                random.choice(["assigned", "completed", "assigned"]),
                DEMO_NOTE,
                now_iso,
                now_iso,
            ),
        )


def seed_transfer_history(resident_id: int, shelter: str, now_iso: str) -> None:
    if shelter == "haven":
        prior = "abba"
    elif shelter == "gratitude":
        prior = "haven"
    else:
        prior = "gratitude"

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


def run_seed(per_shelter: int, weeks: int) -> None:
    now_iso = utcnow_iso()
    today_local = datetime.now(CHICAGO_TZ)
    staff_user_ids = load_staff_user_ids()
    activity_map = load_activity_categories()
    productive_required, work_required = load_pass_requirements()
    chore_template_ids = ensure_chore_templates(now_iso)

    total_residents = 0

    with db_transaction():
        ensure_no_existing_demo_data()

        for shelter in SHELTERS:
            for ordinal in range(1, per_shelter + 1):
                seed = build_seed_resident(
                    shelter=shelter, ordinal=ordinal, today_local=today_local
                )
                staff_user_id = staff_user_ids[(ordinal - 1) % len(staff_user_ids)]

                resident_id = insert_resident(seed=seed, now_iso=now_iso)
                enrollment_id = insert_program_enrollment(
                    resident_id=resident_id,
                    seed=seed,
                    staff_user_id=staff_user_id,
                    now_iso=now_iso,
                )

                child_ids = maybe_insert_children(
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                    seed=seed,
                    now_iso=now_iso,
                    staff_user_id=staff_user_id,
                )

                insert_substances(resident_id=resident_id, now_iso=now_iso)

                seed_attendance_and_weekly_summary(
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

                seed_case_management(
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                    child_ids=child_ids,
                    seed=seed,
                    staff_user_id=staff_user_id,
                    now_iso=now_iso,
                )

                seed_goals_and_appointments(enrollment_id=enrollment_id, now_iso=now_iso)
                seed_requests_and_passes(
                    resident_id=resident_id, seed=seed, staff_user_id=staff_user_id, now_iso=now_iso
                )
                seed_chore_assignments(
                    resident_id=resident_id,
                    shelter=shelter,
                    chore_template_ids=chore_template_ids,
                    now_iso=now_iso,
                )
                seed_transfer_history(resident_id=resident_id, shelter=shelter, now_iso=now_iso)

                total_residents += 1

    current_app.logger.info(
        "Demo seed complete. residents=%s per_shelter=%s weeks=%s prefix=%s",
        total_residents,
        per_shelter,
        weeks,
        DEMO_PREFIX,
    )
    print(
        f"Demo seed complete. Added {total_residents} residents with prefix {DEMO_PREFIX}. "
        f"Weeks seeded per resident: {weeks}."
    )


def main() -> None:
    args = parse_args()
    app = create_app()

    with app.app_context():
        init_db()
        run_seed(per_shelter=args.per_shelter, weeks=args.weeks)


if __name__ == "__main__":
    main()
