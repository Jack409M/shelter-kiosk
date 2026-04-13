from __future__ import annotations

from datetime import datetime


def test_has_active_pass_block_returns_false_when_no_restrictions(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "_load_active_writeup_restrictions",
        lambda resident_id: [],
    )

    has_block, restrictions = pp.has_active_pass_block(1)

    assert has_block is False
    assert restrictions == []


def test_has_active_pass_block_returns_true_when_restrictions_exist(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "_load_active_writeup_restrictions",
        lambda resident_id: [
            {
                "restriction_label": "Program Probation",
                "restriction_detail": "2026-04-01 to 2026-04-30",
            }
        ],
    )

    has_block, restrictions = pp.has_active_pass_block(1)

    assert has_block is True
    assert len(restrictions) == 1
    assert restrictions[0]["restriction_label"] == "Program Probation"


def test_build_policy_check_marks_deadline_pass_and_same_day_pass(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "load_resident_pass_profile",
        lambda resident_id: {
            "id": resident_id,
            "program_level": "Level 3",
            "shelter": "abba",
        },
    )
    monkeypatch.setattr(pp, "load_pass_settings_for_shelter", lambda shelter: {"pass_deadline_weekday": 0})
    monkeypatch.setattr(
        pp,
        "pass_required_hours",
        lambda shelter: {
            "productive_required_hours": 35,
            "work_required_hours": 29,
        },
    )
    monkeypatch.setattr(pp, "use_gh_pass_form", lambda shelter, level: False)
    monkeypatch.setattr(pp, "shared_pass_rule_box", lambda shelter, level: {"lines": ["Rule A"]})
    monkeypatch.setattr(pp, "gh_pass_rule_box", lambda shelter, level: {"lines": ["GH Rule"]})
    monkeypatch.setattr(pp, "pass_type_label", lambda key: "Pass")
    monkeypatch.setattr(pp, "has_active_pass_block", lambda resident_id: (False, []))

    start_local = datetime(2026, 4, 15, 9, 0, 0)
    end_local = datetime(2026, 4, 15, 17, 0, 0)
    created_local = datetime(2026, 4, 14, 8, 0, 0)
    deadline_local = datetime(2026, 4, 14, 10, 0, 0)

    monkeypatch.setattr(
        pp,
        "standard_pass_deadline_for_leave",
        lambda start_local, shelter: deadline_local,
    )

    result = pp.build_policy_check(
        pass_row={
            "resident_id": 1,
            "shelter": "abba",
            "pass_type": "pass",
            "start_at_local": start_local,
            "end_at_local": end_local,
            "created_at_local": created_local,
        },
        pass_detail={},
        hour_summary=None,
        meeting_summary=None,
    )

    checks = result["checks"]

    assert result["title"] == "Pass Policy Check"
    assert result["pass_type_label"] == "Pass"
    assert any(
        check["label"] == "Deadline" and check["status_class"] == "pass"
        for check in checks
    )
    assert any(
        check["label"] == "Pass timing" and check["status_class"] == "pass"
        for check in checks
    )


def test_build_policy_check_marks_late_deadline_and_bad_same_day_timing(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "load_resident_pass_profile",
        lambda resident_id: {
            "id": resident_id,
            "program_level": "Level 3",
            "shelter": "abba",
        },
    )
    monkeypatch.setattr(pp, "load_pass_settings_for_shelter", lambda shelter: {"pass_deadline_weekday": 0})
    monkeypatch.setattr(
        pp,
        "pass_required_hours",
        lambda shelter: {
            "productive_required_hours": 35,
            "work_required_hours": 29,
        },
    )
    monkeypatch.setattr(pp, "use_gh_pass_form", lambda shelter, level: False)
    monkeypatch.setattr(pp, "shared_pass_rule_box", lambda shelter, level: {"lines": ["Rule A"]})
    monkeypatch.setattr(pp, "gh_pass_rule_box", lambda shelter, level: {"lines": ["GH Rule"]})
    monkeypatch.setattr(pp, "pass_type_label", lambda key: "Pass")
    monkeypatch.setattr(pp, "has_active_pass_block", lambda resident_id: (False, []))

    start_local = datetime(2026, 4, 15, 9, 0, 0)
    end_local = datetime(2026, 4, 16, 9, 0, 0)
    created_local = datetime(2026, 4, 14, 12, 0, 0)
    deadline_local = datetime(2026, 4, 14, 10, 0, 0)

    monkeypatch.setattr(
        pp,
        "standard_pass_deadline_for_leave",
        lambda start_local, shelter: deadline_local,
    )

    result = pp.build_policy_check(
        pass_row={
            "resident_id": 1,
            "shelter": "abba",
            "pass_type": "pass",
            "start_at_local": start_local,
            "end_at_local": end_local,
            "created_at_local": created_local,
        },
        pass_detail={},
        hour_summary=None,
        meeting_summary=None,
    )

    checks = result["checks"]

    assert any(
        check["label"] == "Deadline" and check["status_class"] == "fail"
        for check in checks
    )
    assert any(
        check["label"] == "Pass timing" and check["status_class"] == "fail"
        for check in checks
    )


