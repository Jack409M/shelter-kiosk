from __future__ import annotations

import ipaddress
from collections import Counter, deque
from datetime import UTC, datetime

from flask import current_app, g, session

from core.db import db_execute, db_fetchall
from core.geoip import lookup_ip
from core.helpers import utcnow_iso
from core.rate_limit import (
    get_banned_ips_snapshot,
    get_locked_keys_snapshot,
    get_rate_limit_snapshot,
)
from core.sms_sender import send_sms

ROLE_ORDER = ["admin", "shelter_director", "case_manager", "ra", "staff", "demographics_viewer"]

# ... unchanged code above ...

def allowed_roles_to_create():
    if require_admin_role():
        return {"admin", "shelter_director", "staff", "case_manager", "ra", "demographics_viewer"}

    if current_role() == "shelter_director":
        return {"staff", "case_manager", "ra"}

    return set()


def all_roles():
    return {"admin", "shelter_director", "staff", "case_manager", "ra", "demographics_viewer"}

# rest of file unchanged