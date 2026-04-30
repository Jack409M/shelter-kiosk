from __future__ import annotations

from flask import g

DASHBOARD_ATTACK_ACTION_TYPES = (
    "login_failed",
    "resident_signin_failed",
    "resident_signin_rate_limited",
    "kiosk_manager_login_failed",
    "kiosk_pin_failed",
    "kiosk_pin_rate_limited",
    "kiosk_checkout_failed",
    "kiosk_checkout_rate_limited",
    "kiosk_resident_code_locked",
    "kiosk_resident_code_lock_started",
    "login_rate_limited_ip",
    "login_rate_limited_user",
    "login_username_locked",
    "login_ip_banned",
    "login_blocked_banned_ip",
    "cloudflare_bypass_blocked",
    "banned_ip_blocked",
    "bad_method_blocked",
    "bad_user_agent_detected",
    "bad_user_agent_banned",
    "scanner_probe_detected",
    "scanner_probe_banned",
    "public_abuse_rate_limited",
    "public_abuse_banned",
)


def scalar_value(rows, default=0):
    if not rows:
        return default

    row = rows[0]

    if isinstance(row, dict):
        return next(iter(row.values()), default)

    if isinstance(row, list | tuple) and row:
        return row[0]

    return default


def row_value(row, key: str, default=""):
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except Exception:
        return default


def serialize_rows(rows, fields: list[str]) -> list[dict]:
    out = []

    for row in rows or []:
        item = {}
        for field in fields:
            value = row_value(row, field, "")
            item[field] = "" if value is None else value
        out.append(item)

    return out


def security_action_filter_sql(alias: str = "") -> tuple[str, tuple]:
    prefix = f"{alias}." if alias else ""
    placeholders = ", ".join(
        ["%s"] * len(DASHBOARD_ATTACK_ACTION_TYPES)
        if g.get("db_kind") == "pg"
        else ["?"] * len(DASHBOARD_ATTACK_ACTION_TYPES)
    )
    return f"{prefix}action_type IN ({placeholders})", tuple(DASHBOARD_ATTACK_ACTION_TYPES)
