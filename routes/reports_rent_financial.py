from __future__ import annotations

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.rent_reporting_service import (
    build_rent_financial_performance_report,
    clean_report_year,
)

reports_rent_financial = Blueprint("reports_rent_financial", __name__)


@reports_rent_financial.route("/staff/reports/rent-financial-performance")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def rent_financial_performance():
    year = clean_report_year(request.args.get("year"))
    report = build_rent_financial_performance_report(year)

    return render_template(
        "reports/rent_financial_performance.html",
        title="Rent Financial Performance",
        report=report,
    )
