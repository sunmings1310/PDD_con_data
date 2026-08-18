package com.collector.pdd.collector

enum class CollectorErrorAction { RETRY, STOP_TASK, FAIL_ITEM, FAIL_FAST }
enum class CollectorRetryDisposition { RETRY, SKIP, STOP, EXHAUSTED }

object CollectorErrorPolicy {
    fun action(code: SystemCollectorError): CollectorErrorAction = when (code) {
        SystemCollectorError.TEMPORARY_FAILURE,
        SystemCollectorError.RATE_LIMITED -> CollectorErrorAction.RETRY

        SystemCollectorError.AUTH_REQUIRED,
        SystemCollectorError.MANUAL_INTERVENTION_REQUIRED -> CollectorErrorAction.STOP_TASK

        SystemCollectorError.ITEM_NOT_FOUND,
        SystemCollectorError.ITEM_UNAVAILABLE,
        SystemCollectorError.PARSE_ERROR,
        SystemCollectorError.DATA_QUALITY_FAILURE -> CollectorErrorAction.FAIL_ITEM

        SystemCollectorError.PLATFORM_NOT_SUPPORTED,
        SystemCollectorError.CAPABILITY_NOT_SUPPORTED -> CollectorErrorAction.FAIL_FAST
    }

    fun action(error: CollectorException): CollectorErrorAction =
        if (error.recoveryHint == CollectorRecoveryHint.RISK_POLICY) CollectorErrorAction.RETRY else action(error.code)

    fun canRetry(code: SystemCollectorError, retriesCompleted: Int, maxRetries: Int): Boolean =
        action(code) == CollectorErrorAction.RETRY && retriesCompleted < maxRetries.coerceAtLeast(0)

    fun canRetry(error: CollectorException, retriesCompleted: Int, maxRetries: Int): Boolean =
        action(error) == CollectorErrorAction.RETRY && retriesCompleted < maxRetries.coerceAtLeast(0)

    fun cooldownMs(error: CollectorException, busyCooldownMs: Long, riskCooldownMs: Long): Long =
        if (error.recoveryHint == CollectorRecoveryHint.RISK_POLICY) riskCooldownMs else busyCooldownMs

    fun retryDisposition(
        error: CollectorException,
        configuredResponse: String,
        retriesCompleted: Int,
        maxRetries: Int,
    ): CollectorRetryDisposition = when (configuredResponse.lowercase()) {
        "stop" -> CollectorRetryDisposition.STOP
        "skip" -> CollectorRetryDisposition.SKIP
        else -> if (canRetry(error, retriesCompleted, maxRetries)) {
            CollectorRetryDisposition.RETRY
        } else {
            CollectorRetryDisposition.EXHAUSTED
        }
    }
}
