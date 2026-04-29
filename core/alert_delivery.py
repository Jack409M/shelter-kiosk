from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app, has_app_context

from core.sh_events import safe_log_sh_event

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
VALID_SEVERITIES = {"info", "warn", "error", "critical"}
SEVERITY_ORDER = {"info": 1, "warn": 2, "error": 3, "critical": 4}


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def _env_truthy(name: str) -> bool:
    return _env(name).lower() in TRUTHY_ENV_VALUES


def _split_recipients(value: str) -> list[str]:
    recipients: list[str] = []
    for part in str(value or "").replace(";", ",").split(","):
        cleaned = part.strip()
        if cleaned and cleaned not in recipients:
            recipients.append(cleaned)
    return recipients


def _normalize_severity(value: Any) -> str:
    severity = str(value or "").strip().lower()
    if severity not in VALID_SEVERITIES:
        return "warn"
    return severity


def _minimum_severity() -> str:
    severity = _normalize_severity(_env("ALERT_MIN_SEVERITY", "warn"))
    return severity


def _should_deliver(severity: str) -> bool:
    normalized = _normalize_severity(severity)
    minimum = _minimum_severity()
    return SEVERITY_ORDER[normalized] >= SEVERITY_ORDER[minimum]


def _safe_text(value: Any, max_length: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _alert_subject(alert: dict[str, Any]) -> str:
    app_name = _env("APP_NAME", "Shelter Kiosk")
    severity = _normalize_severity(alert.get("severity")).upper()
    title = _safe_text(alert.get("title"), 160)
    return f"[{app_name}] {severity}: {title}"


def _alert_body(alert: dict[str, Any]) -> str:
    lines = [
        _alert_subject(alert),
        "",
        f"Type: {_safe_text(alert.get('alert_type'))}",
        f"Source: {_safe_text(alert.get('source_module'))}",
        f"Severity: {_normalize_severity(alert.get('severity'))}",
        f"Key: {_safe_text(alert.get('alert_key'))}",
        "",
        "Message:",
        _safe_text(alert.get("message"), 2000),
    ]

    metadata = _safe_text(alert.get("metadata"), 2000)
    if metadata:
        lines.extend(["", "Metadata:", metadata])

    return "\n".join(lines).strip()


def _log_delivery(
    *,
    channel: str,
    status: str,
    alert: dict[str, Any],
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    safe_log_sh_event(
        event_type="system_alert_delivery",
        event_status=status,
        event_source=f"alert_delivery:{channel}",
        entity_type="system_alert",
        entity_id=None,
        message=message,
        metadata={
            "alert_key": _safe_text(alert.get("alert_key"), 240),
            "severity": _normalize_severity(alert.get("severity")),
            "channel": channel,
            **(metadata or {}),
        },
    )


def _send_email(alert: dict[str, Any]) -> bool:
    if not _env_truthy("ALERT_EMAIL_ENABLED"):
        return False

    recipients = _split_recipients(_env("ALERT_EMAIL_RECIPIENTS"))
    if not recipients:
        _log_delivery(
            channel="email",
            status="error",
            alert=alert,
            message="Alert email delivery is enabled but no recipients are configured.",
        )
        return False

    smtp_host = _env("SMTP_HOST")
    smtp_port_raw = _env("SMTP_PORT", "587")
    smtp_user = _env("SMTP_USERNAME")
    smtp_password = _env("SMTP_PASSWORD")
    smtp_from = _env("SMTP_FROM") or smtp_user

    if not smtp_host or not smtp_from:
        _log_delivery(
            channel="email",
            status="error",
            alert=alert,
            message="Alert email delivery is enabled but SMTP settings are incomplete.",
            metadata={"missing": "SMTP_HOST or SMTP_FROM"},
        )
        return False

    try:
        smtp_port = int(smtp_port_raw)
    except Exception:
        smtp_port = 587

    message = EmailMessage()
    message["Subject"] = _alert_subject(alert)
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(_alert_body(alert))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if _env_truthy("SMTP_USE_TLS") or smtp_port == 587:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(message)

        _log_delivery(
            channel="email",
            status="success",
            alert=alert,
            message="System alert email delivered.",
            metadata={"recipient_count": len(recipients)},
        )
        return True
    except Exception as err:
        if has_app_context():
            current_app.logger.exception("system_alert_email_delivery_failed")
        _log_delivery(
            channel="email",
            status="error",
            alert=alert,
            message="System alert email delivery failed.",
            metadata={"error": str(err)},
        )
        return False


def _send_webhook(alert: dict[str, Any]) -> bool:
    webhook_url = _env("ALERT_WEBHOOK_URL")
    if not webhook_url:
        return False

    payload = {
        "event": "system_alert_created",
        "alert_key": _safe_text(alert.get("alert_key"), 240),
        "alert_type": _safe_text(alert.get("alert_type"), 120),
        "severity": _normalize_severity(alert.get("severity")),
        "title": _safe_text(alert.get("title"), 240),
        "message": _safe_text(alert.get("message"), 2000),
        "source_module": _safe_text(alert.get("source_module"), 120),
        "metadata": _safe_text(alert.get("metadata"), 2000),
    }

    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = _env("ALERT_WEBHOOK_SECRET")
    if secret:
        headers["X-Shelter-Kiosk-Alert-Secret"] = secret

    request = Request(webhook_url, data=body, headers=headers, method="POST")

    try:
        with urlopen(request, timeout=10) as response:
            status_code = int(getattr(response, "status", 0) or 0)

        if 200 <= status_code < 300:
            _log_delivery(
                channel="webhook",
                status="success",
                alert=alert,
                message="System alert webhook delivered.",
                metadata={"status_code": status_code},
            )
            return True

        _log_delivery(
            channel="webhook",
            status="error",
            alert=alert,
            message="System alert webhook returned a non success status.",
            metadata={"status_code": status_code},
        )
        return False
    except HTTPError as err:
        _log_delivery(
            channel="webhook",
            status="error",
            alert=alert,
            message="System alert webhook delivery failed.",
            metadata={"status_code": err.code, "error": str(err)},
        )
        return False
    except URLError as err:
        _log_delivery(
            channel="webhook",
            status="error",
            alert=alert,
            message="System alert webhook delivery failed.",
            metadata={"error": str(err.reason)},
        )
        return False
    except Exception as err:
        if has_app_context():
            current_app.logger.exception("system_alert_webhook_delivery_failed")
        _log_delivery(
            channel="webhook",
            status="error",
            alert=alert,
            message="System alert webhook delivery failed.",
            metadata={"error": str(err)},
        )
        return False


def _send_sms(alert: dict[str, Any]) -> bool:
    if not _env_truthy("ALERT_SMS_ENABLED"):
        _log_delivery(
            channel="sms",
            status="error",
            alert=alert,
            message="Alert SMS delivery is disabled.",
            metadata={"missing_or_false": "ALERT_SMS_ENABLED"},
        )
        return False

    recipients = _split_recipients(_env("ALERT_SMS_RECIPIENTS"))
    if not recipients:
        _log_delivery(
            channel="sms",
            status="error",
            alert=alert,
            message="Alert SMS delivery is enabled but no recipients are configured.",
            metadata={"missing": "ALERT_SMS_RECIPIENTS"},
        )
        return False

    try:
        from core.sms_sender import send_sms, sms_delivery_ready
    except Exception as err:
        _log_delivery(
            channel="sms",
            status="error",
            alert=alert,
            message="Alert SMS delivery could not import the SMS sender.",
            metadata={"error": str(err)},
        )
        return False

    ready, reason = sms_delivery_ready()
    if not ready:
        _log_delivery(
            channel="sms",
            status="error",
            alert=alert,
            message="Alert SMS delivery is not ready.",
            metadata={"reason": reason},
        )
        return False

    sent_count = 0
    failed_count = 0
    sms_message = _safe_text(f"{_alert_subject(alert)}: {alert.get('message', '')}", 480)

    for recipient in recipients:
        try:
            if send_sms(recipient, sms_message, enforce_consent=False):
                sent_count += 1
            else:
                failed_count += 1
                _log_delivery(
                    channel="sms",
                    status="error",
                    alert=alert,
                    message="System alert SMS delivery was skipped or failed for one recipient.",
                    metadata={"recipient_suffix": recipient[-4:] if recipient else ""},
                )
        except Exception as err:
            failed_count += 1
            _log_delivery(
                channel="sms",
                status="error",
                alert=alert,
                message="System alert SMS delivery failed for one recipient.",
                metadata={"error": str(err)},
            )

    if sent_count:
        _log_delivery(
            channel="sms",
            status="success",
            alert=alert,
            message="System alert SMS delivered through Twilio.",
            metadata={"sent_count": sent_count, "failed_count": failed_count},
        )
        return True

    return False


def deliver_system_alert(alert: dict[str, Any]) -> dict[str, bool]:
    severity = _normalize_severity(alert.get("severity"))
    if not _should_deliver(severity):
        return {"email": False, "webhook": False, "sms": False}

    return {
        "email": _send_email(alert),
        "webhook": _send_webhook(alert),
        "sms": _send_sms(alert),
    }
