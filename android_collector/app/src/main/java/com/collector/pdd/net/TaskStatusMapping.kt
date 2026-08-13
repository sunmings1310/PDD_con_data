package com.collector.pdd.net

/** Protocol adapter only. The server remains authoritative for business state. */
object TaskStatusMapping {
    const val COMPLETE = "complete"
    const val FAILED = "failed"
    const val CANCELLED = "cancelled"

    fun completionFor(localStatus: String): String = when (localStatus) {
        "finished" -> COMPLETE
        "failed" -> FAILED
        "stopped" -> CANCELLED
        else -> throw IllegalArgumentException("unknown Android task status: $localStatus")
    }

    fun itemResult(matched: Boolean): String = if (matched) "succeeded" else "not_matched"
}
