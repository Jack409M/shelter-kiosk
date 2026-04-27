from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_COUNT = 3
DEFAULT_MIN_FILE_SIZE_BYTES = 2
JSONValue = Mapping[str, Any] | list[Any]
Validator = Callable[[Any], None]


class FileSafetyError(RuntimeError):
    """Base error for protected file read and write failures."""


class FileIntegrityError(FileSafetyError):
    """Raised when file content fails integrity validation."""


class FileRecoveryError(FileSafetyError):
    """Raised when the primary file and all backups are unusable."""


def _as_path(file_path: str | os.PathLike[str]) -> Path:
    return Path(file_path)


def _checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_parent_dir(file_path: Path) -> None:
    parent = file_path.parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return

    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        logger.debug("Could not open directory for fsync: %s", directory, exc_info=True)
        return

    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _backup_path(file_path: Path, number: int) -> Path:
    return file_path.with_name(f"{file_path.name}.bak{number}")


def _rotate_backups(file_path: Path, backup_count: int) -> None:
    if backup_count <= 0:
        return

    oldest_backup = _backup_path(file_path, backup_count)
    if oldest_backup.exists():
        oldest_backup.unlink()

    for number in range(backup_count - 1, 0, -1):
        source = _backup_path(file_path, number)
        destination = _backup_path(file_path, number + 1)
        if source.exists():
            os.replace(source, destination)

    if file_path.exists():
        os.replace(file_path, _backup_path(file_path, 1))


def _validate_raw_bytes(
    raw: bytes,
    *,
    path: Path,
    min_file_size_bytes: int,
) -> None:
    if len(raw) < min_file_size_bytes:
        raise FileIntegrityError(
            f"File is too small and may be truncated: {path} size={len(raw)} "
            f"minimum={min_file_size_bytes}"
        )


def _decode_json(raw: bytes, *, path: Path) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise FileIntegrityError(f"Invalid JSON content in {path}: {exc}") from exc


def _validate_json_payload(payload: Any, validator: Validator | None) -> None:
    if validator is not None:
        validator(payload)


def safe_write_bytes(
    file_path: str | os.PathLike[str],
    raw: bytes,
    *,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
) -> None:
    """
    Atomically write bytes to disk with backup rotation and post write verification.

    Use this for any durable generated file where truncation would matter. The destination is
    only replaced after the temporary file has been flushed, fsynced, size checked, and checksum
    verified.
    """

    destination = _as_path(file_path)
    _ensure_parent_dir(destination)

    _validate_raw_bytes(raw, path=destination, min_file_size_bytes=min_file_size_bytes)
    expected_checksum = _checksum_bytes(raw)

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_file.write(raw)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = Path(temp_file.name)

        written = temp_path.read_bytes()
        _validate_raw_bytes(written, path=temp_path, min_file_size_bytes=min_file_size_bytes)
        actual_checksum = _checksum_bytes(written)
        if actual_checksum != expected_checksum:
            raise FileIntegrityError(
                f"Temporary file checksum mismatch for {destination}: "
                f"expected={expected_checksum} actual={actual_checksum}"
            )

        _rotate_backups(destination, backup_count)
        os.replace(temp_path, destination)
        temp_path = None
        _fsync_directory(destination.parent)

        final = destination.read_bytes()
        _validate_raw_bytes(final, path=destination, min_file_size_bytes=min_file_size_bytes)
        final_checksum = _checksum_bytes(final)
        if final_checksum != expected_checksum:
            raise FileIntegrityError(
                f"Post write checksum mismatch for {destination}: "
                f"expected={expected_checksum} actual={final_checksum}"
            )

        logger.info(
            "Protected file write completed path=%s size=%s checksum=%s",
            destination,
            len(final),
            final_checksum,
        )
    except Exception:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.warning("Could not remove abandoned temp file: %s", temp_path, exc_info=True)
        raise


def safe_read_bytes(
    file_path: str | os.PathLike[str],
    *,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
) -> bytes:
    """Read bytes defensively and fall back to rolling backups when needed."""

    path = _as_path(file_path)
    candidates = [path]
    candidates.extend(_backup_path(path, number) for number in range(1, backup_count + 1))

    failures: list[str] = []

    for candidate in candidates:
        if not candidate.exists():
            failures.append(f"{candidate}: missing")
            continue

        try:
            raw = candidate.read_bytes()
            _validate_raw_bytes(raw, path=candidate, min_file_size_bytes=min_file_size_bytes)
            return raw
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
            logger.warning("Rejected file candidate: %s", candidate, exc_info=True)

    raise FileRecoveryError(
        f"No valid file version found for {path}. Failures: {'; '.join(failures)}"
    )


def safe_write_text(
    file_path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
) -> None:
    """Atomically write text to disk using the same protected byte write path."""

    safe_write_bytes(
        file_path,
        text.encode(encoding),
        backup_count=backup_count,
        min_file_size_bytes=min_file_size_bytes,
    )


def safe_read_text(
    file_path: str | os.PathLike[str],
    *,
    encoding: str = "utf-8",
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
) -> str:
    """Read text defensively and fall back to rolling backups when needed."""

    return safe_read_bytes(
        file_path,
        backup_count=backup_count,
        min_file_size_bytes=min_file_size_bytes,
    ).decode(encoding)


def safe_write_json(
    file_path: str | os.PathLike[str],
    data: JSONValue,
    *,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
    validator: Validator | None = None,
) -> None:
    """
    Atomically write JSON to disk with validation, backup rotation, and post write verification.

    The write path is intentionally defensive:
    1. Serialize data before touching the destination file.
    2. Validate the serialized payload.
    3. Write to a temporary file in the same directory.
    4. Flush and fsync the temporary file.
    5. Verify size and checksum before promotion.
    6. Rotate backups.
    7. Replace the destination with os.replace.
    8. Verify the final file after promotion.
    """

    _validate_json_payload(data, validator)
    raw = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
    safe_write_bytes(
        file_path,
        raw,
        backup_count=backup_count,
        min_file_size_bytes=min_file_size_bytes,
    )


def safe_read_json(
    file_path: str | os.PathLike[str],
    *,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    min_file_size_bytes: int = DEFAULT_MIN_FILE_SIZE_BYTES,
    validator: Validator | None = None,
) -> Any:
    """
    Read JSON defensively and fall back to rolling backups when the primary file is unusable.
    """

    path = _as_path(file_path)
    candidates = [path]
    candidates.extend(_backup_path(path, number) for number in range(1, backup_count + 1))

    failures: list[str] = []

    for candidate in candidates:
        if not candidate.exists():
            failures.append(f"{candidate}: missing")
            continue

        try:
            return _read_json_candidate(
                candidate,
                min_file_size_bytes=min_file_size_bytes,
                validator=validator,
            )
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
            logger.warning("Rejected JSON file candidate: %s", candidate, exc_info=True)

    raise FileRecoveryError(
        f"No valid JSON version found for {path}. Failures: {'; '.join(failures)}"
    )


def _read_json_candidate(
    file_path: Path,
    *,
    min_file_size_bytes: int,
    validator: Validator | None,
) -> Any:
    raw = file_path.read_bytes()
    _validate_raw_bytes(raw, path=file_path, min_file_size_bytes=min_file_size_bytes)
    payload = _decode_json(raw, path=file_path)
    _validate_json_payload(payload, validator)
    return payload
