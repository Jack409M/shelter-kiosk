from __future__ import annotations

from core.app_factory import create_app
from core.db import db_execute, db_fetchall, db_transaction
from core.runtime import init_db


DEMO_PREFIX = "demo-seed-20260406"


def fetch_ids(sql: str, params: tuple = ()) -> list[int]:
    rows = db_fetchall(sql, params)
    return [int(row["id"]) for row in rows or []]


def delete_by_id(table_name: str, row_id: int) -> None:
    db_execute(f"DELETE FROM {table_name} WHERE id = %s", (row_id,))


def delete_where_value(table_name: str, column_name: str, value) -> None:
    db_execute(f"DELETE FROM {table_name} WHERE {column_name} = %s", (value,))


def run_clear() -> None:
    resident_ids = fetch_ids(
        """
        SELECT id
        FROM residents
        WHERE resident_identifier LIKE %s
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    if not resident_ids:
        print(f"No demo residents found for prefix {DEMO_PREFIX}.")
        return

    enrollment_ids = fetch_ids(
        """
        SELECT id
        FROM program_enrollments
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    child_ids = fetch_ids(
        """
        SELECT id
        FROM resident_children
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    pass_ids = fetch_ids(
        """
        SELECT id
        FROM resident_passes
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    submission_ids = fetch_ids(
        """
        SELECT id
        FROM resident_form_submissions
        WHERE resident_id IN (
            SELECT id
            FROM residents
            WHERE resident_identifier LIKE %s
        )
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    case_update_ids = fetch_ids(
        """
        SELECT id
        FROM case_manager_updates
        WHERE enrollment_id IN (
            SELECT id
            FROM program_enrollments
            WHERE resident_id IN (
                SELECT id
                FROM residents
                WHERE resident_identifier LIKE %s
            )
        )
        ORDER BY id ASC
        """,
        (f"{DEMO_PREFIX}%",),
    )

    with db_transaction():
        for pass_id in pass_ids:
            delete_where_value("resident_pass_request_details", "pass_id", pass_id)

        for submission_id in submission_ids:
            delete_where_value("weekly_resident_summary", "submission_id", submission_id)

        for case_update_id in case_update_ids:
            delete_where_value("case_manager_update_summary", "case_manager_update_id", case_update_id)

        for child_id in child_ids:
            delete_where_value("resident_child_income_supports", "child_id", child_id)
            delete_where_value("child_services", "resident_child_id", child_id)

        for enrollment_id in enrollment_ids:
            delete_where_value("weekly_resident_summary", "enrollment_id", enrollment_id)
            delete_where_value("resident_form_submissions", "enrollment_id", enrollment_id)
            delete_where_value("client_services", "enrollment_id", enrollment_id)
            delete_where_value("case_manager_updates", "enrollment_id", enrollment_id)
            delete_where_value("resident_needs", "enrollment_id", enrollment_id)
            delete_where_value("resident_medications", "enrollment_id", enrollment_id)
            delete_where_value("resident_ua_log", "enrollment_id", enrollment_id)
            delete_where_value("resident_living_area_inspections", "enrollment_id", enrollment_id)
            delete_where_value("resident_budget_sessions", "enrollment_id", enrollment_id)
            delete_where_value("goals", "enrollment_id", enrollment_id)
            delete_where_value("appointments", "enrollment_id", enrollment_id)
            delete_where_value("child_services", "enrollment_id", enrollment_id)

        for resident_id in resident_ids:
            delete_where_value("resident_notifications", "resident_id", resident_id)
            delete_where_value("resident_passes", "resident_id", resident_id)
            delete_where_value("attendance_events", "resident_id", resident_id)
            delete_where_value("resident_transfers", "resident_id", resident_id)
            delete_where_value("resident_form_submissions", "resident_id", resident_id)
            delete_where_value("resident_medications", "resident_id", resident_id)
            delete_where_value("resident_ua_log", "resident_id", resident_id)
            delete_where_value("resident_living_area_inspections", "resident_id", resident_id)
            delete_where_value("resident_budget_sessions", "resident_id", resident_id)
            delete_where_value("chore_assignments", "resident_id", resident_id)
            delete_where_value("resident_substances", "resident_id", resident_id)
            delete_where_value("resident_children", "resident_id", resident_id)
            delete_where_value("program_enrollments", "resident_id", resident_id)

        for resident_id in resident_ids:
            delete_by_id("residents", resident_id)

    print(f"Removed demo data for {len(resident_ids)} residents with prefix {DEMO_PREFIX}.")


def main() -> None:
    app = create_app()
    with app.app_context():
        init_db()
        run_clear()


if __name__ == "__main__":
    main()
