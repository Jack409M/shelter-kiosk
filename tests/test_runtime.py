from __future__ import annotations

from core import runtime


def test_env_flag_returns_default_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("TEST_FLAG", raising=False)
    assert runtime.env_flag("TEST_FLAG") is False
    assert runtime.env_flag("TEST_FLAG", default=True) is True


def test_env_flag_recognizes_truthy_values(monkeypatch) -> None:
    for value in ["1", "true", "TRUE", "Yes", " on "]:
        monkeypatch.setenv("TEST_FLAG", value)
        assert runtime.env_flag("TEST_FLAG") is True


def test_env_flag_rejects_non_truthy_values(monkeypatch) -> None:
    for value in ["0", "false", "off", "no", "random"]:
        monkeypatch.setenv("TEST_FLAG", value)
        assert runtime.env_flag("TEST_FLAG") is False
