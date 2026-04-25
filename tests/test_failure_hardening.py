from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from core import db as core_db
from core.helpers import utcnow_iso


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON_ROOTS = (
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "routes",
    PROJECT_ROOT / "db",
)
INTENTIONAL_EMPTY_FILES = {
    "routes/operations_settings_parts/kiosk_categories.py",
}
TRUNCATION_MARKERS = (
    "SNIP",
    "... unchanged",
    "rest unchanged",
    "truncated)",
    "<truncated>",
)
AI_REWRITE_PLACEHOLDER_MARKERS = (
    "TODO: implement later",
    "TODO implement later",
    "placeholder implementation",
    "temporary placeholder",
    "rest of file unchanged",
    "remaining code unchanged",
    "existing code unchanged",
    "previous code unchanged",
    "omitted for brevity",
    "implementation omitted",
    "not implemented yet",
)
LOGGING_FUNCTION_NAMES = {
    "log_action",
    "log_exception",
    "log_error",
    "log_warning",
    "print",
}
LOGGING_METHOD_NAMES = {
    "critical",
    "debug",
    "error",
    "exception",
    "info",
    "warning",
}
AUDIT_FUNCTION_NAMES = {
    "log_action",
    "audit_action",
    "write_audit_log",
}
LOG_ACTION_REQUIRED_ARGUMENTS = (
    "entity_type",
    "entity_id",
    "shelter",
    "staff_user_id",
    "action_type",
)
STATE_CHANGE_SQL_VERBS = {
    "insert",
    "update",
    "delete",
}
MUTATING_ROUTE_METHODS = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}
ALLOWED_CONTEXTLIB_SUPPRESS_EXCEPTION_PREFIXES = (
    "db/schema",
)
ALLOWED_CONTEXTLIB_SUPPRESS_EXCEPTION_FILES = {
    "core/db.py",
}
BASELINED_CONTEXTLIB_SUPPRESS_EXCEPTION_LOCATIONS = {
    ("core/kiosk_activity_categories.py", 261),
    ("core/kiosk_activity_categories.py", 309),
    ("routes/attendance_parts/pass_action_helpers.py", 357),
    ("routes/attendance_parts/print_views.py", 99),
    ("routes/case_management_parts/exit.py", 31),
    ("routes/case_management_parts/intake_income_support.py", 87),
    ("routes/inspection_v2.py", 136),
    ("routes/inspection_v2.py", 163),
    ("routes/rent_tracking_parts/schema.py", 456),
    ("routes/rent_tracking_parts/schema.py", 479),
    ("routes/rent_tracking_parts/schema.py", 488),
    ("routes/rent_tracking_parts/schema.py", 491),
    ("routes/rent_tracking_parts/schema.py", 494),
    ("routes/resident_parts/pass_request_helpers.py", 580),
    ("db/l9_schema_support.py", 257),
}
BASELINED_BARE_EXCEPTION_PASS_LOCATIONS = {
    ("core/stats/common.py", 63),
    ("routes/attendance_parts/pass_actions.py", 131),
    ("routes/case_management_parts/intake_income_support.py", 593),
    ("routes/resident_detail_parts/read.py", 20),
    ("routes/resident_detail_parts/read.py", 27),
    ("db/schema_goals.py", 89),
    ("db/schema_goals.py", 101),
    ("db/schema_outcomes.py", 157),
    ("db/schema_outcomes.py", 198),
    ("db/schema_outcomes.py", 316),
    ("db/schema_outcomes.py", 422),
    ("db/schema_outcomes.py", 440),
    ("db/schema_outcomes.py", 452),
    ("db/schema_outcomes.py", 464),
    ("db/schema_outcomes.py", 476),
    ("db/schema_people.py", 485),
    ("db/schema_requests.py", 254),
    ("db/schema_requests.py", 379),
}
BASELINED_BROAD_EXCEPTION_WITHOUT_LOG_OR_RERAISE_LOCATIONS = {
    ("core/attendance_hours.py", 70),
    ("core/attendance_hours.py", 77),
    ("core/attendance_hours.py", 100),
    ("core/attendance_hours.py", 110),
    ("core/attendance_hours.py", 50),
    ("core/attendance_hours.py", 103),
    ("core/db.py", 15),
    ("core/helpers.py", 88),
    ("core/helpers.py", 21),
    ("core/kiosk_activity_categories.py", 180),
    ("core/kiosk_activity_categories.py", 835),
    ("core/meeting_progress.py", 54),
    ("core/pass_retention.py", 27),
    ("core/pass_retention.py", 40),
    ("core/pass_retention.py", 51),
    ("core/pass_retention.py", 64),
    ("core/pass_rules.py", 28),
    ("core/pass_rules.py", 68),
    ("core/pass_rules.py", 153),
    ("core/pass_rules.py", 201),
    ("core/promotion_readiness.py", 19),
    ("core/sms.py", 62),
    ("core/sms.py", 79),
    ("core/sms_sender.py", 12),
    ("core/sms_sender.py", 102),
    ("core/sms_sender.py", 107),
    ("core/sms_sender.py", 87),
    ("core/stats/common.py", 23),
    ("core/stats/common.py", 32),
    ("core/stats/common.py", 44),
    ("core/stats/common.py", 19),
    ("core/stats/common.py", 35),
    ("core/stats/safe.py", 14),
    ("core/timezone.py", 15),
    ("routes/RR_rent_admin.py", 88),
    ("routes/admin_parts/helpers.py", 165),
    ("routes/admin_parts/helpers.py", 407),
    ("routes/admin_parts/helpers.py", 822),
    ("routes/admin_parts/helpers.py", 1071),
    ("routes/attendance_parts/board.py", 139),
    ("routes/attendance_parts/board.py", 149),
    ("routes/attendance_parts/board.py", 961),
    ("routes/attendance_parts/board.py", 1182),
    ("routes/attendance_parts/board.py", 1191),
    ("routes/attendance_parts/board.py", 834),
    ("routes/attendance_parts/board.py", 843),
    ("routes/attendance_parts/board.py", 852),
    ("routes/attendance_parts/board.py", 1023),
    ("routes/attendance_parts/board.py", 1034),
    ("routes/attendance_parts/board.py", 1045),
    ("routes/attendance_parts/board.py", 1248),
    ("routes/attendance_parts/board.py", 1259),
    ("routes/attendance_parts/board.py", 1270),
    ("routes/attendance_parts/helpers.py", 115),
    ("routes/attendance_parts/helpers.py", 122),
    ("routes/attendance_parts/helpers.py", 34),
    ("routes/attendance_parts/helpers.py", 46),
    ("routes/attendance_parts/pass_detail_data.py", 165),
    ("routes/attendance_parts/pass_detail_data.py", 205),
    ("routes/attendance_parts/pass_policy.py", 27),
    ("routes/attendance_parts/pass_policy.py", 82),
    ("routes/attendance_parts/pass_policy.py", 106),
    ("routes/attendance_parts/print_views.py", 74),
    ("routes/case_management_parts/intake_income_support.py", 96),
    ("routes/case_management_parts/intake_income_support.py", 105),
    ("routes/case_management_parts/intake_income_support.py", 114),
    ("routes/case_management_parts/intake_income_support.py", 169),
    ("routes/case_management_parts/intake_income_support.py", 189),
    ("routes/case_management_parts/l9_disposition.py", 199),
    ("routes/case_management_parts/l9_workspace.py", 40),
    ("routes/case_management_parts/l9_workspace.py", 230),
    ("routes/case_management_parts/l9_workspace.py", 271),
    ("routes/case_management_parts/promotion_review.py", 137),
    ("routes/case_management_parts/promotion_review.py", 603),
    ("routes/case_management_parts/promotion_review.py", 564),
    ("routes/case_management_parts/resident_case.py", 80),
    ("routes/case_management_parts/resident_case_discipline.py", 18),
    ("routes/case_management_parts/resident_case_employment.py", 9),
    ("routes/case_management_parts/resident_case_employment.py", 18),
    ("routes/case_management_parts/resident_case_viewmodel.py", 37),
    ("routes/case_management_parts/transfer.py", 38),
    ("routes/case_management_parts/transfer.py", 365),
    ("routes/case_management_parts/transfer.py", 104),
    ("routes/case_management_parts/update.py", 441),
    ("routes/case_management_parts/update.py", 551),
    ("routes/field_audit.py", 43),
    ("routes/field_audit.py", 40),
    ("routes/inspection_v2.py", 382),
    ("routes/operations_settings_parts/parsing.py", 16),
    ("routes/operations_settings_parts/parsing.py", 23),
    ("routes/operations_settings_parts/parsing.py", 50),
    ("routes/operations_settings_parts/parsing.py", 61),
    ("routes/rent_tracking_parts/dates.py", 29),
    ("routes/rent_tracking_parts/schema.py", 175),
    ("routes/rent_tracking_parts/utils.py", 15),
    ("routes/rent_tracking_parts/utils.py", 24),
    ("routes/reports.py", 133),
    ("routes/reports.py", 322),
    ("routes/reports.py", 386),
    ("routes/reports.py", 393),
    ("routes/reports.py", 409),
    ("routes/reports.py", 201),
    ("routes/reports_active_census.py", 33),
    ("routes/reports_income_change.py", 47),
    ("routes/reports_income_change.py", 56),
    ("routes/resident_parts/pass_request_helpers.py", 97),
    ("routes/resident_parts/pass_request_helpers.py", 137),
    ("routes/resident_parts/pass_request_helpers.py", 227),
    ("routes/resident_parts/pass_request_helpers.py", 241),
    ("routes/resident_parts/pass_request_helpers.py", 378),
    ("routes/resident_parts/pass_request_helpers.py", 394),
    ("routes/resident_parts/resident_transfer_helpers.py", 164),
    ("routes/resident_parts/resident_transfer_helpers.py", 199),
    ("routes/resident_parts/resident_transfer_helpers.py", 328),
    ("routes/resident_requests.py", 82),
    ("routes/system.py", 71),
    ("routes/transport.py", 42),
    ("routes/transport.py", 52),
    ("routes/twilio.py", 13),
    ("routes/twilio.py", 155),
    ("db/schema_bootstrap.py", 152),
    ("db/schema_people.py", 22),
    ("db/schema_shelter_operations.py", 274),
}
BASELINED_ROUTE_STATE_CHANGE_WITHOUT_AUDIT_LOCATIONS: set[tuple[str, str, int]] = set()
BASELINED_UNSTRUCTURED_LOG_ACTION_LOCATIONS = {
    ("routes/admin_parts/dashboard.py", 165),
    ("routes/admin_parts/dashboard.py", 195),
    ("routes/admin_parts/dashboard.py", 221),
    ("routes/admin_parts/dashboard.py", 251),
    ("routes/admin_parts/users.py", 653),
    ("routes/admin_parts/users.py", 698),
    ("routes/admin_parts/users.py", 738),
    ("routes/admin_parts/users.py", 376),
    ("routes/admin_parts/users.py", 595),
    ("routes/attendance_parts/board.py", 742),
    ("routes/auth.py", 301),
    ("routes/auth.py", 323),
    ("routes/auth.py", 81),
    ("routes/auth.py", 97),
    ("routes/auth.py", 180),
    ("routes/auth.py", 188),
    ("routes/auth.py", 200),
    ("routes/auth.py", 207),
    ("routes/auth.py", 222),
    ("routes/auth.py", 246),
    ("routes/auth.py", 265),
    ("routes/auth.py", 281),
    ("routes/auth.py", 416),
    ("routes/kiosk.py", 167),
    ("routes/kiosk.py", 253),
    ("routes/kiosk.py", 273),
    ("routes/kiosk.py", 294),
    ("routes/kiosk.py", 313),
    ("routes/kiosk.py", 361),
    ("routes/kiosk.py", 549),
    ("routes/kiosk.py", 343),
    ("routes/reports.py", 1156),
    ("routes/reports.py", 1215),
    ("routes/reports.py", 1125),
    ("routes/resident_parts/consent.py", 154),
    ("routes/resident_parts/consent.py", 130),
    ("routes/resident_requests.py", 195),
    ("routes/resident_requests.py", 291),
    ("routes/resident_requests.py", 165),
    ("routes/resident_requests.py", 179),
    ("routes/residents.py", 518),
    ("routes/transport.py", 346),
}


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_PYTHON_ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    return files


