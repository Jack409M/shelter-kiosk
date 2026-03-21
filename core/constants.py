# ==========================================================
# SHARED CONSTANTS
# ==========================================================
# This file is the single source of truth for all controlled
# values used across intake, assessment, exit, and reporting.
#
# DO NOT duplicate these lists anywhere else in the system.
# Always import from here.
# ==========================================================


# ==========================================================
# EDUCATION LEVELS (LOCKED)
# ----------------------------------------------------------
# value: what is stored in the database
# label: what is shown in the UI
# rank: used ONLY for statistics and averaging
#
# IMPORTANT BUSINESS RULES:
# - High School Graduate and GED share the same rank
# - Vocational and Associates share the same rank
# - Do NOT change ranks once data exists
# ==========================================================

EDUCATION_LEVEL_OPTIONS = [
    {"value": "No High School", "label": "No High School", "rank": 1},
    {"value": "Some High School", "label": "Some High School", "rank": 2},

    {"value": "High School Graduate", "label": "High School Graduate", "rank": 3},
    {"value": "GED", "label": "GED", "rank": 3},

    {"value": "Vocational", "label": "Vocational", "rank": 4},
    {"value": "Associates", "label": "Associates", "rank": 4},

    {"value": "Bachelor", "label": "Bachelor", "rank": 5},
    {"value": "Masters", "label": "Masters", "rank": 6},
    {"value": "Doctorate", "label": "Doctorate", "rank": 7},
]


# ==========================================================
# EDUCATION LOOKUPS
# ----------------------------------------------------------
# These are used for statistics and reporting.
# Do not store numeric values in DB — always derive from text.
# ==========================================================

EDUCATION_LEVEL_RANK = {
    opt["value"]: opt["rank"]
    for opt in EDUCATION_LEVEL_OPTIONS
}

EDUCATION_LEVEL_LABELS = {
    opt["value"]: opt["label"]
    for opt in EDUCATION_LEVEL_OPTIONS
}


# ==========================================================
# EXIT CATEGORY (LOCKED)
# ----------------------------------------------------------
# High level outcome buckets used in reporting
# ==========================================================

EXIT_CATEGORIES = [
    "Successful Completion",
    "Positive Exit",
    "Neutral Exit",
    "Negative Exit",
    "Administrative Exit",
]


# ==========================================================
# EXIT REASONS (LOCKED + MAPPED)
# ----------------------------------------------------------
# These MUST stay aligned with exit_category logic
# in both UI and backend validation.
# ==========================================================

EXIT_REASON_MAP = {
    "Successful Completion": [
        "Program Graduated",
    ],
    "Positive Exit": [
        "Permanent Housing",
        "Family Placement",
        "Health Placement",
    ],
    "Neutral Exit": [
        "Transferred to Another Program",
        "Unknown / Lost Contact",
    ],
    "Negative Exit": [
        "Relapse",
        "Behavioral Conflict",
        "Rules Violation",
        "Non Compliance with Program",
        "Left Without Notice",
    ],
    "Administrative Exit": [
        "Incarceration",
        "Medical Discharge",
        "Safety Removal",
        "Left by Choice",
    ],
}


# Flat list (useful for validation)
ALL_EXIT_REASONS = [
    reason
    for reasons in EXIT_REASON_MAP.values()
    for reason in reasons
]


# ==========================================================
# SHELTER / PROGRAM IDENTIFIERS (CURRENT STATE)
# ----------------------------------------------------------
# NOTE:
# This currently mixes location + program level + status.
# Future blueprint should split into:
# - location
# - program level
# - status
# ==========================================================

SHELTER_OPTIONS = [
    "Abba",
    "Haven House",
    "Haven Too",
    "Gratitude House",
    "Level 9",
    "Exited",
    "Outreach",
]


# ==========================================================
# DISABILITY TYPES (LOCKED)
# ==========================================================

DISABILITY_TYPES = [
    "Visual",
    "Deaf",
    "Mental Health",
    "Intellectual",
    "Acquired Brain Injury",
    "Autism Spectrum Disorder",
    "Physical",
    "Multiple",
]


# ==========================================================
# EDUCATION PROGRAM TYPES (CURRENT STATUS FIELD)
# ----------------------------------------------------------
# This is NOT the same as education level.
# This is what they are currently enrolled in.
# ==========================================================

EDUCATION_PROGRAM_TYPES = [
    "Secondary",
    "GED",
    "Vocational",
    "Other",
]


# ==========================================================
# YES / NO OPTIONS (STANDARDIZED)
# ==========================================================

YES_NO_OPTIONS = [
    {"value": "yes", "label": "Yes"},
    {"value": "no", "label": "No"},
]
