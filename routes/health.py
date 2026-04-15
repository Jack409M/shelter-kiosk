from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, g

from core.db import db_fetchone
from db.migration_runner import (
    database_schema_is_compatible,
    get_current_schema_version,
    get_required_schema_version,
)

health = Blueprint("health", __name__)


def _service_name() -> str:
    return str(current_app.config.get("APP_NAME") or "shelter-kiosk")


def _database_mode() -> str:
    db_kind = g.get("db_kind")
    if db_kind:
        return str(db_kind)
    return str(current_app.config.get("DATABASE_MODE_LABEL") or "unknown")


def _database_probe() -> dict[str, Any]:
    row = db_fetchone("SELECT 1 AS ok")
    if not row or int(row.get("ok", 0)) != 1:
        raise RuntimeError("Database probe returned an unexpected result.")

    current_version = get_current_schema_version()
    required_version = get_required_schema_version()
    schema_compatible = database_schema_is_compatible()

    return {
        "ok": True,
        "database_mode": _database_mode(),
        "current_schema_version": current_version,
        "required_schema_version": required_version,
        "schema_compatible": schema_compatible,
    }


def _readiness_payload() -> tuple[dict[str, Any], int]:
    status_code = 200
    overall_status = "ok"

    checks: dict[str, Any] = {
        "config": {
            "ok": bool(current_app.config.get("DATABASE_URL")),
            "database_mode": str(current_app.config.get("DATABASE_MODE_LABEL") or "unknown"),
            "init_db_func_configured": callable(current_app.config.get("INIT_DB_FUNC")),
        }
    }

    try:
        database_check = _database_probe()
        checks["database"] = database_check

        if not database_check["schema_compatible"]:
            overall_status = "degraded"
            status_code = 503
    except Exception as exc:
        current_app.logger.exception(
            "health_readiness_failed exception_type=%s",
            type(exc).__name__,
        )
        checks["database"] = {
            "ok": False,
            "database_mode": _database_mode(),
            "error": type(exc).__name__,
            "schema_compatible": False,
            "current_schema_version": None,
            "required_schema_version": None,
        }
        overall_status = "error"
        status_code = 503

    if not checks["config"]["ok"] or not checks["config"]["init_db_func_configured"]:
        overall_status = "error"
        status_code = 503

    payload = {
        "status": overall_status,
        "service": _service_name(),
        "checks": checks,
    }

    request_id = getattr(g, "request_id", None)
    if request_id:
        payload["request_id"] = request_id

    return payload, status_code


@health.get("/health")
def health_root():
    return {
        "status": "ok",
        "service": _service_name(),
    }, 200


@health.get("/live")
def live():
    return {
        "status": "ok",
        "service": _service_name(),
    }, 200


@health.get("/ready")
def ready():
    payload, status_code = _readiness_payload()
    return payload, status_code
