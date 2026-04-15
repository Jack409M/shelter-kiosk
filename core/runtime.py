from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from flask import current_app, has_app_context

from core.db import get_db
from core.request_utils import client_ip
from core.shelters import get_all_shelters as load_all_shelters
from db import schema
from db.migration_runner import (
    apply_pending_migrations,
    get_current_schema_version,
    get_required_schema_version,
)

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
# Database runtime configuration
# ------------------------------------------------------------

_DB_INITIALIZED = False
_DB_INITIALIZATION_LOCK = Lock()
_DB_INIT_URL: str | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    database_url: str
    database_mode_label: str


def _normalize_database_url(value: str | None) -> str:
    return str(value or "").strip()


def database_mode_label_from_url(database_url: str) -> str:
    normalized = _normalize_database_url(database_url).lower()

    if not normalized:
        return "missing"

    if normalized.startswith("sqlite:"):
        return "sqlite"

    if normalized.startswith("postgres://") or normalized.startswith("postgresql://"):
        return "postgres"

    return "custom"


def load_runtime_config(*, explicit_database_url: str | None = None) -> RuntimeConfig:
    database_url = _normalize_database_url(
        explicit_database_url
        if explicit_database_url is not None
        else os.environ.get("DATABASE_URL")
    )

    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    return RuntimeConfig(
        database_url=database_url,
        database_mode_label=database_mode_label_from_url(database_url),
    )


def current_database_url() -> str:
    if has_app_context():
        configured = _normalize_database_url(current_app.config.get("DATABASE_URL"))
        if configured:
            return configured

    return _normalize_database_url(os.environ.get("DATABASE_URL"))


def _log_migration_result(applied_versions: list[int]) -> None:
    current_version = get_current_schema_version()
    required_version = get_required_schema_version()

    if applied_versions:
        current_app.logger.info(
            "database_migrations_applied versions=%s current_version=%s required_version=%s",
            applied_versions,
            current_version,
            required_version,
        )
        return

    current_app.logger.info(
        "database_migrations_current current_version=%s required_version=%s",
        current_version,
        required_version,
    )


def init_db() -> None:
    """
    Ensures database connection, migration application, and schema initialization.

    Current transition contract:
    - migrations are now the official schema evolution path
    - legacy schema.init_db() still runs as a temporary compatibility verifier
    - initialization still runs only once per process per resolved DATABASE_URL

    Requires an active Flask app context so the database layer reads the same
    configuration the app was built with.
    """
    global _DB_INITIALIZED, _DB_INIT_URL

    if not has_app_context():
        raise RuntimeError("init_db() requires an active Flask app context.")

    effective_database_url = current_database_url()
    if not effective_database_url:
        raise RuntimeError("DATABASE_URL is required before database initialization.")

    with _DB_INITIALIZATION_LOCK:
        if _DB_INITIALIZED and effective_database_url == _DB_INIT_URL:
            return

        current_app.config["DATABASE_URL"] = effective_database_url
        current_app.config["DATABASE_MODE_LABEL"] = database_mode_label_from_url(
            effective_database_url
        )

        get_db()

        applied_versions = apply_pending_migrations()
        _log_migration_result(applied_versions)

        # Temporary compatibility bridge.
        # Keep legacy schema initialization active until future migrations fully
        # absorb the existing ensure_* upgrade paths.
        schema.init_db()

        _DB_INITIALIZED = True
        _DB_INIT_URL = effective_database_url


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
