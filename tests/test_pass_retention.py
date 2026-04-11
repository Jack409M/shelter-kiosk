from __future__ import annotations


def test_run_pass_retention_cleanup_for_blank_shelter():
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    result = run_pass_retention_cleanup_for_shelter("")

    assert result == {
        "shelter": "",
        "backfilled": 0,
        "deleted": 0,
    }


def test_run_pass_retention_cleanup_returns_counts(monkeypatch):
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    monkeypatch.setattr(
        "core.pass_retention.backfill_missing_delete_after_at_for_shelter",
        lambda shelter: 3,
    )
    monkeypatch.setattr(
        "core.pass_retention.delete_expired_passes_for_shelter",
        lambda shelter: 2,
    )

    result = run_pass_retention_cleanup_for_shelter("abba")

    assert result == {
        "shelter": "abba",
        "backfilled": 3,
        "deleted": 2,
    }


def test_run_pass_retention_cleanup_normalizes_shelter(monkeypatch):
    from core.pass_retention import run_pass_retention_cleanup_for_shelter

    seen: list[tuple[str, str]] = []

    def fake_backfill(shelter: str) -> int:
        seen.append(("backfill", shelter))
        return 1

    def fake_delete(shelter: str) -> int:
        seen.append(("delete", shelter))
        return 4

    monkeypatch.setattr(
        "core.pass_retention.backfill_missing_delete_after_at_for_shelter",
        fake_backfill,
    )
    monkeypatch.setattr(
        "core.pass_retention.delete_expired_passes_for_shelter",
        fake_delete,
    )

    result = run_pass_retention_cleanup_for_shelter("  haven  ")

    assert seen == [
        ("backfill", "haven"),
        ("delete", "haven"),
    ]
    assert result == {
        "shelter": "haven",
        "backfilled": 1,
        "deleted": 4,
    }
