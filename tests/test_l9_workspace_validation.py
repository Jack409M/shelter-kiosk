from routes.case_management_parts import l9_workspace_validation


def test_l9_workspace_validation_module_exists():
    assert hasattr(l9_workspace_validation, "validate")
