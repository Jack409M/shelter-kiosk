from __future__ import annotations

import os
from authlib.integrations.flask_client import OAuth
from flask import current_app


def microsoft_sso_enabled() -> bool:
    return (
        os.environ.get("MS_SSO_ENABLED", "false").lower() == "true"
        and os.environ.get("MS_CLIENT_ID")
        and os.environ.get("MS_CLIENT_SECRET")
    )


def get_microsoft_client():
    tenant = os.environ.get("MS_TENANT_ID", "organizations")

    oauth = OAuth(current_app)

    return oauth.register(
        name="microsoft",
        client_id=os.environ.get("MS_CLIENT_ID"),
        client_secret=os.environ.get("MS_CLIENT_SECRET"),
        server_metadata_url=f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
