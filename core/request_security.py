from __future__ import annotations

from flask import abort, current_app, flash, redirect, render_template, request


# ------------------------------------------------------------
# Request Security Middleware Registration
# ------------------------------------------------------------
# This module centralizes request level security hooks that were
# previously living inline in app.py.
#
# Current responsibilities:
# cloudflare only enforcement
# banned IP blocking
# bad method and bad user agent blocking
# scanner probe auto blocking
# public form abuse throttling
#
# Future extraction ideas:
# split scanner logic into scanner_defense.py
# split public abuse throttling into abuse_controls.py
# move marker lists into config
# ------------------------------------------------------------


def register_request_security(app, *, client_ip_func, is_ip_banned_func, is_rate_limited_func, ban_ip_func) -> None:
    """
    Register request security before_request handlers onto the Flask app.

    Parameters are injected so this module stays decoupled from app.py and
    can be tested or reused more easily later.
    """

    @app.before_request
    def require_cloudflare_proxy():
        if (current_app.config.get("CLOUDFLARE_ONLY") or "").strip().lower() not in {"1", "true", "yes", "on"}:
            return None

        if not request.headers.get("CF-Connecting-IP"):
            current_app.logger.warning(
                "BLOCK non-cloudflare request remote_addr=%s path=%s",
                request.remote_addr,
                request.path,
            )
            abort(403)

        return None

    @app.before_request
    def block_banned_ips():
        ip = client_ip_func()
        if ip != "unknown" and is_ip_banned_func(ip):
            abort(403)

        return None

    @app.before_request
    def block_bad_methods_and_agents():
        bad_methods = {"TRACE", "TRACK", "CONNECT"}
        if request.method in bad_methods:
            abort(405)

        user_agent = (request.headers.get("User-Agent") or "").lower()

        allowed_agent_markers = (
            "twilio",
        )

        if any(marker in user_agent for marker in allowed_agent_markers):
            return None

        bad_agent_markers = (
            "sqlmap",
            "nikto",
            "nmap",
            "masscan",
            "zgrab",
            "curl",
            "wget",
            "python-requests",
            "pythonurllib",
            "go-http-client",
            "libwww-perl",
        )

        if any(marker in user_agent for marker in bad_agent_markers):
            ip = client_ip_func()
            if ip != "unknown":
                ban_ip_func(ip, 3600)
                current_app.logger.warning(
                    "AUTO BAN bad user agent ip=%s ua=%s path=%s",
                    ip,
                    request.headers.get("User-Agent"),
                    request.path,
                )
            abort(403)

        return None

    @app.before_request
    def auto_ban_scanner_probes():
        path = (request.path or "").lower()

        scanner_markers = (
            ".env",
            ".git",
            "wp-admin",
            "wp-login",
            "phpmyadmin",
            "xmlrpc.php",
            "cgi-bin",
            "boaform",
            "server-status",
            "actuator",
            "jenkins",
            "/vendor/",
        )

        if not any(marker in path for marker in scanner_markers):
            return None

        ip = client_ip_func()

        if ip != "unknown" and is_rate_limited_func(f"scanner_probe:{ip}", limit=3, window_seconds=600):
            ban_ip_func(ip, 3600)
            current_app.logger.warning("AUTO BAN scanner probe ip=%s path=%s", ip, request.path)
            abort(403)

        abort(404)

    @app.before_request
    def public_bot_throttle():
        public_paths = {
            "/resident",
            "/leave",
            "/transport",
            "/resident/consent",
        }

        if request.path not in public_paths:
            return None

        if request.method == "GET":
            return None

        ip = client_ip_func()

        if is_rate_limited_func(f"public_post:{request.path}:{ip}", limit=20, window_seconds=300):
            if ip != "unknown":
                ban_ip_func(ip, 1800)
                current_app.logger.warning("AUTO BAN public abuse ip=%s path=%s", ip, request.path)

            if request.path == "/resident":
                flash("Too many requests. Please wait a few minutes and try again.", "error")
                return render_template("resident_signin.html"), 429

            return "Too many requests. Please wait a few minutes and try again.", 429

        return None