def _route_python_files() -> list[Path]:
    return sorted((PROJECT_ROOT / "routes").rglob("*.py"))


def _is_exception_name(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "Exception"
    if isinstance(node, ast.Attribute):
        return node.attr == "Exception"
    return False


def _is_not_implemented_error_name(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "NotImplementedError"
    if isinstance(node, ast.Attribute):
        return node.attr == "NotImplementedError"
    return False


def _is_contextlib_suppress_exception_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False

    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "suppress"
        and isinstance(func.value, ast.Name)
        and func.value.id == "contextlib"
    ):
        return False

    return any(_is_exception_name(arg) for arg in node.args)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent_name = _call_name(node.value)
        if parent_name:
            return f"{parent_name}.{node.attr}"
        return node.attr
    return ""


def _call_looks_like_logging(call: ast.Call) -> bool:
    call_name = _call_name(call.func)
    if not call_name:
        return False

    final_name = call_name.rsplit(".", 1)[-1]
    if final_name in LOGGING_FUNCTION_NAMES:
        return True

    if final_name in LOGGING_METHOD_NAMES:
        return True

    lowered_name = call_name.lower()
    return "logger" in lowered_name or "audit" in lowered_name or "log_" in lowered_name


def _exception_handler_logs_or_reraises(node: ast.ExceptHandler) -> bool:
    for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Call) and _call_looks_like_logging(child):
            return True
    return False


