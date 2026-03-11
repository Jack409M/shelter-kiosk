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
    Use ProxyFix normalized remote_addr rather than trusting raw
    forwarded headers directly.
    """
    return (request.remote_addr or "").strip() or "unknown"
