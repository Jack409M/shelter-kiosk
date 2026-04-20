from routes.case_management_parts import promotion_review_validation


def test_promotion_review_validation_module_exists():
    assert hasattr(promotion_review_validation, "validate")
