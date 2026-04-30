from __future__ import annotations

from flask import current_app

from core.admin_dashboard_utils import (
    scalar_value,
    security_action_filter_sql,
    serialize_rows,
)
from core.db import db_fetchall
from core.rate_limit import get_banned_ips_snapshot, get_rate_limit_snapshot
from core.security_alerts import maybe_send_security_alerts
from core.security_banner import build_security_banner
from core.security_incidents import (
    load_recent_security_incidents,
    maybe_create_security_incidents,
)
from core.security_intelligence import (
    build_attack_intelligence,
    build_attack_map_points,
    build_threat_scores,
)
from core.security_settings import load_security_settings
from routes.admin_parts.helpers import (
    build_locked_username_snapshot,
    build_recent_staff_sessions,
)


def build_admin_dashboard_payload(
    *, send_alerts: bool = False, include_static: bool = True
) -> dict:
    is_pg = bool(current_app.config.get("DATABASE_URL"))
    settings = load_security_settings()

    total_users = 0
    active_users = 0
    recent_audit = []

    if include_static:
        total_users = scalar_value(db_fetchall("SELECT COUNT(*) AS c FROM staff_users"))

        active_users = scalar_value(
            db_fetchall(
                "SELECT COUNT(*) AS c FROM staff_users WHERE is_active = %s"
                if is_pg
                else "SELECT COUNT(*) AS c FROM staff_users WHERE is_active = ?",
                (True if is_pg else 1,),
            )
        )

        recent_audit = db_fetchall(
            """
            SELECT
                a.id,
                a.entity_type,
                a.action_type,
                a.action_details,
                a.created_at,
                COALESCE(su.username, '') AS staff_username
            FROM audit_log a
            LEFT JOIN staff_users su ON su.id = a.staff_user_id
            ORDER BY a.id DESC
            LIMIT %s
            """
            if is_pg
            else """
            SELECT
                a.id,
                a.entity_type,
                a.action_type,
                a.action_details,
                a.created_at,
                COALESCE(su.username, '') AS staff_username
            FROM audit_log a
            LEFT JOIN staff_users su ON su.id = a.staff_user_id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (10,),
        )

    attack_where_sql, attack_where_params = security_action_filter_sql()
    attack_where_sql_a, attack_where_params_a = security_action_filter_sql("a")

    failed_login_count = scalar_value(
        db_fetchall(
            f"""
            SELECT COUNT(*) AS c
            FROM audit_log
            WHERE {attack_where_sql}
              AND NULLIF(created_at, '')::timestamptz >= NOW() - INTERVAL '24 hours'
            """
            if is_pg
            else f"""
            SELECT COUNT(*) AS c
            FROM audit_log
            WHERE {attack_where_sql}
              AND created_at >= datetime('now', '-24 hours')
            """,
            attack_where_params,
        )
    )

    failed_logins_24h = db_fetchall(
        f"""
        SELECT
            a.id,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE {attack_where_sql_a}
          AND NULLIF(a.created_at, '')::timestamptz >= NOW() - INTERVAL '24 hours'
        ORDER BY a.id DESC
        LIMIT %s
        """
        if is_pg
        else f"""
        SELECT
            a.id,
            a.action_type,
            a.action_details,
            a.created_at,
            COALESCE(su.username, '') AS staff_username
        FROM audit_log a
        LEFT JOIN staff_users su ON su.id = a.staff_user_id
        WHERE {attack_where_sql_a}
          AND a.created_at >= datetime('now', '-24 hours')
        ORDER BY a.id DESC
        LIMIT ?
        """,
        attack_where_params_a + (200,),
    )

    recent_failed_logins = failed_logins_24h[:10]
    top_attacking_ips, targeted_usernames = build_attack_intelligence(failed_logins_24h)
    top_threats, top_threat_score = build_threat_scores(failed_logins_24h)
    attack_map_points = build_attack_map_points(top_attacking_ips)

    banned_ips = get_banned_ips_snapshot()
    locked_usernames = build_locked_username_snapshot()
    rate_limit_activity = get_rate_limit_snapshot()
    recent_staff_sessions = build_recent_staff_sessions()

    kiosk_security_events = db_fetchall(
        """
        SELECT action_type, action_details, created_at
        FROM audit_log
        WHERE action_type LIKE 'kiosk_%%'
           OR action_type LIKE 'resident_signin_%%'
        ORDER BY id DESC
        LIMIT %s
        """
        if is_pg
        else """
        SELECT action_type, action_details, created_at
        FROM audit_log
        WHERE action_type LIKE 'kiosk_%'
           OR action_type LIKE 'resident_signin_%'
        ORDER BY id DESC
        LIMIT ?
        """,
        (10,),
    )

    maybe_create_security_incidents(
        failed_login_count=int(failed_login_count or 0),
        top_attacking_ips=top_attacking_ips,
        targeted_usernames=targeted_usernames,
        banned_ips=banned_ips,
        locked_usernames=locked_usernames,
        settings=settings,
        top_threat_score=top_threat_score,
        top_threats=top_threats,
    )

    recent_security_incidents = load_recent_security_incidents()

    if send_alerts:
        maybe_send_security_alerts(
            failed_login_count=int(failed_login_count or 0),
            top_attacking_ips=top_attacking_ips,
            targeted_usernames=targeted_usernames,
            banned_ips=banned_ips,
            locked_usernames=locked_usernames,
            settings=settings,
            top_threat_score=top_threat_score,
            top_threats=top_threats,
        )

    security_banner = build_security_banner(
        failed_login_count=int(failed_login_count or 0),
        top_attacking_ips=top_attacking_ips,
        targeted_usernames=targeted_usernames,
        banned_ips=banned_ips,
        locked_usernames=locked_usernames,
        settings=settings,
        top_threat_score=int(top_threat_score or 0),
        top_threats=top_threats,
    )

    return {
        "settings": settings,
        "total_users": int(total_users or 0),
        "active_users": int(active_users or 0),
        "recent_audit": recent_audit,
        "failed_login_count": int(failed_login_count or 0),
        "recent_failed_logins": recent_failed_logins,
        "top_attacking_ips": top_attacking_ips,
        "targeted_usernames": targeted_usernames,
        "top_threats": top_threats,
        "top_threat_score": int(top_threat_score or 0),
        "attack_map_points": attack_map_points,
        "banned_ips": banned_ips,
        "locked_usernames": locked_usernames,
        "rate_limit_activity": rate_limit_activity,
        "kiosk_security_events": kiosk_security_events,
        "recent_staff_sessions": recent_staff_sessions,
        "recent_security_incidents": recent_security_incidents,
        "security_banner": security_banner,
        "live_payload": {
            "settings": settings,
            "failed_login_count": int(failed_login_count or 0),
            "recent_audit": serialize_rows(
                recent_audit, ["created_at", "staff_username", "action_type", "action_details"]
            ),
            "recent_failed_logins": serialize_rows(
                recent_failed_logins, ["created_at", "action_type", "action_details"]
            ),
            "kiosk_security_events": serialize_rows(
                kiosk_security_events, ["created_at", "action_type", "action_details"]
            ),
            "recent_staff_sessions": recent_staff_sessions,
            "recent_security_incidents": recent_security_incidents,
            "top_attacking_ips": top_attacking_ips,
            "targeted_usernames": targeted_usernames,
            "top_threats": top_threats,
            "top_threat_score": int(top_threat_score or 0),
            "attack_map_points": attack_map_points,
            "banned_ips": banned_ips,
            "locked_usernames": locked_usernames,
            "rate_limit_activity": rate_limit_activity,
            "security_banner": security_banner,
        },
    }
