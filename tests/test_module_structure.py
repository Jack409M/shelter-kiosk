from pathlib import Path


ROUTES_DIR = Path("routes/case_management_parts")
TESTS_DIR = Path("tests")


def test_every_module_has_validation_and_test():
    route_files = [
        f for f in ROUTES_DIR.glob("*.py")
        if not f.name.endswith("_validation.py")
        and f.name != "__init__.py"
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
        f"Missing validation files for modules: {missing_validation}"
    )

    assert not missing_tests, (
        f"Missing validation tests for modules: {missing_tests}"
    )
