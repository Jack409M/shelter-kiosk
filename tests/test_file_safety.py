from __future__ import annotations

from pathlib import Path

import pytest

from core.file_safety import FileIntegrityError, FileRecoveryError, safe_read_json, safe_write_json


def test_safe_write_and_read_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    payload = {"value": 1}

    safe_write_json(path, payload)
    result = safe_read_json(path)

    assert result == payload


def test_truncated_file_falls_back_to_backup(tmp_path: Path) -> None:
    path = tmp_path / "data.json"

    safe_write_json(path, {"value": 1})
    safe_write_json(path, {"value": 2})

    # Corrupt the active file by truncating it
    path.write_bytes(b"{")

    result = safe_read_json(path)

    assert result == {"value": 1}


def test_empty_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.json"

    path.write_bytes(b"")

    with pytest.raises(FileRecoveryError):
        safe_read_json(path)


def test_invalid_json_rejected(tmp_path: Path) -> None:
    path = tmp_path / "data.json"

    path.write_bytes(b"not json")

    with pytest.raises(FileRecoveryError):
        safe_read_json(path)


def test_backup_chain_used_when_multiple_failures(tmp_path: Path) -> None:
    path = tmp_path / "data.json"

    safe_write_json(path, {"value": 1})
    safe_write_json(path, {"value": 2})
    safe_write_json(path, {"value": 3})

    # Corrupt primary and first backup
    path.write_bytes(b"{")
    (tmp_path / "data.json.bak1").write_bytes(b"{")

    result = safe_read_json(path)

    assert result == {"value": 1}


def test_write_rejects_too_small_payload(tmp_path: Path) -> None:
    path = tmp_path / "data.json"

    with pytest.raises(FileIntegrityError):
        safe_write_json(path, {}, min_file_size_bytes=50)
