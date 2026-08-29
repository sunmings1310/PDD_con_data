package com.collector.pdd.net

import com.collector.pdd.data.OutboxEntity
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CandidateObservationTerminalGateTest {
    private fun event(state: String) = OutboxEntity(
        outboxId="candidate-1", eventType="candidate_observation", remoteTaskId=1,
        payloadJson="{}", state=state,
    )

    @Test fun terminalRequiresPersistedAckAndRejectIsNotSuccess() {
        assertTrue(candidateEvidenceAcknowledged(emptyList()))
        assertTrue(candidateEvidenceAcknowledged(listOf(event("acked"))))
        for (state in listOf("pending", "retry", "in_flight", "rejected")) {
            assertFalse(state, candidateEvidenceAcknowledged(listOf(event(state))))
        }
    }
}
