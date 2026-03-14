from __future__ import annotations

from flask import current_app, redirect, request


def register_app_hooks(app):

    # ------------------------------------------------------------
    # Request logging
    # ------------------------------------------------------------

    @app.before_request
    def log_request_info():
        try:
            app.logger.debug(
                f"REQUEST method={request.method} path={request.path} endpoint={request.endpoint}"
            )
            app.logger.debug(f"URL RULE {request.url_rule}")

            if request.method == "POST":
                app.logger.debug(f"FORM KEYS {list(request.form.keys())}")

        except Exception as e:
            app.logger.debug(f"LOGGING ERROR {e}")


    # ------------------------------------------------------------
    # Force HTTPS
    # ------------------------------------------------------------

    @app.before_request
    def force_https_redirect():
        if current_app.debug:
            return None

        if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
            return None

        if request.is_secure:
            return None

        return redirect(request.url.replace("http://", "https://", 1), code=301)


    # ------------------------------------------------------------
    # Security and cache headers
    # ------------------------------------------------------------

    @app.after_request
    def add_security_headers(response):

        # Static caching
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        else:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # Basic security headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Origin-Agent-Cluster", "?1")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        # Modern browsers ignore this but it doesn't hurt
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")

        # Permissions policy
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), camera=(), microphone=(), payment=(), usb=(), accelerometer=(), gyroscope=(), magnetometer=()"
        )

        # Content Security Policy
        csp = (
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

        response.headers.setdefault("Content-Security-Policy", csp)

        # HSTS
        if not current_app.debug:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
