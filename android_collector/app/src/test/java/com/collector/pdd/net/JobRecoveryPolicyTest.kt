package com.collector.pdd.net

import com.collector.pdd.data.OutboxEntity
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.CollectTarget
import org.junit.Assert.assertEquals
import org.json.JSONArray
import org.json.JSONObject
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

    @Test
    fun resumedAttemptUsesConfirmedReceiptsFromEarlierAttemptOfSameJob() {
        val oldReceipt = OutboxEntity(
            outboxId = "receipt-old-attempt",
            eventType = "product",
            remoteTaskId = 1122,
            payloadJson = JSONObject().put("keyword", "牙膏").put("pick_tag", "slot-1").toString(),
            state = "acked",
            jobId = 320,
            attemptId = 328,
        )
        val unrelated = oldReceipt.copy(
            outboxId = "receipt-unrelated",
            payloadJson = JSONObject().put("keyword", "牙膏").put("pick_tag", "slot-2").toString(),
        )
        val checkpoint = JSONObject().put("confirmed_slots", JSONArray().put("牙膏|slot-1"))

        assertEquals(
            listOf("receipt-old-attempt"),
            confirmedJobProducts(checkpoint, listOf(oldReceipt, unrelated)).map { it.outboxId },
        )
    }

    @Test
    fun recoveredJobRetriesEngineAfterAccessibilityBecomesAvailable() {
        assertEquals(true, shouldRetryRecoveredEngine(false, false, 20_000, 0))
        assertEquals(false, shouldRetryRecoveredEngine(true, false, 20_000, 0))
        assertEquals(false, shouldRetryRecoveredEngine(false, true, 20_000, 0))
        assertEquals(false, shouldRetryRecoveredEngine(false, false, 20_000, 10_000))
    }

    @Test
    fun fullyConfirmedOrdinaryCollectionCompletesWithoutReopeningPlatform() {
        val config = CollectConfig(
            keywords = listOf("牙膏"),
            maxDetailPerKeyword = 2,
            confirmedSlots = setOf("牙膏|default_top_1", "牙膏|default_top_2"),
        )
        assertEquals(true, checkpointCoversCollectWork(config))
        assertEquals(false, checkpointCoversCollectWork(config.copy(confirmedSlots = setOf("牙膏|default_top_1"))))
        assertEquals(
            false,
            checkpointCoversCollectWork(
                config.copy(
                    targets = listOf(
                        CollectTarget(keyword = "牙膏", targetApproval = "国药准字", targetSpec = "100g"),
                    ),
                ),
            ),
        )
    }
}
