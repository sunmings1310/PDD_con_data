package com.collector.pdd.net

object OutboxRetryPolicy {
    fun delayMillis(attemptCount: Int): Long {
        val exponent = attemptCount.coerceIn(0, 8)
        return (2_000L * (1L shl exponent)).coerceAtMost(5 * 60_000L)
    }
}
