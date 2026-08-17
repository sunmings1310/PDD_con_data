package com.collector.pdd.net

import org.junit.Assert.assertEquals
import org.junit.Test

class JobRecoveryPolicyTest {
    @Test
    fun runningAssignmentIsNotFailedOnRestart() {
        assertEquals(
            RecoveryDecision.RESUME,
            recoveryDecision(localAssignment = true, serverAssignment = true, sameAttempt = true),
        )
    }

    @Test
    fun missingServerTruthWaitsInsteadOfAcquiringOverOldLease() {
        assertEquals(
            RecoveryDecision.WAIT_FOR_SERVER,
            recoveryDecision(localAssignment = true, serverAssignment = false, sameAttempt = false),
        )
    }

    @Test
    fun staleLeaseRejectsOldOutbox() {
        assertEquals(
            RecoveryDecision.REJECT_STALE,
            recoveryDecision(localAssignment = true, serverAssignment = true, sameAttempt = true, leaseRejected = true),
        )
    }

    @Test
    fun noAssignmentCanAcquire() {
        assertEquals(
            RecoveryDecision.ACQUIRE,
            recoveryDecision(localAssignment = false, serverAssignment = false, sameAttempt = false),
        )
    }

    @Test
    fun terminalRequiresConfirmedResultsAndRejectsPartialLoss() {
        assertEquals(JobTerminalAction.FAIL_NO_RESULT, jobTerminalAction(0, 0))
        assertEquals(JobTerminalAction.FAIL_REJECTED, jobTerminalAction(1, 1))
        assertEquals(JobTerminalAction.COMPLETE, jobTerminalAction(2, 0))
    }
}
