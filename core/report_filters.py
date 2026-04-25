"""
DWC Shelter Operations System
Reporting Filter Engine

Provides standardized filtering for statistics dashboards.

Filters supported
-----------------

Scope
    total_program
    abba
    haven
    gratitude

Population
    active
    exited
    all

Date Range
    this_month
    last_month
    this_quarter
    this_year
    last_year
    all_time
    custom
"""

from datetime import UTC, datetime, timedelta

# -----------------------------------------------------
# Date Range Helpers
# -----------------------------------------------------


def _utc_today():
    return datetime.now(UTC).date()


def _start_of_month(date):
    return date.replace(day=1)


def _start_of_year(date):
    return date.replace(month=1, day=1)


def _start_of_quarter(date):
    quarter = (date.month - 1) // 3
    month = quarter * 3 + 1
    return date.replace(month=month, day=1)


def resolve_date_range(range_key, start=None, end=None):
    """
    Converts a date range key into actual start and end dates.
    """

    today = _utc_today()

    if range_key == "this_month":
        start = _start_of_month(today)
        end = today

    elif range_key == "last_month":
        first = _start_of_month(today)
        end = first - timedelta(days=1)
        start = _start_of_month(end)

    elif range_key == "this_quarter":
        start = _start_of_quarter(today)
        end = today

    elif range_key == "this_year":
        start = _start_of_year(today)
        end = today

    elif range_key == "last_year":
        start = datetime(today.year - 1, 1, 1).date()
        end = datetime(today.year - 1, 12, 31).date()

    elif range_key == "custom":
        return start, end

    elif range_key == "all_time":
        return None, None

    else:
        return None, None

    return start, end


# -----------------------------------------------------
# SQL Filter Builder
# -----------------------------------------------------


def build_resident_filters(scope=None, population=None, date_range=None, start=None, end=None):
    """
    Build SQL WHERE clauses for resident based reporting.
    """

    where = []
    params = []

    # -----------------------------
    # Scope
    # -----------------------------

    if scope and scope != "total_program":
        where.append("shelter = ?")
        params.append(scope)

    # -----------------------------
    # Population
    # -----------------------------

    if population == "active":
        where.append("is_active = 1")

    elif population == "exited":
        where.append("is_active = 0")

    # "all" includes both

    # -----------------------------
    # Date Range
    # -----------------------------

    start_date, end_date = resolve_date_range(date_range, start, end)

    if start_date:
        where.append("date_entered >= ?")
        params.append(str(start_date))

    if end_date:
        where.append("date_entered <= ?")
        params.append(str(end_date))

    # -----------------------------
    # Final WHERE Clause
    # -----------------------------

    clause = "WHERE " + " AND ".join(where) if where else ""

    return clause, params


# -----------------------------------------------------
# Privacy Helpers
# -----------------------------------------------------


def mask_small_counts(value):
    """
    Mask small counts to avoid identification risk.
    """

    if value is None:
        return "0"

    if 0 < value < 5:
        return "<5"

    return str(value)
