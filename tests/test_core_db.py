from __future__ import annotations

import pytest

from core import db as core_db


def test_is_sqlite_url_true_and_false() -> None:
    assert core_db._is_sqlite_url("sqlite:///:memory:") is True
    assert core_db._is_sqlite_url("postgresql://user:pass@localhost/dbname") is False


def test_normalize_sql_for_sqlite() -> None:
    sql = "SELECT NOW(), BTRIM(name) FROM users WHERE id = %s"
    normalized = core_db._normalize_sql(sql, db_kind="sqlite")
    assert normalized == "SELECT CURRENT_TIMESTAMP, TRIM(name) FROM users WHERE id = ?"


def test_normalize_sql_for_pg() -> None:
    sql = "SELECT * FROM users WHERE id = ?"
    normalized = core_db._normalize_sql(sql, db_kind="pg")
    assert normalized == "SELECT * FROM users WHERE id = %s"


def test_sqlite_should_skip_statement_true() -> None:
    sql = "SELECT pg_get_serial_sequence('transport_requests', 'id')"
    assert core_db._sqlite_should_skip_statement(sql) is True


def test_rewrite_legacy_sqlite_transport_insert_rewrites_exact_match() -> None:
    sql = "INSERT INTO transport_requests (resident_identifier, shelter, status) VALUES (?, ?, ?)"
    params = ("RID123", "Haven", "pending")

    rewritten_sql, rewritten_params = core_db._rewrite_legacy_sqlite_transport_insert(sql, params)

    assert "first_name" in rewritten_sql
    assert rewritten_params[0:3] == ("RID123", "Haven", "pending")
    assert len(rewritten_params) == 9


def test_row_to_dict_none_returns_empty_dict() -> None:
    assert core_db._row_to_dict(None) == {}


def test_row_to_dict_invalid_row_raises() -> None:
    with pytest.raises(RuntimeError, match="could not be converted to dict"):
        core_db._row_to_dict(object())
