package com.collector.pdd.net

import org.json.JSONObject

/** Durable server-issued execution identity. The lease token is never logged. */
data class JobLeaseIdentity(
    val taskId: Long,
    val jobId: Long,
    val jobKey: String,
    val jobType: String,
    val payload: JSONObject,
    val attemptId: Long,
    val attemptNo: Int,
    val leaseToken: String,
    val workerId: String,
    val traceId: String,
    val checkpointVersion: Int,
    val leaseExpiresAt: Long,
)

class JobProtocolException(
    val errorCode: String,
    message: String,
    val currentStatus: String? = null,
) : IllegalStateException(message)

/** The jobs API is absent on an older server; only this case permits legacy pull. */
class JobProtocolUnavailableException(message: String) : IllegalStateException(message)

enum class RecoveryDecision { RESUME, WAIT_FOR_SERVER, REJECT_STALE, ACQUIRE }

enum class JobTerminalAction { COMPLETE, FAIL_NO_RESULT, FAIL_REJECTED }

fun jobTerminalAction(acknowledgedProducts: Int, rejectedProducts: Int): JobTerminalAction = when {
    rejectedProducts > 0 -> JobTerminalAction.FAIL_REJECTED
    acknowledgedProducts == 0 -> JobTerminalAction.FAIL_NO_RESULT
    else -> JobTerminalAction.COMPLETE
}

/** Pure policy keeps process-death behaviour deterministic and JVM-testable. */
fun recoveryDecision(
    localAssignment: Boolean,
    serverAssignment: Boolean,
    sameAttempt: Boolean,
    leaseRejected: Boolean = false,
): RecoveryDecision = when {
    leaseRejected -> RecoveryDecision.REJECT_STALE
    localAssignment && serverAssignment && sameAttempt -> RecoveryDecision.RESUME
    localAssignment && !serverAssignment -> RecoveryDecision.WAIT_FOR_SERVER
    !localAssignment && serverAssignment -> RecoveryDecision.WAIT_FOR_SERVER
    else -> RecoveryDecision.ACQUIRE
}

fun JSONObject.toJobLease(workerId: String): JobLeaseIdentity {
    val taskId = optLong("task_id", 0L)
    val jobId = optLong("job_id", 0L)
    val attemptId = optLong("attempt_id", 0L)
    val token = optString("lease_token")
    require(taskId > 0 && jobId > 0 && attemptId > 0 && token.length >= 32) {
        "job acquire response has incomplete lease identity"
    }
    val expiresAt = optLong("lease_expires_at", 0L).takeIf { it > 0L }
        ?: (System.currentTimeMillis() + optLong("lease_seconds", 120L).coerceIn(1L, 3600L) * 1000L)
    val payload = optJSONObject("payload") ?: JSONObject()
    optJSONObject("checkpoint")?.let { payload.put("_checkpoint", it) }
    return JobLeaseIdentity(
        taskId = taskId,
        jobId = jobId,
        jobKey = optString("job_key"),
        jobType = optString("job_type"),
        payload = payload,
        attemptId = attemptId,
        attemptNo = optInt("attempt_no", 1),
        leaseToken = token,
        workerId = workerId,
        traceId = optString("trace_id"),
        checkpointVersion = optInt("checkpoint_version", 0),
        leaseExpiresAt = expiresAt,
    )
}
