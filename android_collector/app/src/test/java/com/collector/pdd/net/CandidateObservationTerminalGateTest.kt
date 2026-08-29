package com.collector.pdd.net

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.collector.pdd.data.AppDatabase
import com.collector.pdd.data.OutboxEntity
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
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

    @Test fun realRoomOutboxBlocksTerminalUntilCandidateAckIncludingTruncationAck() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(), AppDatabase::class.java,
        ).allowMainThreadQueries().build()
        try {
            val dao = db.outboxDao()
            val candidate = event("pending").copy(jobId=12, attemptId=13, createdAt=2)
            val terminal = OutboxEntity(
                outboxId="fail-1", eventType="job_fail", remoteTaskId=1,
                payloadJson="{\"local_status\":\"not_matched\"}", state="pending",
                jobId=12, attemptId=13, createdAt=1,
            )
            dao.insert(terminal)
            dao.insert(candidate)
            assertFalse(candidateEvidenceAcknowledged(dao.listForAttempt(12,13)))
            dao.markAcked(candidate.outboxId, 77, System.currentTimeMillis())
            assertTrue(candidateEvidenceAcknowledged(dao.listForAttempt(12,13)))
        } finally {
            db.close()
        }
    }
}
