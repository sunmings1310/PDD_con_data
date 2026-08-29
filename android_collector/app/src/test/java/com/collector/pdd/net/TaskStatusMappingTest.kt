package com.collector.pdd.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TaskStatusMappingTest {
    @Test fun mapsKnownCompletionStates() {
        assertEquals("complete", TaskStatusMapping.completionFor("finished"))
        assertEquals("failed", TaskStatusMapping.completionFor("failed"))
        assertEquals("cancelled", TaskStatusMapping.completionFor("stopped"))
    }

    @Test fun rejectsUnknownCompletionState() {
        assertThrows(IllegalArgumentException::class.java) {
            TaskStatusMapping.completionFor("mystery")
        }
    }

    @Test fun mapsItemResultsWithoutConflatingNoMatchAndFailure() {
        assertEquals("succeeded", TaskStatusMapping.itemResult(true))
        assertEquals("not_matched", TaskStatusMapping.itemResult(false))
    }

    @Test fun mapsNaturalTargetMissToDedicatedTerminalStatus() {
        assertEquals("not_matched", TaskStatusMapping.completionFor("not_matched"))
        assertEquals("business_rejection" to "TARGET_NOT_MATCHED", TaskStatusMapping.jobFailureFor("not_matched"))
    }
}
