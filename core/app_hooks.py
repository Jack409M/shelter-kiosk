from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Final

from flask import Flask, current_app, g, redirect, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

_STATIC_CACHE_CONTROL: Final[str] = "public, max-age=86400"
_DYNAMIC_CACHE_CONTROL: Final[str] = "no-store, no-cache, must-revalidate, private, max-age=0"
_PERMISSIONS_POLICY: Final[str] = (
    "geolocation=(), camera=(), microphone=(), payment=(), usb=(), "
    "accelerometer=(), gyroscope=(), magnetometer=()"
)
_CONTENT_SECURITY_POLICY: Final[str] = (
    "default-src 'none'; "
    "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "connect-src 'self'; "
    "font-src 'self' data: https://unpkg.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)
_HSTS_HEADER: Final[str] = "max-age=31536000; includeSubDomains"


def _request_id() -> str:
    existing_request_id = request.headers.get("X-Request-ID")
    if existing_request_id:
        return existing_request_id.strip() or uuid.uuid4().hex
    return uuid.uuid4().hex


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    return request.remote_addr or ""


def _should_log_requests(app: Flask) -> bool:
    return app.logger.isEnabledFor(logging.INFO)


def _json_log(app: Flask, level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    app.logger.log(level, json.dumps(payload, sort_keys=True, default=str))


def _log_request_start(app: Flask) -> None:
    if not _should_log_requests(app):
        return

    _json_log(
        app,
        logging.INFO,
        "request_started",
        request_id=getattr(g, "request_id", ""),
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        remote_ip=_client_ip(),
    )


def _log_request_complete(app: Flask, response: Response) -> None:
    if not _should_log_requests(app):
        return

    started_at = getattr(g, "request_started_at", None)
    duration_ms = int((time.perf_counter() - started_at) * 1000) if started_at else 0

    _json_log(
        app,
        logging.INFO,
        "request_completed",
        request_id=getattr(g, "request_id", ""),
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        status=response.status_code,
        duration_ms=duration_ms,
    )


def _log_request_failure(app: Flask, error: BaseException) -> None:
    if not _should_log_requests(app):
        return

    started_at = getattr(g, "request_started_at", None)
    duration_ms = int((time.perf_counter() - started_at) * 1000) if started_at else 0

    _json_log(
        app,
        logging.ERROR,
        "request_failed",
        request_id=getattr(g, "request_id", ""),
        method=request.method,
        path=request.path,
        endpoint=request.endpoint,
        duration_ms=duration_ms,
        error_type=type(error).__name__,
    )


def _https_is_already_secure() -> bool:
    if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        return True
    return bool(request.is_secure)


def _redirect_to_https() -> Response:
    return redirect(request.url.replace("http://", "https://", 1), code=301)


def _apply_cache_headers(response: Response) -> None:
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = _STATIC_CACHE_CONTROL
        return

    response.headers["Cache-Control"] = _DYNAMIC_CACHE_CONTROL
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def _apply_security_headers(response: Response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Origin-Agent-Cluster", "?1")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
    response.headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)

    if not current_app.debug:
        response.headers.setdefault("Strict-Transport-Security", _HSTS_HEADER)


def _wants_json() -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _handle_http_exception(error: HTTPException):
    status_code = error.code or 500

    if _wants_json():
        return {"error": error.name, "message": error.description}, status_code

    return render_template("errors/http_error.html", error=error), status_code


def _handle_unexpected_exception(error: Exception):
    app = current_app

    _log_request_failure(app, error)

    if _wants_json():
        return {"error": "Internal Server Error"}, 500

    return render_template("errors/500.html"), 500


def register_app_hooks(app: Flask) -> None:
    @app.before_request
    def start_request_context() -> None:
        g.request_id = _request_id()
        g.request_started_at = time.perf_counter()
        _log_request_start(app)
        return None

    @app.before_request
    def force_https_redirect():
        if current_app.debug or current_app.config.get("TESTING"):
            return None

        if _https_is_already_secure():
            return None

        return _redirect_to_https()

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers.setdefault("X-Request-ID", request_id)

        _apply_cache_headers(response)
        _apply_security_headers(response)
        _log_request_complete(app, response)
        return response

    @app.teardown_request
    def log_request_exception(error: BaseException | None) -> None:
        if error is None:
            return
        if not hasattr(g, "request_started_at"):
            return
        _log_request_failure(app, error)

    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected_exception)
