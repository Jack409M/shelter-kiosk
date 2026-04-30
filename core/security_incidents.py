from __future__ import annotations

from flask import g

from core.admin_dashboard_utils import row_value
from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

INCIDENT_DEDUPE_WINDOWS = {
    "banned_ip": 3600,
    "locked_username": 3600,
    "attacker_ip_threshold": 3600,
    "targeted_username_threshold": 3600,
    "failed_logins_threshold": 7200,
    "threat_score_threshold": 7200,
}

SECURITY_INCIDENT_LOOKBACK_HOURS = 24


def load_recent_security_incidents(limit: int = 10) -> list[dict]:
    kind = g.get("db_kind")

    rows = db_fetchall(
        """
        SELECT id, incident_type, severity, title, details, related_ip, related_username, status, created_at
        FROM security_incidents
        WHERE NULLIF(created_at, '')::timestamptz >= NOW() - INTERVAL '24 hours'
        ORDER BY id DESC
        LIMIT %s
        """
        if kind == "pg"
        else """
        SELECT id, incident_type, severity, title, details, related_ip, related_username, status, created_at
        FROM security_incidents
        WHERE created_at >= datetime('now', '-24 hours')
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )

    incidents = []
    for row in rows or []:
        incidents.append(
            {
                "id": row_value(row, "id", ""),
                "incident_type": row_value(row, "incident_type", ""),
                "severity": row_value(row, "severity", ""),
                "title": row_value(row, "title", ""),
                "details": row_value(row, "details", ""),
                "related_ip": row_value(row, "related_ip", ""),
                "related_username": row_value(row, "related_username", ""),
                "status": row_value(row, "status", ""),
                "created_at": row_value(row, "created_at", ""),
            }
        )

    return incidents


def incident_exists_recently(
    incident_type: str,
    related_ip: str = "",
    related_username: str = "",
    window_seconds: int | None = None,
) -> bool:
    kind = g.get("db_kind")
    effective_window = int(window_seconds or INCIDENT_DEDUPE_WINDOWS.get(incident_type, 1800))

    rows = db_fetchall(
        """
        SELECT id
        FROM security_incidents
        WHERE incident_type = %s
          AND COALESCE(related_ip, '') = %s
          AND COALESCE(related_username, '') = %s
          AND NULLIF(created_at, '')::timestamptz >= NOW() - (%s * INTERVAL '1 second')
        ORDER BY id DESC
        LIMIT 1
        """
        if kind == "pg"
        else """
        SELECT id
        FROM security_incidents
        WHERE incident_type = ?
          AND COALESCE(related_ip, '') = ?
          AND COALESCE(related_username, '') = ?
          AND created_at >= datetime('now', '-' || ? || ' seconds')
        ORDER BY id DESC
        LIMIT 1
        """,
        (incident_type, related_ip or "", related_username or "", effective_window),
    )
    return bool(rows)


def create_security_incident(
    incident_type: str,
    severity: str,
    title: str,
    details: str,
    related_ip: str = "",
    related_username: str = "",
    dedupe_window_seconds: int | None = None,
) -> None:
    if incident_exists_recently(incident_type, related_ip, related_username, dedupe_window_seconds):
        return

    now = utcnow_iso()
    kind = g.get("db_kind")

    db_execute(
        """
        INSERT INTO security_incidents (
            incident_type,
            severity,
            title,
            details,
            related_ip,
            related_username,
            status,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if kind == "pg"
        else """
        INSERT INTO security_incidents (
            incident_type,
            severity,
            title,
            details,
            related_ip,
            related_username,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            incident_type,
            severity,
            title,
            details,
            related_ip or "",
            related_username or "",
            "open",
            now,
            now,
        ),
    )


def maybe_create_security_incidents(
    *,
    failed_login_count: int,
    top_attacking_ips: list[dict],
    targeted_usernames: list[dict],
    banned_ips: list[dict],
    locked_usernames: list[dict],
    settings: dict,
    top_threat_score: int = 0,
    top_threats: list[dict] | None = None,
) -> None:
    ip_threshold = settings["attacker_ip_alert_threshold"]
    user_threshold = settings["targeted_username_alert_threshold"]
    failed_threshold = settings["failed_login_alert_threshold"]
    top_threats = top_threats or []

    if banned_ips:
        row = banned_ips[0]
        create_security_incident(
            "banned_ip",
            "high",
            "Banned IP Active",
            f"An IP is currently banned for hostile activity. ip={row.get('ip', '')}",
            related_ip=row.get("ip", ""),
        )

    if locked_usernames:
        row = locked_usernames[0]
        create_security_incident(
            "locked_username",
            "high",
            "Locked Username Active",
            f"A username is currently locked due to repeated login failures. username={row.get('username', '')}",
            related_username=row.get("username", ""),
        )

    if top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0)) >= ip_threshold:
        row = top_attacking_ips[0]
        create_security_incident(
            "attacker_ip_threshold",
            "high",
            "Attacker IP Threshold Reached",
            f"IP {row.get('ip', '')} reached {row.get('attempts', 0)} hostile events in the last 24 hours.",
            related_ip=row.get("ip", ""),
        )

    if targeted_usernames and int(targeted_usernames[0].get("attempts", 0)) >= user_threshold:
        row = targeted_usernames[0]
        create_security_incident(
            "targeted_username_threshold",
            "high",
            "Username Targeting Threshold Reached",
            f"Username {row.get('username', '')} reached {row.get('attempts', 0)} hostile events in the last 24 hours.",
            related_username=row.get("username", ""),
        )

    if failed_login_count >= failed_threshold:
        create_security_incident(
            "failed_logins_threshold",
            "medium",
            "Failed Login Threshold Reached",
            f"Hostile security events reached {failed_login_count} in the last 24 hours.",
        )

    if top_threat_score >= 10 and top_threats:
        row = top_threats[0]
        create_security_incident(
            "threat_score_threshold",
            "high",
            "Threat Score Threshold Reached",
            f"IP {row.get('ip', '')} reached threat score {row.get('score', 0)} with {row.get('events', 0)} hostile events. {row.get('summary', '')}.",
            related_ip=row.get("ip", ""),
        )
