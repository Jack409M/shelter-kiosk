from pathlib import Path


ROUTES_DIR = Path("routes/case_management_parts")
TESTS_DIR = Path("tests")

SKIP_EXACT = {
    "__init__.py",
}

SKIP_SUFFIXES = (
    "_validation.py",
    "_helpers.py",
    "_helper.py",
    "_loaders.py",
    "_loader.py",
    "_mappers.py",
    "_mapper.py",
    "_builders.py",
    "_builder.py",
    "_formatters.py",
    "_formatter.py",
    "_metrics.py",
    "_metric.py",
    "_utils.py",
    "_util.py",
    "_scope.py",
    "_viewmodel.py",
    "_inserts.py",
    "_recorders.py",
    "_drafts.py",
)


def _is_form_handling_module(route_file: Path) -> bool:
    text = route_file.read_text(encoding="utf-8")

    return any(
        marker in text
        for marker in (
            "request.form",
            "request.method == \"POST\"",
            "request.method == 'POST'",
            "methods=[\"GET\", \"POST\"]",
            "methods=['GET', 'POST']",
            ".post(",
        )
    )


def test_every_form_module_has_validation_and_test():
    route_files = [
        f for f in ROUTES_DIR.glob("*.py")
        if f.name not in SKIP_EXACT
        and not f.name.endswith(SKIP_SUFFIXES)
        and _is_form_handling_module(f)
    ]

    missing_validation = []
    missing_tests = []

    for route_file in route_files:
        module_name = route_file.stem

        validation_file = ROUTES_DIR / f"{module_name}_validation.py"
        test_file = TESTS_DIR / f"test_{module_name}_validation.py"

        if not validation_file.exists():
            missing_validation.append(module_name)

        if not test_file.exists():
            missing_tests.append(module_name)

    assert not missing_validation, (
        f"Missing validation files for form modules: {missing_validation}"
    )

    assert not missing_tests, (
        f"Missing validation tests for form modules: {missing_tests}"
    )
