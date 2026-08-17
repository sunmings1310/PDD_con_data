"""Phase 2 authoritative Job/Attempt state and retry contract.

Pure Python by design: Oracle and FastAPI adapters must call these helpers rather
than reimplementing transitions or retry classification.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib


class JobStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD = "dead"
    QUARANTINED = "quarantined"


class AttemptStatus(str, Enum):
    LEASED = "leased"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    RECLAIMED = "reclaimed"


class ErrorClass(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    BUSINESS_REJECTION = "business_rejection"
    DATA_QUALITY = "data_quality"
    AUTHENTICATION_REQUIRED = "authentication_required"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


JOB_TERMINAL = frozenset(
    {JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD, JobStatus.QUARANTINED}
)
ATTEMPT_TERMINAL = frozenset(
    {
        AttemptStatus.SUCCESS,
        AttemptStatus.FAILED,
        AttemptStatus.TIMEOUT,
        AttemptStatus.CANCELLED,
        AttemptStatus.RECLAIMED,
    }
)
JOB_TRANSITIONS = {
    JobStatus.PENDING: frozenset({JobStatus.LEASED, JobStatus.PAUSED, JobStatus.CANCELLED}),
    JobStatus.LEASED: frozenset(
        {JobStatus.RUNNING, JobStatus.RETRY_WAIT, JobStatus.PAUSED, JobStatus.FAILED,
         JobStatus.CANCELLED, JobStatus.DEAD}
    ),
    JobStatus.RUNNING: frozenset(
        {JobStatus.SUCCESS, JobStatus.RETRY_WAIT, JobStatus.PAUSED, JobStatus.FAILED,
         JobStatus.CANCELLED, JobStatus.QUARANTINED, JobStatus.DEAD}
    ),
    JobStatus.PAUSED: frozenset({JobStatus.PENDING, JobStatus.CANCELLED}),
    JobStatus.RETRY_WAIT: frozenset(
        {JobStatus.PENDING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD}
    ),
}
ATTEMPT_TRANSITIONS = {
    AttemptStatus.LEASED: frozenset(
        {AttemptStatus.RUNNING, AttemptStatus.FAILED, AttemptStatus.TIMEOUT,
         AttemptStatus.CANCELLED, AttemptStatus.RECLAIMED}
    ),
    AttemptStatus.RUNNING: ATTEMPT_TERMINAL,
}


@dataclass(frozen=True)
class JobStateConflict(ValueError):
    code: str
    current: str
    requested: str

    def __str__(self) -> str:
        return f"{self.code}: {self.current} -> {self.requested}"


@dataclass(frozen=True)
class RetryDecision:
    target: JobStatus
    retryable: bool
    delay_seconds: int | None
    reason: str


def job_status(value: str | JobStatus) -> JobStatus:
    return value if isinstance(value, JobStatus) else JobStatus(str(value).lower())


def attempt_status(value: str | AttemptStatus) -> AttemptStatus:
    return value if isinstance(value, AttemptStatus) else AttemptStatus(str(value).lower())


def validate_job_transition(current: str | JobStatus, requested: str | JobStatus) -> bool:
    old, new = job_status(current), job_status(requested)
    if old == new:
        return False
    if old in JOB_TERMINAL or new not in JOB_TRANSITIONS.get(old, frozenset()):
        raise JobStateConflict("JOB_STATE_CONFLICT", old.value, new.value)
    return True


def validate_attempt_transition(current: str | AttemptStatus, requested: str | AttemptStatus) -> bool:
    old, new = attempt_status(current), attempt_status(requested)
    if old == new:
        return False
    if old in ATTEMPT_TERMINAL or new not in ATTEMPT_TRANSITIONS.get(old, frozenset()):
        raise JobStateConflict("ATTEMPT_STATE_CONFLICT", old.value, new.value)
    return True


def retry_delay_seconds(attempt_no: int, identity: str, *, base: int = 15, cap: int = 900) -> int:
    """Exponential backoff with stable 0..base-1 second jitter."""
    ordinal = max(1, int(attempt_no))
    exponential = min(cap, base * (2 ** (ordinal - 1)))
    digest = hashlib.sha256(f"{identity}:{ordinal}".encode()).digest()
    jitter = int.from_bytes(digest[:2], "big") % max(1, base)
    return min(cap, exponential + jitter)


def decide_retry(
    error_class: str | ErrorClass,
    *,
    attempt_no: int,
    max_attempts: int,
    identity: str,
) -> RetryDecision:
    category = error_class if isinstance(error_class, ErrorClass) else ErrorClass(str(error_class).lower())
    exhausted = int(attempt_no) >= max(1, int(max_attempts))
    if category == ErrorClass.TRANSIENT:
        if exhausted:
            return RetryDecision(JobStatus.FAILED, False, None, "max_attempts_exhausted")
        return RetryDecision(
            JobStatus.RETRY_WAIT,
            True,
            retry_delay_seconds(attempt_no, identity),
            "transient_backoff",
        )
    if category in {ErrorClass.DATA_QUALITY, ErrorClass.AUTHENTICATION_REQUIRED}:
        return RetryDecision(JobStatus.QUARANTINED, False, None, category.value)
    if category == ErrorClass.MANUAL_INTERVENTION_REQUIRED:
        return RetryDecision(JobStatus.DEAD, False, None, category.value)
    return RetryDecision(JobStatus.FAILED, False, None, category.value)
