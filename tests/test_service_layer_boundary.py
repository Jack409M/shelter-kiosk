from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTES_ROOT = PROJECT_ROOT / "routes"

DB_WRITE_IMPORTS = {"db_execute", "db_transaction"}

# Legacy route files that still contain direct DB write access.
# This list is intentionally frozen. New route files must move write logic
# into core service modules instead of importing db_execute or db_transaction.
LEGACY_ROUTE_DB_WRITE_FILES = {
    "routes/NP_placement.py",
    "routes/RR_rent_admin.py",
    "routes/admin_parts/dashboard.py",
    "routes/admin_parts/data_quality_repairs.py",
    "routes/admin_parts/duplicate_merge_review.py",
    "routes/admin_parts/duplicate_primary_selection.py",
    "routes/admin_parts/sh_data_quality.py",
    "routes/admin_parts/users.py",
    "routes/attendance_parts/board.py",
    "routes/attendance_parts/helpers.py",
    "routes/attendance_parts/pass_action_helpers.py",
    "routes/auth.py",
    "routes/calendar.py",
    "routes/case_management_parts/actions.py",
    "routes/case_management_parts/budget_sessions.py",
    "routes/case_management_parts/exit.py",
    "routes/case_management_parts/family.py",
    "routes/case_management_parts/followups.py",
    "routes/case_management_parts/income_state_sync.py",
    "routes/case_management_parts/income_support.py",
    "routes/case_management_parts/intake_drafts.py",
    "routes/case_management_parts/intake_income_support.py",
    "routes/case_management_parts/intake_inserts.py",
    "routes/case_management_parts/medications.py",
    "routes/case_management_parts/needs.py",
    "routes/case_management_parts/promotion_review.py",
    "routes/case_management_parts/recovery_profile.py",
    "routes/case_management_parts/resident_case_enrollment_context.py",
    "routes/case_management_parts/resident_status.py",
    "routes/case_management_parts/schema_helpers.py",
    "routes/case_management_parts/transfer.py",
    "routes/case_management_parts/ua_log.py",
    "routes/case_management_parts/update.py",
    "routes/case_management_parts/update_needs.py",
    "routes/case_management_parts/update_note_services.py",
    "routes/case_management_parts/update_summary_rows.py",
    "routes/inspection_v2.py",
    "routes/operations_settings_parts/employment_income_settings_controller.py",
    "routes/operations_settings_parts/inspection_settings_controller.py",
    "routes/operations_settings_parts/pass_settings_controller.py",
    "routes/operations_settings_parts/settings_store.py",
    "routes/rent_tracking_parts/RR_rent_config.py",
    "routes/rent_tracking_parts/data_access.py",
    "routes/rent_tracking_parts/schema.py",
    "routes/rent_tracking_parts/settings.py",
    "routes/rent_tracking_parts/views.py",
    "routes/reports.py",
    "routes/resident_detail_parts/actions.py",
    "routes/resident_parts/consent.py",
    "routes/resident_parts/pass_request_helpers.py",
    "routes/resident_parts/resident_profile.py",
    "routes/resident_parts/resident_transfer_helpers.py",
    "routes/resident_portal_parts/budget.py",
    "routes/resident_portal_parts/daily_log.py",
    "routes/resident_portal_parts/helpers.py",
    "routes/residents.py",
    "routes/shelter_operations.py",
    "routes/staff_email_admin.py",
    "routes/transport.py",
    "routes/twilio.py",
    "routes/writeups.py",
}


def _imports_db_write_tool(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.db":
            for alias in node.names:
                if alias.name in DB_WRITE_IMPORTS:
                    return True
    return False


def test_no_new_route_files_import_db_write_tools() -> None:
    current_files = set()

    for path in sorted(ROUTES_ROOT.rglob("*.py")):
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        if _imports_db_write_tool(tree):
            current_files.add(relative_path)

    new_files = sorted(current_files - LEGACY_ROUTE_DB_WRITE_FILES)

    assert not new_files, (
        "New route files must not import db_execute or db_transaction. "
        "Move write logic into a core service module instead. New violations:\n"
        + "\n".join(new_files)
    )
