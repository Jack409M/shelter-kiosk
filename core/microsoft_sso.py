from __future__ import annotations

import os
from typing import Any

from flask import current_app

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None  # type: ignore[assignment]


def authlib_available() -> bool:
    return OAuth is not None


def microsoft_sso_enabled() -> bool:
    return (
        authlib_available()
        and os.environ.get("MS_SSO_ENABLED", "false").lower() == "true"
        and bool(os.environ.get("MS_CLIENT_ID"))
        and bool(os.environ.get("MS_CLIENT_SECRET"))
    )


def get_microsoft_client() -> Any:
    if OAuth is None:
        raise RuntimeError("Microsoft SSO is not available because authlib is not installed.")

    tenant = os.environ.get("MS_TENANT_ID", "organizations")

    oauth = OAuth(current_app)

    return oauth.register(
        name="microsoft",
        client_id=os.environ.get("MS_CLIENT_ID"),
        client_secret=os.environ.get("MS_CLIENT_SECRET"),
        server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