def test_build_policy_check_fails_when_previous_week_hours_are_below_required(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "load_resident_pass_profile",
        lambda resident_id: {
            "id": resident_id,
            "program_level": "Level 3",
            "shelter": "abba",
        },
    )
    monkeypatch.setattr(pp, "load_pass_settings_for_shelter", lambda shelter: {"pass_deadline_weekday": 0})
    monkeypatch.setattr(
        pp,
        "pass_required_hours",
        lambda shelter: {
            "productive_required_hours": 35,
            "work_required_hours": 29,
        },
    )
    monkeypatch.setattr(pp, "use_gh_pass_form", lambda shelter, level: False)
    monkeypatch.setattr(pp, "shared_pass_rule_box", lambda shelter, level: {"lines": ["Rule A"]})
    monkeypatch.setattr(pp, "gh_pass_rule_box", lambda shelter, level: {"lines": ["GH Rule"]})
    monkeypatch.setattr(pp, "pass_type_label", lambda key: "Pass")
    monkeypatch.setattr(pp, "has_active_pass_block", lambda resident_id: (False, []))
    monkeypatch.setattr(
        pp,
        "standard_pass_deadline_for_leave",
        lambda start_local, shelter: datetime(2026, 4, 14, 10, 0, 0),
    )

    result = pp.build_policy_check(
        pass_row={
            "resident_id": 1,
            "shelter": "abba",
            "pass_type": "pass",
            "start_at_local": datetime(2026, 4, 15, 9, 0, 0),
            "end_at_local": datetime(2026, 4, 15, 17, 0, 0),
            "created_at_local": datetime(2026, 4, 14, 9, 0, 0),
        },
        pass_detail={},
        hour_summary={
            "productive_hours": 20,
            "work_hours": 10,
        },
        meeting_summary=None,
    )

    checks = result["checks"]

    assert any(
        check["label"] == "Previous week hours" and check["status_class"] == "fail"
        for check in checks
    )


def test_build_policy_check_includes_disciplinary_block(monkeypatch):
    import routes.attendance_parts.pass_policy as pp

    monkeypatch.setattr(
        pp,
        "load_resident_pass_profile",
        lambda resident_id: {
            "id": resident_id,
            "program_level": "Level 3",
            "shelter": "abba",
        },
    )
    monkeypatch.setattr(pp, "load_pass_settings_for_shelter", lambda shelter: {"pass_deadline_weekday": 0})
    monkeypatch.setattr(
        pp,
        "pass_required_hours",
        lambda shelter: {
            "productive_required_hours": 35,
            "work_required_hours": 29,
        },
    )
    monkeypatch.setattr(pp, "use_gh_pass_form", lambda shelter, level: False)
    monkeypatch.setattr(pp, "shared_pass_rule_box", lambda shelter, level: {"lines": ["Rule A"]})
    monkeypatch.setattr(pp, "gh_pass_rule_box", lambda shelter, level: {"lines": ["GH Rule"]})
    monkeypatch.setattr(pp, "pass_type_label", lambda key: "Pass")
    monkeypatch.setattr(
        pp,
        "has_active_pass_block",
        lambda resident_id: (
            True,
            [
                {
                    "restriction_label": "Program Probation",
                    "restriction_detail": "2026-04-01 to 2026-04-30",
                    "summary": "Open restriction",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        pp,
        "standard_pass_deadline_for_leave",
        lambda start_local, shelter: datetime(2026, 4, 14, 10, 0, 0),
    )

    result = pp.build_policy_check(
        pass_row={
            "resident_id": 1,
            "shelter": "abba",
            "pass_type": "pass",
            "start_at_local": datetime(2026, 4, 15, 9, 0, 0),
            "end_at_local": datetime(2026, 4, 15, 17, 0, 0),
            "created_at_local": datetime(2026, 4, 14, 9, 0, 0),
        },
        pass_detail={},
        hour_summary=None,
        meeting_summary=None,
    )

    assert result["has_disciplinary_block"] is True
    assert any(
        check["label"] == "Program Probation" and check["status_class"] == "fail"
        for check in result["checks"]
    )
