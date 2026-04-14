from __future__ import annotations

from flask import request

# Request utility helpers
#
# Future extraction note
# Additional request level helpers from app.py can move here over time,
# especially things related to IP resolution, proxy awareness, and
# common request parsing.


def client_ip() -> str:
    """
    Resolve the real client IP.

    Priority:
    1. Cloudflare CF-Connecting-IP header (if present)
    2. ProxyFix normalized request.remote_addr
    """

    cf_ip = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cf_ip:
        return cf_ip

    return (request.remote_addr or "").strip() or "unknown"
