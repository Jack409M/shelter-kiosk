from __future__ import annotations


def build_attack_intelligence(failed_logins_24h):
    ip_counts = {}
    username_counts = {}

    for row in failed_logins_24h:
        details = (row.get("action_details") or "").lower()

        # crude extraction (matches current behavior)
        ip = None
        username = None

        for part in details.split():
            if part.startswith("ip="):
                ip = part.replace("ip=", "").strip()
            if part.startswith("username="):
                username = part.replace("username=", "").strip()

        if ip:
            ip_counts[ip] = ip_counts.get(ip, 0) + 1

        if username:
            username_counts[username] = username_counts.get(username, 0) + 1

    top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_usernames = sorted(username_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return top_ips, top_usernames


def build_threat_scores(failed_logins_24h):
    scores = {}

    for row in failed_logins_24h:
        details = (row.get("action_details") or "").lower()

        ip = None
        for part in details.split():
            if part.startswith("ip="):
                ip = part.replace("ip=", "").strip()

        if not ip:
            continue

        scores[ip] = scores.get(ip, 0) + 1

    top_threats = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
    top_score = top_threats[0][1] if top_threats else 0

    return top_threats, top_score


def build_attack_map_points(top_attacking_ips):
    return [
        {
            "ip": ip,
            "count": count,
        }
        for ip, count in top_attacking_ips
    ]
