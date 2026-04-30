from __future__ import annotations


def _security_status_from_conditions(
    *,
    banned_ips: list[dict],
    locked_usernames: list[dict],
    top_threat_score: int,
    failed_login_count: int,
    settings: dict,
) -> tuple[str, str]:
    if banned_ips or locked_usernames or top_threat_score >= 20:
        return "critical", "Critical threat level"

    if top_threat_score >= 10 or failed_login_count >= int(
        settings.get("failed_login_alert_threshold", 15) or 15
    ):
        return "elevated", "Elevated threat level"

    if failed_login_count > 0:
        return "guarded", "Guarded"

    return "normal", "Normal"


def build_security_banner(
    *,
    failed_login_count: int,
    top_attacking_ips: list[dict],
    targeted_usernames: list[dict],
    banned_ips: list[dict],
    locked_usernames: list[dict],
    settings: dict,
    top_threat_score: int = 0,
    top_threats: list[dict] | None = None,
) -> dict:
    top_threats = top_threats or []

    level_key, status_label = _security_status_from_conditions(
        banned_ips=banned_ips,
        locked_usernames=locked_usernames,
        top_threat_score=int(top_threat_score or 0),
        failed_login_count=int(failed_login_count or 0),
        settings=settings,
    )

    primary_risk = "No active hostile pattern detected"
    recommended_action = "Continue monitoring"
    recommended_reason = "No bans, lockouts, or major hostile clusters are active right now."
    focal_value = ""
    focal_type = ""

    if banned_ips:
        row = banned_ips[0]
        ip = str(row.get("ip", "") or "").strip() or "unknown"
        primary_risk = "Active banned IP still hitting the system"
        recommended_action = f"Block IP {ip} upstream and review related events"
        recommended_reason = (
            f"An IP is currently banned and remains the highest priority threat. IP {ip}."
        )
        focal_value = ip
        focal_type = "ip"

    elif locked_usernames:
        row = locked_usernames[0]
        username = str(row.get("username", "") or "").strip() or "unknown"
        seconds_remaining = int(row.get("seconds_remaining", 0) or 0)
        primary_risk = "Staff account under active lockout pressure"
        recommended_action = f"Investigate username {username}"
        recommended_reason = (
            f"That username is currently locked from repeated failures. "
            f"{seconds_remaining} seconds remain on the lock."
        )
        focal_value = username
        focal_type = "username"

    elif top_threats and int(top_threat_score or 0) >= 10:
        row = top_threats[0]
        ip = str(row.get("ip", "") or "").strip() or "unknown"
        score = int(row.get("score", 0) or 0)
        events = int(row.get("events", 0) or 0)
        summary = str(row.get("summary", "") or "").strip()
        primary_risk = "Concentrated hostile activity from one IP"
        recommended_action = f"Block IP {ip}"
        recommended_reason = (
            f"That IP reached threat score {score} across {events} hostile events. {summary}"
        )
        focal_value = ip
        focal_type = "ip"

    elif top_attacking_ips and int(top_attacking_ips[0].get("attempts", 0) or 0) >= int(
        settings.get("attacker_ip_alert_threshold", 10) or 10
    ):
        row = top_attacking_ips[0]
        ip = str(row.get("ip", "") or "").strip() or "unknown"
        attempts = int(row.get("attempts", 0) or 0)
        primary_risk = "High volume hostile traffic from one IP"
        recommended_action = f"Review and consider blocking IP {ip}"
        recommended_reason = f"That IP generated {attempts} hostile events in the last 24 hours."
        focal_value = ip
        focal_type = "ip"

    elif targeted_usernames and int(targeted_usernames[0].get("attempts", 0) or 0) >= int(
        settings.get("targeted_username_alert_threshold", 10) or 10
    ):
        row = targeted_usernames[0]
        username = str(row.get("username", "") or "").strip() or "unknown"
        attempts = int(row.get("attempts", 0) or 0)
        primary_risk = "Repeated targeting of one username"
        recommended_action = f"Investigate username {username}"
        recommended_reason = (
            f"That username appeared in {attempts} hostile events in the last 24 hours."
        )
        focal_value = username
        focal_type = "username"

    elif int(failed_login_count or 0) >= int(
        settings.get("failed_login_alert_threshold", 15) or 15
    ):
        primary_risk = "High hostile event volume across the system"
        recommended_action = "Review recent failed login activity now"
        recommended_reason = (
            f"Hostile security events reached {int(failed_login_count or 0)} in the last 24 hours."
        )

    elif int(failed_login_count or 0) > 0:
        primary_risk = "Low level hostile activity detected"
        recommended_action = "Monitor live activity and review top offenders"
        recommended_reason = (
            f"There were {int(failed_login_count or 0)} hostile events in the last 24 hours."
        )

    headline = f"Security Status: {status_label}"

    return {
        "status": level_key,
        "headline": headline,
        "status_label": status_label,
        "primary_risk": primary_risk,
        "recommended_action": recommended_action,
        "recommended_reason": recommended_reason,
        "focal_value": focal_value,
        "focal_type": focal_type,
        "failed_login_count": int(failed_login_count or 0),
        "top_threat_score": int(top_threat_score or 0),
        "banned_ip_count": len(banned_ips or []),
        "locked_username_count": len(locked_usernames or []),
    }
