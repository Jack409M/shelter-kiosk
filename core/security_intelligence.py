from __future__ import annotations

import ipaddress
from collections import Counter

from core.geoip import lookup_ip

THREAT_EVENT_SCORES = {
    "login_failed": 2,
    "resident_signin_failed": 1,
    "resident_signin_rate_limited": 3,
    "kiosk_manager_login_failed": 2,
    "kiosk_pin_failed": 2,
    "kiosk_pin_rate_limited": 4,
    "kiosk_checkout_failed": 2,
    "kiosk_checkout_rate_limited": 4,
    "kiosk_resident_code_locked": 4,
    "kiosk_resident_code_lock_started": 5,
    "login_rate_limited_ip": 4,
    "login_rate_limited_user": 4,
    "login_username_locked": 5,
    "login_ip_banned": 6,
    "login_blocked_banned_ip": 5,
    "cloudflare_bypass_blocked": 6,
    "banned_ip_blocked": 5,
    "bad_method_blocked": 5,
    "bad_user_agent_detected": 5,
    "bad_user_agent_banned": 6,
    "scanner_probe_detected": 5,
    "scanner_probe_banned": 7,
    "public_abuse_rate_limited": 4,
    "public_abuse_banned": 6,
}

THREAT_SUMMARY_LABELS = {
    "login_failed": "repeated staff login failures",
    "resident_signin_failed": "repeated resident sign in failures",
    "resident_signin_rate_limited": "resident sign in rate limiting",
    "kiosk_manager_login_failed": "repeated kiosk manager login failures",
    "kiosk_pin_failed": "repeated kiosk PIN failures",
    "kiosk_pin_rate_limited": "kiosk PIN rate limiting",
    "kiosk_checkout_failed": "repeated kiosk checkout failures",
    "kiosk_checkout_rate_limited": "kiosk checkout rate limiting",
    "kiosk_resident_code_locked": "resident code lock activity",
    "kiosk_resident_code_lock_started": "resident code lock started",
    "login_rate_limited_ip": "staff login IP rate limiting",
    "login_rate_limited_user": "staff login username rate limiting",
    "login_username_locked": "staff username lockouts",
    "login_ip_banned": "staff login IP bans",
    "login_blocked_banned_ip": "blocked banned IP login attempts",
    "cloudflare_bypass_blocked": "cloudflare bypass attempts",
    "banned_ip_blocked": "banned IP blocking activity",
    "bad_method_blocked": "blocked suspicious request methods",
    "bad_user_agent_detected": "suspicious user agent detection",
    "bad_user_agent_banned": "suspicious user agent bans",
    "scanner_probe_detected": "scanner probe activity",
    "scanner_probe_banned": "scanner probe bans",
    "public_abuse_rate_limited": "public form abuse rate limiting",
    "public_abuse_banned": "public form abuse bans",
}


def row_value(row, key: str, default=""):
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def extract_detail_value(details: str, key: str) -> str:
    if not details:
        return ""

    prefix = f"{key}="

    for line in details.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        for part in parts:
            if not part.startswith(prefix):
                continue

            value = part[len(prefix) :].strip()
            if not value:
                return ""

            if key == "ip":
                try:
                    return str(ipaddress.ip_address(value))
                except ValueError:
                    return ""

            return value

    return ""


def build_attack_intelligence(rows):
    ip_counter = Counter()
    username_counter = Counter()

    for row in rows or []:
        details = (
            row.get("action_details", "")
            if isinstance(row, dict)
            else row_value(row, "action_details", "")
        )
        ip = extract_detail_value(details, "ip")
        username = extract_detail_value(details, "username")

        if ip:
            ip_counter[ip] += 1

        if username:
            username_counter[username] += 1

    top_attacking_ips = [
        {"ip": ip, "attempts": attempts} for ip, attempts in ip_counter.most_common(10)
    ]

    targeted_usernames = [
        {"username": username, "attempts": attempts}
        for username, attempts in username_counter.most_common(10)
    ]

    return top_attacking_ips, targeted_usernames


def _human_threat_summary(type_counter: Counter) -> str:
    if not type_counter:
        return "Suspicious repeated behavior detected"

    ordered = [event_type for event_type, _count in type_counter.most_common()]
    top_types = ordered[:3]

    if len(top_types) == 1:
        return THREAT_SUMMARY_LABELS.get(top_types[0], top_types[0].replace("_", " ")).capitalize()

    labels = [
        THREAT_SUMMARY_LABELS.get(event_type, event_type.replace("_", " "))
        for event_type in top_types
    ]

    if len(set(labels)) == 1:
        return labels[0].capitalize()

    if len(type_counter) >= 3:
        first_two = labels[:2]
        return f"Mixed hostile activity including {first_two[0]} and {first_two[1]}"

    if len(labels) == 2:
        return f"Mixed hostile activity including {labels[0]} and {labels[1]}"

    return f"Mixed hostile activity including {labels[0]} and {labels[1]}"


def build_threat_scores(rows):
    per_ip = {}

    for row in rows or []:
        action_type = str(row_value(row, "action_type", "") or "").strip()
        details = row_value(row, "action_details", "") or ""
        ip = extract_detail_value(details, "ip")

        if not ip:
            continue

        score = int(THREAT_EVENT_SCORES.get(action_type, 1) or 1)
        item = per_ip.setdefault(
            ip,
            {
                "ip": ip,
                "score": 0,
                "events": 0,
                "types": Counter(),
                "last_seen": "",
            },
        )

        item["score"] += score
        item["events"] += 1
        item["types"][action_type] += 1

        created_at = str(row_value(row, "created_at", "") or "")
        if created_at > str(item["last_seen"]):
            item["last_seen"] = created_at

    top_threats = []
    for ip, item in per_ip.items():
        top_threats.append(
            {
                "ip": ip,
                "score": int(item["score"]),
                "events": int(item["events"]),
                "last_seen": item["last_seen"],
                "summary": _human_threat_summary(item["types"]),
            }
        )

    top_threats.sort(
        key=lambda item: (
            int(item.get("score", 0)),
            int(item.get("events", 0)),
            str(item.get("last_seen", "")),
        ),
        reverse=True,
    )

    top_threat_score = int(top_threats[0]["score"]) if top_threats else 0
    return top_threats[:10], top_threat_score


def build_attack_map_points(top_attacking_ips: list[dict]) -> list[dict]:
    points = []

    for row in top_attacking_ips or []:
        ip = str(row.get("ip", "") or "").strip()
        attempts = int(row.get("attempts", 0) or 0)

        if not ip:
            continue

        geo = lookup_ip(ip)

        lat = geo.get("lat")
        lon = geo.get("lon")

        if lat is None or lon is None:
            continue

        points.append(
            {
                "ip": ip,
                "attempts": attempts,
                "lat": lat,
                "lon": lon,
                "city": geo.get("city", ""),
                "region": geo.get("region", ""),
                "country": geo.get("country", ""),
            }
        )

    return points
