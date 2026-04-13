from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    code: str
    message: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IntegrityCheckResult:
    ok: bool
    issues: list[IntegrityIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


def check_resident_integrity(resident_id: int) -> IntegrityCheckResult:
    del resident_id
    return IntegrityCheckResult(ok=True, issues=[])


def ensure_resident_integrity(resident_id: int) -> None:
    del resident_id
    return None


def repair_missing_family_snapshot_for_enrollment(enrollment_id: int) -> bool:
    del enrollment_id
    return False


def repair_resident_integrity(resident_id: int) -> IntegrityCheckResult:
    del resident_id
    return IntegrityCheckResult(ok=True, issues=[])
