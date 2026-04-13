from __future__ import annotations

import logging
import time
import uuid
from typing import Final

from flask import Flask, current_app, g, redirect, request
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


def _log_request_start(app: Flask) -> None:
    if not _should_log_requests(app):
        return

    request_id = getattr(g, "request_id", "")
    app.logger.info(
        "request_started request_id=%s method=%s path=%s endpoint=%s remote_ip=%s",
        request_id,
        request.method,
        request.path,
        request.endpoint,
        _client_ip(),
    )


def _log_request_complete(app: Flask, response: Response) -> None:
    if not _should_log_requests(app):
        return

    request_id = getattr(g, "request_id", "")
    started_at = getattr(g, "request_started_at", None)
    duration_ms = int((time.perf_counter() - started_at) * 1000) if started_at is not None else 0

    app.logger.info(
        "request_completed request_id=%s method=%s path=%s endpoint=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.path,
        request.endpoint,
        response.status_code,
        duration_ms,
    )


def _log_request_failure(app: Flask, error: BaseException) -> None:
    if not _should_log_requests(app):
        return

    request_id = getattr(g, "request_id", "")
    started_at = getattr(g, "request_started_at", None)
    duration_ms = int((time.perf_counter() - started_at) * 1000) if started_at is not None else 0

    app.logger.exception(
        "request_failed request_id=%s method=%s path=%s endpoint=%s duration_ms=%s error_type=%s",
        request_id,
        request.method,
        request.path,
        request.endpoint,
        duration_ms,
        type(error).__name__,
    )


def _https_is_already_secure() -> bool:
    if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        return True
    if request.is_secure:
        return True
    return False


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


def register_app_hooks(app: Flask) -> None:
    @app.before_request
    def start_request_context() -> None:
        g.request_id = _request_id()
        g.request_started_at = time.perf_counter()
        _log_request_start(app)
        return None

    @app.before_request
    def force_https_redirect():
        if current_app.debug:
            return None

        if _https_is_already_secure():
            return None

        return _redirect_to_https()

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        # ✅ FIXED LINE (this is what was breaking everything)
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
        _log_request_failure(app, error)
