from __future__ import annotations

from flask import g

from core.admin_dashboard_utils import (
    DASHBOARD_ATTACK_ACTION_TYPES,
    row_value,
    scalar_value,
    security_action_filter_sql,
    serialize_rows,
)
from core.admin_rbac import (
    ROLE_ORDER,
    allowed_roles_to_create,
    all_roles,
    current_role,
    ordered_roles,
    require_admin_or_shelter_director_role,
    require_admin_role,
)
from core.audit_filters import audit_where_from_request
from core.db import db_fetchall
from core.rate_limit import get_locked_keys_snapshot
from core.security_alerts import (
    load_admin_alert_numbers,
    maybe_send_security_alerts,
    security_alert_cooldown_hit,
)
from core.security_banner import build_security_banner
from core.security_incidents import (
    INCIDENT_DEDUPE_WINDOWS,
    SECURITY_INCIDENT_LOOKBACK_HOURS,
    create_security_incident,
    incident_exists_recently,
    load_recent_security_incidents,
    maybe_create_security_incidents,
)
from core.security_intelligence import (
    THREAT_EVENT_SCORES,
    THREAT_SUMMARY_LABELS,
    build_attack_intelligence,
    build_attack_map_points,
    build_threat_scores,
    extract_detail_value,
)
from core.security_settings import load_security_settings


def build_locked_username_snapshot():
    rows = []

    for row in get_locked_keys_snapshot():
        key = str(row.get("key", ""))
        prefix = "staff_login_username_lock:"

        if not key.startswith(prefix):
            continue

        rows.append(
            {
                "username": key[len(prefix) :],
                "seconds_remaining": row.get("seconds_remaining", 0),
                "key": key,
            }
        )

    rows.sort(key=lambda item: int(item["seconds_remaining"]), reverse=True)
    return rows


def build_recent_staff_sessions(limit: int = 12) -> list[dict]:
    kind = g.get("db_kind")
    query_limit = max(int(limit or 12) * 20, 100)

    rows = db_fetchall(
        """
        SELECT
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type IN ('login', 'logout', 'profile_update', 'reset_password', 'set_role', 'set_active')
          AND NULLIF(a.created_at, '')::timestamptz >= NOW() - INTERVAL '12 hours'
        ORDER BY a.id DESC
        LIMIT %s
        """
        if kind == "pg"
        else """
        SELECT
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE a.action_type IN ('login', 'logout', 'profile_update', 'reset_password', 'set_role', 'set_active')
          AND a.created_at >= datetime('now', '-12 hours')
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (query_limit,),
    )

    sessions = {}

    for row in rows or []:
        username = (row_value(row, "staff_username", "") or "").strip()
        if not username:
            details = row_value(row, "action_details", "") or ""
            username = extract_detail_value(details, "username")

        if not username or username in sessions:
            continue

        action_type = (row_value(row, "action_type", "") or "").strip()
        created_at = row_value(row, "created_at", "") or ""

        sessions[username] = {
            "username": username,
            "status": "active" if action_type == "login" else "ended",
            "last_seen": created_at,
            "last_action": action_type,
        }

    active_rows = [row for row in sessions.values() if row["status"] == "active"]
    active_rows.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
    return active_rows[:limit]


def build_admin_dashboard_payload(
    *, send_alerts: bool = False, include_static: bool = True
) -> dict:
    from core.admin_dashboard_payload import (
        build_admin_dashboard_payload as _build_admin_dashboard_payload,
    )

    return _build_admin_dashboard_payload(
        send_alerts=send_alerts,
        include_static=include_static,
    )