def _literal_string_value(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return " ".join(
            value.value for value in node.values if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return ""


def _call_is_audit_call(call: ast.Call) -> bool:
    call_name = _call_name(call.func)
    if not call_name:
        return False

    final_name = call_name.rsplit(".", 1)[-1]
    if final_name in AUDIT_FUNCTION_NAMES:
        return True

    return "audit" in call_name.lower()


def _call_is_log_action(call: ast.Call) -> bool:
    return _call_name(call.func).rsplit(".", 1)[-1] == "log_action"


def _log_action_argument(call: ast.Call, index: int, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value

    if len(call.args) > index:
        return call.args[index]

    return None


def _log_action_required_identity_fields_present(call: ast.Call) -> bool:
    for index, name in enumerate(LOG_ACTION_REQUIRED_ARGUMENTS):
        if _log_action_argument(call, index, name) is None:
            return False
    return True


def _log_action_details_payload_is_structured(call: ast.Call) -> bool:
    details_node = _log_action_argument(call, 5, "details")
    if details_node is None:
        return True

    if isinstance(details_node, ast.Constant):
        return details_node.value in (None, "")

    if isinstance(details_node, ast.Dict):
        return True

    if isinstance(details_node, ast.Call):
        return True

    if isinstance(details_node, ast.Name):
        return True

    return False


def _unstructured_log_action_allowed(relative_path: str, line_number: int) -> bool:
    return (relative_path, line_number) in BASELINED_UNSTRUCTURED_LOG_ACTION_LOCATIONS


def _call_is_direct_state_change(call: ast.Call) -> bool:
    call_name = _call_name(call.func)
    if call_name.rsplit(".", 1)[-1] != "db_execute":
        return False

    if not call.args:
        return False

    sql_text = _literal_string_value(call.args[0]).strip().lower()
    if not sql_text:
        return False

    return any(sql_text.startswith(verb) for verb in STATE_CHANGE_SQL_VERBS)


def _route_methods_from_decorator(decorator: ast.AST) -> set[str]:
    call = decorator if isinstance(decorator, ast.Call) else None
    func = call.func if call else decorator
    decorator_name = _call_name(func)
    final_name = decorator_name.rsplit(".", 1)[-1]

    if final_name in {"post", "put", "patch", "delete"}:
        return {final_name.upper()}

    if final_name != "route" or call is None:
        return set()

    for keyword in call.keywords:
        if keyword.arg != "methods":
            continue
        if isinstance(keyword.value, ast.List | ast.Tuple | ast.Set):
            methods: set[str] = set()
            for item in keyword.value.elts:
                method = _literal_string_value(item).strip().upper()
                if method:
                    methods.add(method)
            return methods

    return {"GET"}


def _function_route_methods(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    methods: set[str] = set()
    for decorator in function_node.decorator_list:
        methods.update(_route_methods_from_decorator(decorator))
    return methods


def _function_has_direct_state_change(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call) and _call_is_direct_state_change(node)
        for node in ast.walk(function_node)
    )


def _function_has_audit_call(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call) and _call_is_audit_call(node)
        for node in ast.walk(function_node)
    )


def _route_state_change_without_audit_allowed(relative_path: str, function_name: str, line_number: int) -> bool:
    return (relative_path, function_name, line_number) in BASELINED_ROUTE_STATE_CHANGE_WITHOUT_AUDIT_LOCATIONS


def _contextlib_suppress_exception_allowed(relative_path: str, line_number: int | None = None) -> bool:
    if relative_path in ALLOWED_CONTEXTLIB_SUPPRESS_EXCEPTION_FILES:
        return True

    if line_number is not None:
        if (relative_path, line_number) in BASELINED_CONTEXTLIB_SUPPRESS_EXCEPTION_LOCATIONS:
            return True

    return any(
        relative_path.startswith(prefix)
        for prefix in ALLOWED_CONTEXTLIB_SUPPRESS_EXCEPTION_PREFIXES
    )


def _bare_exception_pass_allowed(relative_path: str, line_number: int) -> bool:
    return (relative_path, line_number) in BASELINED_BARE_EXCEPTION_PASS_LOCATIONS


def _broad_exception_without_log_or_reraise_allowed(relative_path: str, line_number: int) -> bool:
    return (relative_path, line_number) in BASELINED_BROAD_EXCEPTION_WITHOUT_LOG_OR_RERAISE_LOCATIONS


def test_no_datetime_utcnow_in_production_code() -> None:
    offenders: list[str] = []

    for path in _production_python_files():
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow" in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_production_python_files_parse_and_have_no_truncation_markers() -> None:
    failures: list[str] = []

    for path in _production_python_files():
        relative_path = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8")

        if not text.strip():
            if path.name == "__init__.py" or relative_path in INTENTIONAL_EMPTY_FILES:
                continue
            failures.append(f"{relative_path}: empty file")
            continue

        for marker in TRUNCATION_MARKERS:
            if marker in text:
                failures.append(f"{relative_path}: contains truncation marker {marker!r}")

        try:
            ast.parse(text, filename=relative_path)
        except SyntaxError as exc:
            failures.append(f"{relative_path}: syntax error at line {exc.lineno}: {exc.msg}")

    assert failures == []


def test_no_ai_rewrite_placeholder_or_silent_failure_patterns_in_production_code() -> None:
    failures: list[str] = []

    for path in _production_python_files():
        relative_path = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8")
        lowered_text = text.lower()

        for marker in AI_REWRITE_PLACEHOLDER_MARKERS:
            if marker.lower() in lowered_text:
                failures.append(f"{relative_path}: contains AI rewrite placeholder marker {marker!r}")

        try:
            tree = ast.parse(text, filename=relative_path)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if node.value.value is Ellipsis:
                    failures.append(f"{relative_path}:{node.lineno}: contains ellipsis placeholder statement")

            if isinstance(node, ast.Raise):
                raised_node = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
                if _is_not_implemented_error_name(raised_node):
                    failures.append(f"{relative_path}:{node.lineno}: raises NotImplementedError in production code")

            if isinstance(node, ast.ExceptHandler) and _is_exception_name(node.type):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    if not _bare_exception_pass_allowed(relative_path, node.lineno):
                        failures.append(f"{relative_path}:{node.lineno}: contains bare except Exception: pass outside baseline")

                if not _exception_handler_logs_or_reraises(node):
                    if not _broad_exception_without_log_or_reraise_allowed(relative_path, node.lineno):
                        failures.append(
                            f"{relative_path}:{node.lineno}: broad except Exception must log or re-raise"
                        )

            if isinstance(node, ast.With):
                for item in node.items:
                    if _is_contextlib_suppress_exception_call(item.context_expr):
                        if not _contextlib_suppress_exception_allowed(relative_path, node.lineno):
                            failures.append(
                                f"{relative_path}:{node.lineno}: uses contextlib.suppress(Exception) outside baseline"
                            )

    assert failures == []


def test_log_action_calls_use_structured_audit_payloads() -> None:
    failures: list[str] = []

    for path in _production_python_files():
        relative_path = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(text, filename=relative_path)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _call_is_log_action(node):
                continue

            if _unstructured_log_action_allowed(relative_path, node.lineno):
                continue

            if not _log_action_required_identity_fields_present(node):
                failures.append(
                    f"{relative_path}:{node.lineno}: log_action must supply entity_type, entity_id, shelter, staff_user_id, and action_type"
                )
                continue

            if not _log_action_details_payload_is_structured(node):
                failures.append(
                    f"{relative_path}:{node.lineno}: log_action details must be a dict, mapping variable, call result, None, or empty string"
                )

    assert failures == []


def test_direct_mutating_route_handlers_have_audit_logging() -> None:
    failures: list[str] = []

    for path in _route_python_files():
        relative_path = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(text, filename=relative_path)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue

            methods = _function_route_methods(node)
            if not methods.intersection(MUTATING_ROUTE_METHODS):
                continue

            if not _function_has_direct_state_change(node):
                continue

            if _function_has_audit_call(node):
                continue

            if _route_state_change_without_audit_allowed(relative_path, node.name, node.lineno):
                continue

            failures.append(
                f"{relative_path}:{node.lineno}: {node.name} directly changes state without audit logging"
            )

    assert failures == []


def test_recent_redesign_modules_import_and_expose_expected_symbols() -> None:
    expected_symbols = {
        "core.intake_service": [
            "create_intake",
            "create_intake_for_existing_resident",
            "update_intake",
            "IntakeCreateResult",
            "IntakeUpdateResult",
        ],
        "core.pass_retention": [
            "run_pass_retention_cleanup_for_shelter",
        ],
        "core.report_filters": [
            "build_resident_filters",
            "resolve_date_range",
            "mask_small_counts",
        ],
        "routes.case_management_parts.family": [
            "family_intake_view",
            "edit_child_view",
            "child_services_view",
        ],
        "routes.case_management_parts.intake_income_support": [
            "load_intake_income_support",
            "upsert_intake_income_support",
            "recalculate_intake_income_support",
        ],
        "routes.resident_detail_parts.read": [
            "load_resident_for_shelter",
            "next_appointment_for_enrollment",
            "load_enrollment_context_for_shelter",
        ],
        "routes.resident_detail_parts.timeline": [
            "load_timeline",
            "build_calendar_context",
            "parse_anchor_date",
        ],
    }

    missing: list[str] = []

    for module_name, symbols in expected_symbols.items():
        module = importlib.import_module(module_name)
        for symbol in symbols:
            if not hasattr(module, symbol):
                missing.append(f"{module_name}.{symbol}")

    assert missing == []


def test_utcnow_iso_returns_utc_iso_string() -> None:
    value = utcnow_iso()

    assert isinstance(value, str)
    assert "T" in value
    assert not value.endswith("Z")
    if "+" in value:
        assert value.endswith("+00:00")
    assert value.count(":") >= 2


def test_failed_multi_table_write_rolls_back_everything(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE parent_records (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        core_db.db_execute(
            "CREATE TABLE child_records (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, note TEXT NOT NULL)"
        )

        with pytest.raises(RuntimeError, match="forced failure"), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO parent_records (id, name) VALUES (%s, %s)",
                (1, "parent written before failure"),
            )
            core_db.db_execute(
                "INSERT INTO child_records (parent_id, note) VALUES (%s, %s)",
                (1, "child written before failure"),
            )
            raise RuntimeError("forced failure")

        parent_rows = core_db.db_fetchall("SELECT id, name FROM parent_records")
        child_rows = core_db.db_fetchall("SELECT id, parent_id, note FROM child_records")

        assert parent_rows == []
        assert child_rows == []


def test_constraint_failure_rolls_back_prior_successful_writes(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, external_key TEXT NOT NULL UNIQUE, note TEXT NOT NULL)"
        )

        with pytest.raises(Exception), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO records (external_key, note) VALUES (%s, %s)",
                ("same-key", "first write should roll back"),
            )
            core_db.db_execute(
                "INSERT INTO records (external_key, note) VALUES (%s, %s)",
                ("same-key", "constraint failure"),
            )

        rows = core_db.db_fetchall("SELECT id, external_key, note FROM records")

        assert rows == []


def test_large_text_payload_is_not_truncated_on_commit(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    payload = "resident-notes-" + ("0123456789abcdef" * 4096)

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE large_payloads (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )

        with core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO large_payloads (payload) VALUES (%s)",
                (payload,),
            )

        row = core_db.db_fetchone(
            "SELECT payload, LENGTH(payload) AS payload_length FROM large_payloads WHERE id = %s",
            (1,),
        )

        assert row is not None
        assert row["payload_length"] == len(payload)
        assert row["payload"] == payload


def test_large_text_payload_rolls_back_cleanly_after_failure(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    payload = "rollback-payload-" + ("abcdef0123456789" * 4096)

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE large_payloads (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )

        with pytest.raises(RuntimeError, match="fail after large payload"), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO large_payloads (payload) VALUES (%s)",
                (payload,),
            )
            raise RuntimeError("fail after large payload")

        rows = core_db.db_fetchall("SELECT id, payload FROM large_payloads")

        assert rows == []


def test_nested_failure_rolls_back_outer_transaction(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

        with pytest.raises(RuntimeError, match="nested failure"):
            with core_db.db_transaction():
                core_db.db_execute(
                    "INSERT INTO items (name) VALUES (%s)",
                    ("outer write",),
                )
                with core_db.db_transaction():
                    core_db.db_execute(
                        "INSERT INTO items (name) VALUES (%s)",
                        ("inner write",),
                    )
                    raise RuntimeError("nested failure")

        rows = core_db.db_fetchall("SELECT id, name FROM items ORDER BY id")

        assert rows == []
