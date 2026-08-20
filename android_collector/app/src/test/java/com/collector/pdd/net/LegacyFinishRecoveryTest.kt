package com.collector.pdd.net

import com.collector.pdd.data.OutboxEntity
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class LegacyFinishRecoveryTest {
    @Test
    fun cancelledAbortRequeuesOnlyUnackedLegacyFinish() {
        val stuck = OutboxEntity(
            outboxId = "finish-677-0",
            eventType = "finish",
            remoteTaskId = 677,
            payloadJson = "{}",
            state = "retry",
            nextAttemptAt = Long.MAX_VALUE,
        )
        assertTrue(shouldRequeueLegacyFinishForCancellation(stuck, "cancelled"))
        assertFalse(shouldRequeueLegacyFinishForCancellation(stuck, "failed"))
        assertFalse(shouldRequeueLegacyFinishForCancellation(stuck.copy(state = "acked"), "cancelled"))
        assertFalse(
            shouldRequeueLegacyFinishForCancellation(
                stuck.copy(jobId = 1, attemptId = 1),
                "cancelled",
            )
        )
    }

    @Test
    fun jsonNullTargetFieldsRemainOptionalInsteadOfBecomingMatchCriteria() {
        val item = JSONObject()
            .put("target_approval", JSONObject.NULL)
            .put("target_name", "null")
            .put("target_spec", "  ")
        assertTrue(optionalJsonText(item, "target_approval").isEmpty())
        assertTrue(optionalJsonText(item, "target_name").isEmpty())
        assertTrue(optionalJsonText(item, "target_spec").isEmpty())
        assertTrue(optionalJsonText(item, "target_manufacturer").isEmpty())
    }
}
