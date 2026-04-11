from __future__ import annotations

from db.schema_helpers import _is_duplicate_column_error


def test_duplicate_column_error_detection_for_duplicate_column() -> None:
    assert _is_duplicate_column_error(Exception("duplicate column name: first_name")) is True


def test_duplicate_column_error_detection_for_already_exists() -> None:
    assert _is_duplicate_column_error(Exception('column "first_name" already exists')) is True


def test_duplicate_column_error_detection_for_real_failure() -> None:
    assert _is_duplicate_column_error(Exception("syntax error at or near ADD")) is False
