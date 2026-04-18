# core/kiosk_activity_categories.py

from __future__ import annotations

import contextlib
from flask import g, request
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from .kiosk_activity_category_defaults import KIOSK_ACTIVITY_CATEGORY_SEEDS


# ======================
# LOCKED PARENTS
# ======================

LOCKED_PARENT_ACTIVITY_DEFINITIONS = {
    "aa_na_meeting": "AA or NA Meeting",
    "volunteer_community_service": "Volunteer or Community Service",
    "medical_health": "Medical or Health",
    "legal": "Legal",
    "program": "Program",
    "job_search": "Job Search",
    "social_services": "Social Services",
    "education": "Education",
}

NORMALIZED_LOCKED_PARENT_LABEL_TO_KEY = {
    label.lower(): key
    for key, label in LOCKED_PARENT_ACTIVITY_DEFINITIONS.items()
}


# ======================
# CHILD OPTION SEEDS
# ======================

LOCKED_PARENT_CHILD_OPTION_SEEDS = {
    "aa_na_meeting": [
        "Touch of Soul","Clean Air","12 Steps","Moss","Hobbs","Serenity",
        "Nothing to Fear","No Matter What","Top of Texas","DWC House Meting",
        "Online","Other","None"
    ],
    "volunteer_community_service": [
        "Thrift City","Thrift City Too","Office","Gratitude House",
        "Food Bank","Other","None"
    ],
    "medical_health": [
        "Doctor","Dentist","Optometrist","Therapist",
        "Counselor","Psychiatrist","Medication"
    ],
    "legal": [
        "Court","Probation","Parole","Lawyer","Legal Aid"
    ],
    "program": [
        "Case Manager","Intake","Assessment",
        "House Meeting","RAD","Group Session"
    ],
    "job_search": [
        "Interview","Application","Workforce","Resume Help"
    ],
    "social_services": [
        "SNAP","Medicaid","SSI","Housing Authority"
    ],
    "education": [
        "GED","School","Training","Certification"
    ],
}


# ======================
# HELPERS
# ======================

def _normalized(value):
    return (value or "").strip().lower()

def _canonical_key(label):
    return NORMALIZED_LOCKED_PARENT_LABEL_TO_KEY.get(_normalized(label), "")

def _child_option_seeds_for_parent(parent_key):
    return LOCKED_PARENT_CHILD_OPTION_SEEDS.get(parent_key, [])

def _placeholder():
    return "%s" if g.get("db_kind") == "pg" else "?"


# ======================
# TABLE ENSURE
# ======================

def ensure_kiosk_activity_categories_table():
    db_execute("""
        CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT,
            activity_key TEXT,
            activity_label TEXT,
            active INTEGER,
            sort_order INTEGER,
            counts_as_work_hours INTEGER,
            counts_as_productive_hours INTEGER,
            weekly_cap_hours REAL,
            requires_approved_pass INTEGER,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)


def ensure_kiosk_activity_child_options_table():
    db_execute("""
        CREATE TABLE IF NOT EXISTS kiosk_activity_child_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT,
            parent_activity_key TEXT,
            parent_activity_label TEXT,
            option_label TEXT,
            active INTEGER,
            sort_order INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
    """)


# ======================
# LOAD CATEGORIES (FIXED ROW ISSUE)
# ======================

def load_kiosk_activity_categories_for_shelter(shelter):
    ensure_kiosk_activity_categories_table()

    rows = db_fetchall("""
        SELECT * FROM kiosk_activity_categories
        WHERE LOWER(shelter)=LOWER(?)
        ORDER BY sort_order
    """, (shelter,))

    categories = [dict(r) for r in rows]

    # 🔥 FIX: always allow growth
    for _ in range(6):
        categories.append({
            "id": "",
            "activity_key": "",
            "activity_label": "",
            "active": True,
            "sort_order": "",
            "counts_as_work_hours": False,
            "counts_as_productive_hours": False,
            "weekly_cap_hours": "",
            "requires_approved_pass": False,
            "notes": "",
        })

    return categories


# ======================
# LOAD CHILD OPTIONS (GENERIC)
# ======================

def load_active_kiosk_activity_child_options_for_shelter(shelter, parent_key):
    ensure_kiosk_activity_child_options_table()

    rows = db_fetchall("""
        SELECT * FROM kiosk_activity_child_options
        WHERE LOWER(shelter)=LOWER(?)
        AND LOWER(parent_activity_key)=LOWER(?)
        AND active=1
        ORDER BY sort_order
    """, (shelter, parent_key))

    if rows:
        return [dict(r) for r in rows]

    # fallback to seeds
    return [{"option_label": o} for o in _child_option_seeds_for_parent(parent_key)]


# ======================
# SAVE CHILD OPTIONS
# ======================

def save_kiosk_activity_child_options_for_shelter(shelter, parent_key):
    ensure_kiosk_activity_child_options_table()

    now = utcnow_iso()

    labels = request.form.getlist("child_option_label[]")

    db_execute("""
        DELETE FROM kiosk_activity_child_options
        WHERE LOWER(shelter)=LOWER(?)
        AND LOWER(parent_activity_key)=LOWER(?)
    """, (shelter, parent_key))

    for i, label in enumerate(labels):
        if not label.strip():
            continue

        db_execute("""
            INSERT INTO kiosk_activity_child_options
            (shelter, parent_activity_key, parent_activity_label, option_label, active, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (
            shelter,
            parent_key,
            LOCKED_PARENT_ACTIVITY_DEFINITIONS.get(parent_key),
            label.strip(),
            i,
            now,
            now
        ))
