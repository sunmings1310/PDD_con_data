from __future__ import annotations

import unittest

from server.job_state import (
    ATTEMPT_TERMINAL,
    ErrorClass,
    JobStateConflict,
    JobStatus,
    RetryDecision,
    decide_retry,
    retry_delay_seconds,
    validate_attempt_transition,
    validate_job_transition,
)


class JobStateTest(unittest.TestCase):
    def test_all_documented_job_transitions(self):
        allowed = {
            "pending": {"leased", "paused", "cancelled"},
            "leased": {"running", "retry_wait", "paused", "failed", "cancelled", "dead"},
            "running": {"success", "retry_wait", "paused", "failed", "cancelled", "quarantined", "dead"},
            "paused": {"pending", "cancelled"},
            "retry_wait": {"pending", "paused", "failed", "cancelled", "dead"},
        }
        for old, targets in allowed.items():
            for new in targets:
                self.assertTrue(validate_job_transition(old, new), (old, new))
                self.assertFalse(validate_job_transition(new, new))

    def test_terminal_and_illegal_job_transitions_are_rejected(self):
        for terminal in ("success", "failed", "cancelled", "dead", "quarantined"):
            with self.assertRaises(JobStateConflict):
                validate_job_transition(terminal, "pending")
        with self.assertRaises(JobStateConflict):
            validate_job_transition("pending", "success")

    def test_attempt_lifecycle_and_terminal_protection(self):
        self.assertTrue(validate_attempt_transition("leased", "running"))
        for terminal in ATTEMPT_TERMINAL:
            self.assertTrue(validate_attempt_transition("running", terminal))
            with self.assertRaises(JobStateConflict):
                validate_attempt_transition(terminal, "running")

    def test_transient_retry_is_bounded_and_stable(self):
        first = decide_retry(ErrorClass.TRANSIENT, attempt_no=1, max_attempts=5, identity="job-1")
        again = decide_retry("transient", attempt_no=1, max_attempts=5, identity="job-1")
        self.assertEqual(first, again)
        self.assertEqual(JobStatus.RETRY_WAIT, first.target)
        self.assertTrue(first.retryable)
        self.assertGreaterEqual(first.delay_seconds or 0, 15)
        self.assertEqual(
            RetryDecision(JobStatus.FAILED, False, None, "max_attempts_exhausted"),
            decide_retry("transient", attempt_no=5, max_attempts=5, identity="job-1"),
        )

    def test_error_categories_do_not_share_infinite_retry(self):
        expected = {
            "permanent": JobStatus.FAILED,
            "business_rejection": JobStatus.FAILED,
            "data_quality": JobStatus.QUARANTINED,
            "authentication_required": JobStatus.QUARANTINED,
            "manual_intervention_required": JobStatus.DEAD,
        }
        for category, target in expected.items():
            decision = decide_retry(category, attempt_no=1, max_attempts=5, identity="job")
            self.assertEqual(target, decision.target)
            self.assertFalse(decision.retryable)
            self.assertIsNone(decision.delay_seconds)

    def test_backoff_is_capped(self):
        self.assertLessEqual(retry_delay_seconds(99, "job"), 900)


if __name__ == "__main__":
    unittest.main()
