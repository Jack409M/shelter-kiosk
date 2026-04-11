from __future__ import annotations

from flask import abort, current_app, flash, render_template, request

from core.audit import log_action


def register_request_security(
    app,
    *,
    client_ip_func,
    is_ip_banned_func,
    is_rate_limited_func,
    ban_ip_func,
) -> None:
    """
    Register request security before_request handlers onto the Flask app.

    Parameters are injected so this module stays decoupled from app setup and
    can be tested or reused more easily later.
    """

    def _audit(action_type: str, details: str) -> None:
        try:
            log_action("security", None, None, None, action_type, details)
        except Exception:
            current_app.logger.exception(
                "request security audit write failed action_type=%s",
                action_type,
            )

    def _truthy_config(value) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _normalized_path() -> str:
        raw = (request.path or "").strip()
        if not raw:
            return "/"
        if raw != "/" and raw.endswith("/"):
            raw = raw[:-1]
        return raw

    def _safe_log_value(value: str | None, max_length: int = 200) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        text = "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in text)
        text = text.replace(" ", "_")
        return text[:max_length]

    def _request_user_agent() -> str:
        return (request.headers.get("User-Agent") or "").strip()

    def _request_ip() -> str:
        return (client_ip_func() or "unknown").strip() or "unknown"

    def _base_details(*, ip: str | None = None, reason: str = "") -> str:
        actual_ip = (ip or _request_ip()).strip() or "unknown"
        method = (request.method or "").strip()
        path = _normalized_path()
        user_agent = _request_user_agent()

        parts = [
            f"ip={actual_ip}",
            f"method={method}",
            f"path={path}",
        ]

        if reason:
            parts.append(f"reason={reason}")

        safe_ua = _safe_log_value(user_agent)
        if safe_ua:
            parts.append(f"ua={safe_ua}")

        return " ".join(parts)

    def _abort_and_audit(status_code: int, action_type: str, details: str):
        _audit(action_type, details)
        abort(status_code)

    @app.before_request
    def require_cloudflare_proxy():
        if not _truthy_config(current_app.config.get("CLOUDFLARE_ONLY")):
            return None

        if request.headers.get("CF-Connecting-IP"):
            return None

        details = _base_details(
            ip=request.remote_addr,
            reason="missing_cf_connecting_ip",
        )
        _audit("cloudflare_bypass_blocked", details)
        current_app.logger.warning(
            "BLOCK non-cloudflare request remote_addr=%s path=%s",
            request.remote_addr,
            request.path,
        )
        abort(403)

    @app.before_request
    def block_banned_ips():
        ip = _request_ip()

        if ip != "unknown" and is_ip_banned_func(ip):
            _abort_and_audit(
                403,
                "banned_ip_blocked",
                _base_details(ip=ip, reason="ip_already_banned"),
            )

        return None

    @app.before_request
    def block_bad_methods_and_agents():
        bad_methods = {"TRACE", "TRACK", "CONNECT"}

        if request.method in bad_methods:
            _abort_and_audit(
                405,
                "bad_method_blocked",
                _base_details(reason=f"method_{request.method.lower()}"),
            )

        user_agent_lower = _request_user_agent().lower()

        allowed_agent_markers = (
            "twilio",
        )
        if any(marker in user_agent_lower for marker in allowed_agent_markers):
            return None

        bad_agent_markers = (
            "sqlmap",
            "nikto",
            "nmap",
            "masscan",
            "zgrab",
        )

        if not any(marker in user_agent_lower for marker in bad_agent_markers):
            return None

        ip = _request_ip()
        _audit(
            "bad_user_agent_detected",
            _base_details(ip=ip, reason="matched_bad_agent_marker"),
        )

        if ip != "unknown":
            ban_ip_func(ip, 3600)
            _audit(
                "bad_user_agent_banned",
                _base_details(ip=ip, reason="auto_ban_3600"),
            )
            current_app.logger.warning(
                "AUTO BAN bad user agent ip=%s ua=%s path=%s",
                ip,
                _request_user_agent(),
                request.path,
            )

        abort(403)

    @app.before_request
    def auto_ban_scanner_probes():
        path = _normalized_path().lower()

        if path.startswith("/static/") or path == "/favicon.ico":
            return None

        scanner_markers = (
            ".env",
            ".git",
            "wp-admin",
            "wp-login",
            "/wp-json",
            "phpmyadmin",
            "xmlrpc.php",
            "cgi-bin",
            "boaform",
            "server-status",
            "actuator",
            "jenkins",
            "/vendor",
        )

        if not any(marker in path for marker in scanner_markers):
            return None

        ip = _request_ip()
        _audit(
            "scanner_probe_detected",
            _base_details(ip=ip, reason="matched_scanner_marker"),
        )

        if ip != "unknown" and is_rate_limited_func(
            f"scanner_probe:{ip}",
            limit=3,
            window_seconds=600,
        ):
            ban_ip_func(ip, 3600)
            _audit(
                "scanner_probe_banned",
                _base_details(ip=ip, reason="auto_ban_3600"),
            )
            current_app.logger.warning(
                "AUTO BAN scanner probe ip=%s path=%s",
                ip,
                request.path,
            )
            abort(403)

        abort(404)

    @app.before_request
    def public_bot_throttle():
        path = _normalized_path()

        public_paths = {
            "/resident",
            "/leave",
            "/transport",
            "/resident/consent",
        }

        if path not in public_paths:
            return None

        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None

        ip = _request_ip()

        if not is_rate_limited_func(
            f"public_post:{path}:{ip}",
            limit=20,
            window_seconds=300,
        ):
            return None

        _audit(
            "public_abuse_rate_limited",
            _base_details(ip=ip, reason="public_post_limit_exceeded"),
        )

        if ip != "unknown":
            ban_ip_func(ip, 1800)
            _audit(
                "public_abuse_banned",
                _base_details(ip=ip, reason="auto_ban_1800"),
            )
            current_app.logger.warning(
                "AUTO BAN public abuse ip=%s path=%s",
                ip,
                path,
            )

        if path == "/resident":
            flash(
                "Too many requests. Please wait a few minutes and try again.",
                "error",
            )
            return render_template("resident_signin.html"), 429

        return "Too many requests. Please wait a few minutes and try again.", 429
