from __future__ import annotations

from dataclasses import dataclass

from flask import g

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

from .utils import _float_value, _placeholder

UNIT_TYPE_FLAT = "flat"
UNIT_TYPE_ONE_BEDROOM = "one_bedroom"
UNIT_TYPE_TWO_BEDROOM = "two_bedroom"
UNIT_TYPE_TOWNHOME = "townhome"

EDITABLE_UNIT_TYPES = {
    UNIT_TYPE_FLAT,
    UNIT_TYPE_ONE_BEDROOM,
    UNIT_TYPE_TWO_BEDROOM,
    UNIT_TYPE_TOWNHOME,
}

DEFAULT_RENT_RULES: tuple[dict, ...] = (
    {
        "program_level": "1",
        "unit_type": UNIT_TYPE_FLAT,
        "monthly_rent": 150.00,
        "is_minimum": False,
    },
    {
        "program_level": "2",
        "unit_type": UNIT_TYPE_FLAT,
        "monthly_rent": 150.00,
        "is_minimum": False,
    },
    {
        "program_level": "3",
        "unit_type": UNIT_TYPE_FLAT,
        "monthly_rent": 200.00,
        "is_minimum": False,
    },
    {
        "program_level": "4",
        "unit_type": UNIT_TYPE_FLAT,
        "monthly_rent": 250.00,
        "is_minimum": False,
    },
    {
        "program_level": "5",
        "unit_type": UNIT_TYPE_ONE_BEDROOM,
        "monthly_rent": 350.00,
        "is_minimum": False,
    },
    {
        "program_level": "5",
        "unit_type": UNIT_TYPE_TWO_BEDROOM,
        "monthly_rent": 400.00,
        "is_minimum": False,
    },
    {
        "program_level": "5",
        "unit_type": UNIT_TYPE_TOWNHOME,
        "monthly_rent": 400.00,
        "is_minimum": False,
    },
    {
        "program_level": "6",
        "unit_type": UNIT_TYPE_ONE_BEDROOM,
        "monthly_rent": 400.00,
        "is_minimum": False,
    },
    {
        "program_level": "6",
        "unit_type": UNIT_TYPE_TWO_BEDROOM,
        "monthly_rent": 450.00,
        "is_minimum": False,
    },
    {
        "program_level": "6",
        "unit_type": UNIT_TYPE_TOWNHOME,
        "monthly_rent": 450.00,
        "is_minimum": False,
    },
    {
        "program_level": "7",
        "unit_type": UNIT_TYPE_ONE_BEDROOM,
        "monthly_rent": 450.00,
        "is_minimum": False,
    },
    {
        "program_level": "7",
        "unit_type": UNIT_TYPE_TWO_BEDROOM,
        "monthly_rent": 500.00,
        "is_minimum": False,
    },
    {
        "program_level": "7",
        "unit_type": UNIT_TYPE_TOWNHOME,
        "monthly_rent": 500.00,
        "is_minimum": False,
    },
    {
        "program_level": "8",
        "unit_type": UNIT_TYPE_ONE_BEDROOM,
        "monthly_rent": 600.00,
        "is_minimum": True,
    },
    {
        "program_level": "8",
        "unit_type": UNIT_TYPE_TWO_BEDROOM,
        "monthly_rent": 650.00,
        "is_minimum": True,
    },
    {
        "program_level": "8",
        "unit_type": UNIT_TYPE_TOWNHOME,
        "monthly_rent": 650.00,
        "is_minimum": True,
    },
)

LEVEL_8_ADJUSTMENT_GUIDANCE = (
    "Level 8 rent starts at the configured minimum and may be adjusted based on "
    "the income and expense ratio determined by the case manager."
)


@dataclass(frozen=True)
class RentRule:
    program_level: str
    unit_type: str
    monthly_rent: float
    is_minimum: bool
    is_active: bool


