from __future__ import annotations

import importlib
import logging
import os
import pkgutil
import secrets
from datetime import timedelta

from flask import (
    Blueprint,
    flash,
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from core.app_hooks import register_app_hooks
from core.db import close_db
from core.helpers import (
    fmt_date,
    fmt_dt,
    fmt_pretty_date,
    fmt_pretty_dt,
    fmt_time_only,
    safe_url_for,
    shelter_display,
    utcnow_iso,
)
from core.rate_limit import ban_ip, is_ip_banned, is_rate_limited
from core.request_security import register_request_security
from core.request_utils import client_ip
from core.runtime import init_db
