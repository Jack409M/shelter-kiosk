from __future__ import annotations


def test_scheduler_starts_once(monkeypatch, app):
    import core.pass_retention_scheduler as scheduler_module

    started = []

    class FakeThread:
        def __init__(self, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(scheduler_module.threading, "Thread", FakeThread)

    app.config["TESTING"] = False

    scheduler_module.start_pass_retention_scheduler(app)
    scheduler_module.start_pass_retention_scheduler(app)

    assert started == ["pass-retention-scheduler"]
    assert app.extensions.get("pass_retention_scheduler_started") is True


def test_scheduler_skips_in_testing(app):
    from core.pass_retention_scheduler import start_pass_retention_scheduler

    app.config["TESTING"] = True

    start_pass_retention_scheduler(app)

    assert app.extensions.get("pass_retention_scheduler_started") is None


def test_cleanup_cycle_runs_all_shelters(monkeypatch, app):
    from core.pass_retention_scheduler import _run_cleanup_cycle

    calls: list[str] = []

    def fake_cleanup(shelter: str) -> None:
        calls.append(shelter)

    monkeypatch.setattr(
        "core.pass_retention_scheduler.run_pass_retention_cleanup_for_shelter",
        fake_cleanup,
    )

    _run_cleanup_cycle(app)

    assert calls == ["abba", "haven", "gratitude"]


def test_cleanup_cycle_handles_per_shelter_failure(monkeypatch, app):
    from core.pass_retention_scheduler import _run_cleanup_cycle

    calls: list[str] = []

    def fake_cleanup(shelter: str) -> None:
        calls.append(shelter)
        if shelter == "haven":
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "core.pass_retention_scheduler.run_pass_retention_cleanup_for_shelter",
        fake_cleanup,
    )

    _run_cleanup_cycle(app)

    assert calls == ["abba", "haven", "gratitude"]
