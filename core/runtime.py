from __future__ import annotations

import os
from datetime import datetime

from flask import request, session

from core.db import get_db
from core.request_utils import client_ip
from core.shelters import get_all_shelters as load_all_shelters
from db import schema


# ------------------------------------------------------------
# Environment / configuration flags
# ------------------------------------------------------------

MIN_STAFF_PASSWORD_LEN = 8

USER_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra"}

ROLE_LABELS = {
    "admin": "Admin",
    "shelter_director": "Shelter Director",
    "staff": "Staff",
    "ra": "RA DESK",
    "case_manager": "Case Mgr",
}

STAFF_ROLES = {"admin", "shelter_director", "staff", "case_manager", "ra"}

TRANSFER_ROLES = {"admin", "shelter_director", "case_manager"}

ENABLE_DEBUG_ROUTES = (os.environ.get("ENABLE_DEBUG_ROUTES") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ENABLE_DANGEROUS_ADMIN_ROUTES = (
    (os.environ.get("ENABLE_DANGEROUS_ADMIN_ROUTES") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)

KIOSK_PIN = (os.environ.get("KIOSK_PIN") or "").strip()


# ------------------------------------------------------------
# Twilio flags
# ------------------------------------------------------------

TWILIO_ENABLED = os.environ.get("TWILIO_ENABLED", "false").lower() == "true"

TWILIO_INBOUND_ENABLED = (
    os.environ.get("TWILIO_INBOUND_ENABLED", "false").strip().lower() == "true"
)

TWILIO_STATUS_ENABLED = (
    os.environ.get("TWILIO_STATUS_ENABLED", "false").strip().lower() == "true"
)

TWILIO_STATUS_CALLBACK_URL = (
    os.environ.get("TWILIO_STATUS_CALLBACK_URL") or ""
).strip()


# ------------------------------------------------------------
# Database initialization
# ------------------------------------------------------------

_DB_INITIALIZED = False


def init_db() -> None:
    """
    Ensures database connection and schema initialization.
    Runs only once per process.
    """
    global _DB_INITIALIZED

    if _DB_INITIALIZED:
        return

    get_db()
    schema.init_db()
    _DB_INITIALIZED = True


# ------------------------------------------------------------
# Shelter helpers
# ------------------------------------------------------------

def get_all_shelters() -> list[str]:
    """
    Returns all shelters in the system.
    """
    return load_all_shelters(init_db)


# ------------------------------------------------------------
# Client IP helper
# ------------------------------------------------------------

def get_client_ip() -> str:
    """
    Standardized client IP retrieval.
    """
    return client_ip()


# ------------------------------------------------------------
# Datetime helper
# ------------------------------------------------------------

def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)