def normalize_program_level(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def normalize_unit_type(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if not text:
        return ""

    if "flat" in text or "bed" not in text and "town" not in text:
        return UNIT_TYPE_FLAT
    if "one" in text or text in {"1 bedroom", "1 bed", "1bdrm", "1 bdrm"}:
        return UNIT_TYPE_ONE_BEDROOM
    if "two" in text or text in {"2 bedroom", "2 bed", "2bdrm", "2 bdrm"}:
        return UNIT_TYPE_TWO_BEDROOM
    if "town" in text:
        return UNIT_TYPE_TOWNHOME

    return text.replace(" ", "_")


def unit_type_label(unit_type: str) -> str:
    labels = {
        UNIT_TYPE_FLAT: "Flat Rate",
        UNIT_TYPE_ONE_BEDROOM: "One Bedroom",
        UNIT_TYPE_TWO_BEDROOM: "Two Bedroom",
        UNIT_TYPE_TOWNHOME: "Townhome",
    }
    return labels.get(unit_type, unit_type.replace("_", " ").title())


def _bool_for_db(value: bool):
    return value if g.get("db_kind") == "pg" else (1 if value else 0)


def ensure_rr_rent_config_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS rr_rent_rules (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                program_level TEXT NOT NULL,
                unit_type TEXT NOT NULL,
                monthly_rent NUMERIC(10,2) NOT NULL DEFAULT 0,
                is_minimum BOOLEAN NOT NULL DEFAULT FALSE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (shelter, program_level, unit_type)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS rr_rent_policy_settings (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL UNIQUE,
                rent_due_day INTEGER NOT NULL DEFAULT 1,
                rent_late_day INTEGER NOT NULL DEFAULT 6,
                rent_late_fee_per_day NUMERIC(10,2) NOT NULL DEFAULT 1.00,
                carry_forward_balance BOOLEAN NOT NULL DEFAULT TRUE,
                level_8_adjustment_guidance TEXT,
                accepted_payment_methods TEXT,
                payment_collector_roles TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS rr_rent_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            program_level TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            monthly_rent REAL NOT NULL DEFAULT 0,
            is_minimum INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (shelter, program_level, unit_type)
        )
        """
    )
    db_execute(
        """
        CREATE TABLE IF NOT EXISTS rr_rent_policy_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL UNIQUE,
            rent_due_day INTEGER NOT NULL DEFAULT 1,
            rent_late_day INTEGER NOT NULL DEFAULT 6,
            rent_late_fee_per_day REAL NOT NULL DEFAULT 1.00,
            carry_forward_balance INTEGER NOT NULL DEFAULT 1,
            level_8_adjustment_guidance TEXT,
            accepted_payment_methods TEXT,
            payment_collector_roles TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def seed_default_rr_rent_config(shelter: str) -> None:
    ensure_rr_rent_config_table()

    shelter_key = str(shelter or "").strip().lower()
    if not shelter_key:
        return

    now = utcnow_iso()
    ph = _placeholder()

    for rule in DEFAULT_RENT_RULES:
        existing = db_fetchone(
            f"""
            SELECT id
            FROM rr_rent_rules
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND program_level = {ph}
              AND unit_type = {ph}
            LIMIT 1
            """,
            (shelter_key, rule["program_level"], rule["unit_type"]),
        )
        if existing:
            continue

        db_execute(
            (
                """
                INSERT INTO rr_rent_rules (
                    shelter,
                    program_level,
                    unit_type,
                    monthly_rent,
                    is_minimum,
                    is_active,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                if g.get("db_kind") == "pg"
                else """
                INSERT INTO rr_rent_rules (
                    shelter,
                    program_level,
                    unit_type,
                    monthly_rent,
                    is_minimum,
                    is_active,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                shelter_key,
                rule["program_level"],
                rule["unit_type"],
                rule["monthly_rent"],
                _bool_for_db(bool(rule["is_minimum"])),
                _bool_for_db(True),
                LEVEL_8_ADJUSTMENT_GUIDANCE if rule["program_level"] == "8" else None,
                now,
                now,
            ),
        )

    existing_policy = db_fetchone(
        f"""
        SELECT id
        FROM rr_rent_policy_settings
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (shelter_key,),
    )
    if existing_policy:
        return

    db_execute(
        (
            """
            INSERT INTO rr_rent_policy_settings (
                shelter,
                rent_due_day,
                rent_late_day,
                rent_late_fee_per_day,
                carry_forward_balance,
                level_8_adjustment_guidance,
                accepted_payment_methods,
                payment_collector_roles,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO rr_rent_policy_settings (
                shelter,
                rent_due_day,
                rent_late_day,
                rent_late_fee_per_day,
                carry_forward_balance,
                level_8_adjustment_guidance,
                accepted_payment_methods,
                payment_collector_roles,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            shelter_key,
            1,
            6,
            1.00,
            _bool_for_db(True),
            LEVEL_8_ADJUSTMENT_GUIDANCE,
            "Money order\nCashier check",
            "Case managers only",
            now,
            now,
        ),
    )


def load_rr_rent_rules(shelter: str) -> list[RentRule]:
    seed_default_rr_rent_config(shelter)

    shelter_key = str(shelter or "").strip().lower()
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT program_level, unit_type, monthly_rent, is_minimum, is_active
        FROM rr_rent_rules
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        ORDER BY CAST(program_level AS INTEGER), unit_type
        """,
        (shelter_key,),
    )

    return [
        RentRule(
            program_level=normalize_program_level(row["program_level"]),
            unit_type=normalize_unit_type(row["unit_type"]),
            monthly_rent=round(_float_value(row["monthly_rent"]), 2),
            is_minimum=bool(row["is_minimum"]),
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]


def load_rr_rent_policy(shelter: str) -> dict:
    seed_default_rr_rent_config(shelter)

    shelter_key = str(shelter or "").strip().lower()
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT *
        FROM rr_rent_policy_settings
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (shelter_key,),
    )
    return dict(row) if row else {}


def resolve_rr_base_rent(
    *,
    shelter: str,
    program_level: object,
    unit_type: object,
) -> tuple[float, str]:
    level = normalize_program_level(program_level)
    normalized_unit_type = normalize_unit_type(unit_type)

    if level in {"1", "2", "3", "4"}:
        normalized_unit_type = UNIT_TYPE_FLAT

    for rule in load_rr_rent_rules(shelter):
        if not rule.is_active:
            continue
        if rule.program_level != level:
            continue
        if rule.unit_type != normalized_unit_type:
            continue

        label = unit_type_label(rule.unit_type)
        if rule.is_minimum:
            return rule.monthly_rent, f"Level {level} {label} minimum rent from RR admin config"
        return rule.monthly_rent, f"Level {level} {label} rent from RR admin config"

    return 0.0, "No RR rent rule matched"
