from __future__ import annotations

import os
from datetime import datetime
from threading import Lock

from core.db import get_db
from core.request_utils import client_ip
from core.shelters import get_all_shelters as load_all_shelters
from db import schema


# ------------------------------------------------------------
# Environment helpers
# ------------------------------------------------------------

def env_flag(name: str, default: bool = False) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_text(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip()


# ------------------------------------------------------------
# Role and policy constants
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


# ------------------------------------------------------------
# Environment driven feature flags
# ------------------------------------------------------------

ENABLE_DEBUG_ROUTES = env_flag("ENABLE_DEBUG_ROUTES")
ENABLE_DANGEROUS_ADMIN_ROUTES = env_flag("ENABLE_DANGEROUS_ADMIN_ROUTES")

KIOSK_PIN = env_text("KIOSK_PIN")


# ------------------------------------------------------------
# Twilio flags
# ------------------------------------------------------------

TWILIO_ENABLED = env_flag("TWILIO_ENABLED")
TWILIO_INBOUND_ENABLED = env_flag("TWILIO_INBOUND_ENABLED")
TWILIO_STATUS_ENABLED = env_flag("TWILIO_STATUS_ENABLED")
TWILIO_STATUS_CALLBACK_URL = env_text("TWILIO_STATUS_CALLBACK_URL")


# ------------------------------------------------------------
# Database initialization
# ------------------------------------------------------------

_DB_INITIALIZED = False
_DB_INITIALIZATION_LOCK = Lock()


def init_db() -> None:
    """
    Ensures database connection and schema initialization.
    Runs only once per process and is safe under concurrent startup.
    """
    global _DB_INITIALIZED

    if _DB_INITIALIZED:
        return

    with _DB_INITIALIZATION_LOCK:
        if _DB_INITIALIZED:
            return

        get_db()
        schema.init_db()
        _DB_INITIALIZED = True


# ------------------------------------------------------------
# Shelter helpers
# ------------------------------------------------------------

def get_all_shelters() -> list[str]:
    return load_all_shelters()


# ------------------------------------------------------------
# Client IP helper
# ------------------------------------------------------------

def get_client_ip() -> str:
    return client_ip()


# ------------------------------------------------------------
# Datetime helper
# ------------------------------------------------------------

def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)
