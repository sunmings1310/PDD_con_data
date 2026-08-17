package com.collector.pdd.net

import org.junit.Assert.assertEquals
import org.junit.Test

class OutboxRetryPolicyTest {
    @Test fun exponentialBackoffIsBounded() {
        assertEquals(2_000L, OutboxRetryPolicy.delayMillis(0))
        assertEquals(4_000L, OutboxRetryPolicy.delayMillis(1))
        assertEquals(300_000L, OutboxRetryPolicy.delayMillis(20))
    }
}
