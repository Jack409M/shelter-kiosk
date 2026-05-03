from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from flask import session

from core.db import db_fetchone, get_db
from core.scheduler_job_history import fail_job_run, finish_job_run, start_job_run
from core.sh_events import safe_log_sh_event
from core.system_alerts import create_system_alert
from routes.rent_tracking_parts.data_access import _load_sheet_entries
from routes.rent_tracking_parts.dates import _current_year_month, _month_label
from routes.rent_tracking_parts.views import (
    _ensure_sheet_for_month,
    _post_monthly_charge_ledger_entries,
)

RENT_CHARGE_SHELTERS: tuple[str, ...] = ("abba", "haven", "gratitude")
MONTHLY_RENT_CHARGE_JOB_NAME = "monthly_rent_charge_posting"
MONTHLY_RENT_CHARGE_JOB_LABEL = "Monthly Rent Charge Posting"
MONTHLY_RENT_CHARGE_SCHEDULE_LABEL = (
    "Runs once per month during days 1 through 3 in Chicago time"
)


@dataclass(slots=True)
class RentChargeJobResult:
    shelter: str
    rent_year: int
    rent_month: int
    entry_count: int


def _normalized_shelters(shelters: Iterable[str]) -> list[str]:
    values: list[str] = []
    for shelter in shelters:
        normalized = str(shelter or "").strip().lower()
        if normalized and normalized not in values:
            values.append(normalized)
    return values


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
            shelter=shelter,
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


def _log_shelter_success_event(
    *,
    source: str,
    shelter: str,
    rent_year: int,
    rent_month: int,
    rent_month_label: str,
    entry_count: int,
) -> None:
    safe_log_sh_event(
        event_type="monthly_rent_charge_job",
        event_status="success",
        event_source=source,
        shelter=shelter,
        message=f"Monthly rent charges checked for {shelter} {rent_month_label}.",
        metadata={
            "shelter": shelter,
            "rent_year": rent_year,
            "rent_month": rent_month,
            "entry_count": entry_count,
        },
    )


def _log_shelter_error_event(
    *,
    source: str,
    shelter: str,
    rent_year: int,
    rent_month: int,
    rent_month_label: str,
    error_text: str,
) -> None:
    safe_log_sh_event(
        event_type="monthly_rent_charge_job",
        event_status="error",
        event_source=source,
        shelter=shelter,
        message=(
            f"Monthly rent charge job failed for {shelter} "
            f"{rent_month_label}: {error_text or 'Unknown error'}"
        ),
        metadata={
            "shelter": shelter,
            "rent_year": rent_year,
            "rent_month": rent_month,
            "error": error_text,
        },
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

    This job writes to scheduler_job_runs so the Background Job Monitor can show the
    monthly rent posting history alongside pass cleanup and other scheduled jobs.
    """
    results: list[RentChargeJobResult] = []

    with app.test_request_context("/_scheduled/monthly-rent-charges"):
        # Force the app DB adapter to initialize g.db_kind before rent schema code
        # branches on Postgres versus SQLite DDL.
        get_db()

        rent_year, rent_month = _current_year_month()
        rent_month_label = _month_label(rent_year, rent_month)
        shelter_list = _normalized_shelters(shelters)
        run_key = start_job_run(
            job_name=MONTHLY_RENT_CHARGE_JOB_NAME,
            job_label=MONTHLY_RENT_CHARGE_JOB_LABEL,
            metadata={
                "source": source,
                "schedule": MONTHLY_RENT_CHARGE_SCHEDULE_LABEL,
                "rent_year": rent_year,
                "rent_month": rent_month,
                "rent_month_label": rent_month_label,
                "shelters": shelter_list,
            },
        )
        shelter_results: list[dict[str, object]] = []
        error_count = 0

        try:
            for shelter in shelter_list:
                try:
                    result = _post_monthly_rent_for_shelter(
                        shelter=shelter,
                        rent_year=rent_year,
                        rent_month=rent_month,
                    )
                    results.append(result)
                    shelter_results.append(
                        {
                            "shelter": shelter,
                            "status": "success",
                            "entry_count": result.entry_count,
                        }
                    )
                    _log_shelter_success_event(
                        source=source,
                        shelter=shelter,
                        rent_year=rent_year,
                        rent_month=rent_month,
                        rent_month_label=rent_month_label,
                        entry_count=result.entry_count,
                    )
                except Exception as err:
                    error_count += 1
                    error_text = str(err)
                    alert_key = f"monthly_rent_charge:{shelter}:{rent_year:04d}-{rent_month:02d}"
                    shelter_results.append(
                        {
                            "shelter": shelter,
                            "status": "error",
                            "error": error_text,
                        }
                    )
                    app.logger.exception(
                        "monthly rent charge job failed for shelter=%s year=%s month=%s error=%s",
                        shelter,
                        rent_year,
                        rent_month,
                        error_text,
                    )
                    _log_shelter_error_event(
                        source=source,
                        shelter=shelter,
                        rent_year=rent_year,
                        rent_month=rent_month,
                        rent_month_label=rent_month_label,
                        error_text=error_text,
                    )
                    _alert_once_for_failed_month(
                        alert_key=alert_key,
                        shelter=shelter,
                        rent_month_label=rent_month_label,
                        error_text=error_text,
                    )

            metadata = {
                "source": source,
                "schedule": MONTHLY_RENT_CHARGE_SCHEDULE_LABEL,
                "rent_year": rent_year,
                "rent_month": rent_month,
                "rent_month_label": rent_month_label,
                "total_shelters": len(shelter_list),
                "success_count": len(results),
                "error_count": error_count,
                "shelter_results": shelter_results,
            }

            if error_count:
                message = (
                    f"Monthly rent posting completed with {error_count} shelter error(s) "
                    f"for {rent_month_label}."
                )
                fail_job_run(
                    run_key=run_key,
                    error_message=message,
                    metadata=metadata,
                )
                safe_log_sh_event(
                    event_type="monthly_rent_charge_job",
                    event_status="error",
                    event_source=source,
                    message=message,
                    metadata=metadata,
                )
            else:
                message = f"Monthly rent posting checked successfully for {rent_month_label}."
                finish_job_run(
                    run_key=run_key,
                    result_summary=message,
                    metadata=metadata,
                )
                safe_log_sh_event(
                    event_type="monthly_rent_charge_job",
                    event_status="success",
                    event_source=source,
                    message=message,
                    metadata=metadata,
                )
        except Exception as err:
            error_text = str(err)
            app.logger.exception("monthly rent charge job cycle failed error=%s", error_text)
            fail_job_run(
                run_key=run_key,
                error_message=error_text,
                metadata={
                    "source": source,
                    "schedule": MONTHLY_RENT_CHARGE_SCHEDULE_LABEL,
                    "rent_year": rent_year,
                    "rent_month": rent_month,
                    "rent_month_label": rent_month_label,
                    "phase": "monthly_rent_charge_cycle",
                    "shelter_results": shelter_results,
                },
            )
            safe_log_sh_event(
                event_type="monthly_rent_charge_job",
                event_status="error",
                event_source=source,
                message=f"Monthly rent posting cycle failed for {rent_month_label}: {error_text}",
                metadata={"error": error_text, "source": source},
            )
            raise

    return results
