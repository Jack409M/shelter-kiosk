from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.rent_reporting_service import (
    build_rent_financial_performance_report,
    build_rent_resident_drilldown,
    clean_report_year,
)

reports_rent_financial = Blueprint("reports_rent_financial", __name__)

_ALLOWED_SHELTERS = {"abba", "haven", "gratitude"}


def _clean_shelter(value: object | None) -> str:
    shelter = str(value or "abba").strip().lower()
    if shelter in _ALLOWED_SHELTERS:
        return shelter
    return "abba"


@reports_rent_financial.route("/staff/reports/rent-financial-performance")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def rent_financial_performance():
    year = clean_report_year(request.args.get("year"))
    report = build_rent_financial_performance_report(year)

    return render_template(
        "reports/rent_financial_performance.html",
        title="Rent Collection Performance",
        report=report,
    )


@reports_rent_financial.route("/staff/reports/rent-financial-performance/drilldown")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def rent_financial_drilldown():
    year = clean_report_year(request.args.get("year"))
    shelter = _clean_shelter(request.args.get("shelter"))
    drilldown = build_rent_resident_drilldown(year=year, shelter=shelter)

    return render_template(
        "reports/rent_financial_drilldown.html",
        title="Rent Collection Resident Drilldown",
        drilldown=drilldown,
    )


@reports_rent_financial.route("/staff/reports/rent-financial-performance/board-export")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def rent_financial_board_export():
    year = clean_report_year(request.args.get("year"))
    report = build_rent_financial_performance_report(year)

    return render_template(
        "reports/rent_financial_board_export.html",
        title="Rent Collection Board Export",
        report=report,
    )


@reports_rent_financial.route("/staff/reports/rent-financial-performance/export.csv")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def rent_financial_csv_export():
    year = clean_report_year(request.args.get("year"))
    report = build_rent_financial_performance_report(year)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Shelter",
        "Minimal Capacity Rent",
        "Historic Capacity Rent",
        "Rent Charged",
        "Cash Collected",
        "Work Credit Program Offset",
        "Total Rent Applied",
        "Vacancy Unoccupied Capacity",
        "Unpaid Rent After Credits",
        "Rent Collection Rate",
    ])

    for row in [*report.rows, report.totals]:
        writer.writerow([
            row.shelter_label,
            f"{row.minimal_capacity_rent:.2f}",
            f"{row.historic_capacity_rent:.2f}",
            f"{row.actual_charged_rent:.2f}",
            f"{row.cash_collected:.2f}",
            f"{row.work_credit:.2f}",
            f"{row.total_recovered:.2f}",
            f"{row.vacancy_loss:.2f}",
            f"{row.unrecovered_charged_rent:.2f}",
            "" if row.collection_rate is None else f"{row.collection_rate:.1f}%",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=rent_collection_performance_{year}.csv"
        },
    )
