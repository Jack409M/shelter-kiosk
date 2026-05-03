from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from flask import session

from core.db import db_fetchone, get_db
from core.sh_events import safe_log_sh_event
from core.system_alerts import create_system_alert
from routes.rent_tracking_parts.data_access import _load_sheet_entries
from routes.rent_tracking_parts.dates import _current_year_month, _month_label
from routes.rent_tracking_parts.views import (
    _ensure_sheet_for_month,
    _post_monthly_charge_ledger_entries,
)

RENT_CHARGE_SHELTERS: tuple[str, ...] = ("abba", "haven", "gratitude")


@dataclass(slots=True)
class RentChargeJobResult:
    shelter: str
    rent_year: int
    rent_month: int
    entry_count: int


def _post_monthly_rent_for_shelter(
    *,
    shelter: str,
    rent_year: int,
    rent_month: int,
) -> RentChargeJobResult:
    session["shelter"] = shelter
    session["staff_user_id"] = None

    sheet, settings = _ensure_sheet_for_month(shelter, rent_year, rent_month)
    entries = _load_sheet_entries(sheet["id"])
    _post_monthly_charge_ledger_entries(
        shelter=shelter,
        rent_year=rent_year,
        rent_month=rent_month,
        sheet=sheet,
        entries=entries,
        settings=settings,
    )

    return RentChargeJobResult(
        shelter=shelter,
        rent_year=rent_year,
        rent_month=rent_month,
        entry_count=len(entries),
    )


def _open_alert_exists(alert_key: str) -> bool:
    row = db_fetchone(
        """
        SELECT id
        FROM system_alerts
        WHERE alert_key = %s
          AND status = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (alert_key, "open"),
    )
    return bool(row)


def _alert_once_for_failed_month(
    *,
    alert_key: str,
    shelter: str,
    rent_month_label: str,
    error_text: str,
) -> None:
    if _open_alert_exists(alert_key):
        safe_log_sh_event(
            event_type="monthly_rent_charge_job",
            event_status="error_suppressed",
            event_source="rent_charge_job",
            message=f"Repeated monthly rent charge failure suppressed for {shelter} {rent_month_label}.",
            metadata={
                "alert_key": alert_key,
                "shelter": shelter,
                "rent_month_label": rent_month_label,
                "error": error_text,
            },
        )
        return

    create_system_alert(
        alert_type="scheduled_job",
        severity="critical",
        title="Monthly rent posting failed",
        message=(
            f"Monthly rent charge posting failed for {shelter} {rent_month_label}. "
            f"Error: {error_text or 'Unknown error'}"
        ),
        source_module="rent_charge_job",
        alert_key=alert_key,
        metadata=error_text,
    )


def run_monthly_rent_charge_job(
    app,
    *,
    source: str = "in_app_scheduler",
    shelters: Iterable[str] = RENT_CHARGE_SHELTERS,
) -> list[RentChargeJobResult]:
    """
    Ensure monthly rent charges are posted for the current Chicago month.

    The rent ledger posting function is idempotent per resident sheet entry. Re-running
    this job for the same month checks for missing entries without duplicating charges.
    """
    results: list[RentChargeJobResult] = []

    with app.test_request_context("/_scheduled/monthly-rent-charges"):
        # Force the app DB adapter to initialize g.db_kind before rent schema code
        # branches on Postgres versus SQLite DDL.
        get_db()

        rent_year, rent_month = _current_year_month()
        rent_month_label = _month_label(rent_year, rent_month)

        for shelter in shelters:
            normalized_shelter = str(shelter or "").strip().lower()
            if not normalized_shelter:
                continue

            try:
                result = _post_monthly_rent_for_shelter(
                    shelter=normalized_shelter,
                    rent_year=rent_year,
                    rent_month=rent_month,
                )
                results.append(result)
                safe_log_sh_event(
                    event_type="monthly_rent_charge_job",
                    event_status="ok",
                    event_source=source,
                    message=f"Monthly rent charges checked for {normalized_shelter} {rent_month_label}.",
                    metadata={
                        "shelter": normalized_shelter,
                        "rent_year": rent_year,
                        "rent_month": rent_month,
                        "entry_count": result.entry_count,
                    },
                )
            except Exception as err:
                error_text = str(err)
                alert_key = (
                    f"monthly_rent_charge:{normalized_shelter}:"
                    f"{rent_year:04d}-{rent_month:02d}"
                )
                app.logger.exception(
                    "monthly rent charge job failed for shelter=%s year=%s month=%s error=%s",
                    normalized_shelter,
                    rent_year,
                    rent_month,
                    error_text,
                )
                safe_log_sh_event(
                    event_type="monthly_rent_charge_job",
                    event_status="error",
                    event_source=source,
                    message=(
                        f"Monthly rent charge job failed for {normalized_shelter} "
                        f"{rent_month_label}: {error_text or 'Unknown error'}"
                    ),
                    metadata={
                        "shelter": normalized_shelter,
                        "rent_year": rent_year,
                        "rent_month": rent_month,
                        "error": error_text,
                    },
                )
                _alert_once_for_failed_month(
                    alert_key=alert_key,
                    shelter=normalized_shelter,
                    rent_month_label=rent_month_label,
                    error_text=error_text,
                )

    return results
