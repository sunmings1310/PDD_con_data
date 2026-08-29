package com.collector.pdd.net

/** Protocol adapter only. The server remains authoritative for business state. */
object TaskStatusMapping {
    const val COMPLETE = "complete"
    const val FAILED = "failed"
    const val CANCELLED = "cancelled"
    const val NOT_MATCHED = "not_matched"

    fun completionFor(localStatus: String): String = when (localStatus) {
        "finished" -> COMPLETE
        "failed" -> FAILED
        "stopped" -> CANCELLED
        NOT_MATCHED -> NOT_MATCHED
        else -> throw IllegalArgumentException("unknown Android task status: $localStatus")
    }

    fun itemResult(matched: Boolean): String = if (matched) "succeeded" else "not_matched"

    fun jobFailureFor(localStatus: String): Pair<String, String> = when (completionFor(localStatus)) {
        NOT_MATCHED -> "business_rejection" to "TARGET_NOT_MATCHED"
        else -> "transient" to "LOCAL_TASK_FINISHED"
    }
}
