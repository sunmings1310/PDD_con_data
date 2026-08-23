package com.collector.pdd.collector

import com.collector.pdd.parser.DetailReader
import com.collector.pdd.parser.ProductQualityGate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CollectorRegistryTest {
    @Test
    fun registryDeclaresPddCapabilitiesAndFailsFastForUnknownPlatform() {
        val collector = CollectorRegistry.require(" PINDUODUO ")
        assertEquals(setOf("pinduoduo"), CollectorRegistry.platforms())
        assertTrue(collector.capabilities.supports(CollectorCapability.SEARCH))
        assertTrue(collector.capabilities.supports(CollectorCapability.DETAIL))
        assertTrue(collector.capabilities.supports(CollectorCapability.PRICE_SORT))
        assertTrue(collector.capabilities.supports(CollectorCapability.SALES_SORT))
        assertFalse(collector.capabilities.supports(CollectorCapability.CURSOR_PAGINATION))
        assertTrue(DynamicField.SALES in collector.capabilities.supportedDynamicFields)

        val error = runCatching { CollectorRegistry.require("jd") }.exceptionOrNull()
        assertTrue(error is CollectorException)
        assertEquals(SystemCollectorError.PLATFORM_NOT_SUPPORTED, (error as CollectorException).code)
    }

    @Test(expected = IllegalArgumentException::class)
    fun duplicateRegistrationIsRejected() {
        CollectorRegistry.register(PddCollector())
    }

    @Test
    fun pddAdapterPreservesParserAndQualityBehavior() {
        val collector = PddCollector()
        val page = """
            商品详情
            立即购买
            测试牌 感冒灵颗粒
            ￥9.90
            已拼100件
            goods_id=12345678
        """.trimIndent()
        val request = DetailParseRequest(
            pageText = page,
            keyword = "感冒灵",
            pickTag = "default_top_1",
            itemIdHint = "12345678",
            urlHint = "https://mobile.yangkeduo.com/goods.html?goods_id=12345678",
        )
        val before = DetailReader.parse(
            pageText = request.pageText,
            keyword = request.keyword,
            pickTag = request.pickTag,
            itemIdHint = request.itemIdHint,
            urlHint = request.urlHint,
        )
        val after = collector.normalizeForCompatibility(request)
        // Parsing compatibility excludes the observation timestamp, which is generated per call.
        assertEquals(before.copy(updateTime = after.updateTime), after)

        val beforeQuality = ProductQualityGate.apply(page, before)
        val afterQuality = collector.applyQualityForCompatibility(page, after)
        assertEquals(beforeQuality.first, afterQuality.first)
        assertEquals(beforeQuality.second.pageStatus, afterQuality.second.pageStatus)
        assertEquals(beforeQuality.second.parseStatus, afterQuality.second.parseStatus)
        assertEquals(beforeQuality.second.qualityStatus, afterQuality.second.qualityStatus)
        assertEquals(beforeQuality.second.missingFields, afterQuality.second.missingFields)
        assertEquals(beforeQuality.second.warnings, afterQuality.second.warnings)
    }

    @Test
    fun pddErrorsMapToSystemVocabulary() {
        val collector = CollectorRegistry.require("pinduoduo")
        assertEquals(SystemCollectorError.AUTH_REQUIRED, collector.mapError("login_required"))
        assertEquals(SystemCollectorError.RATE_LIMITED, collector.mapError("busy"))
        assertEquals(SystemCollectorError.ITEM_NOT_FOUND, collector.mapError("not_found"))
        assertEquals(SystemCollectorError.ITEM_UNAVAILABLE, collector.mapError("sold_out"))
        assertEquals(SystemCollectorError.PARSE_ERROR, collector.mapError("malformed"))
        assertEquals(SystemCollectorError.DATA_QUALITY_FAILURE, collector.mapError("quarantined"))
    }

    @Test
    fun unsupportedCapabilityFailsFast() {
        val collector = CollectorRegistry.require("pinduoduo")
        val error = runCatching { collector.requireCapability(CollectorCapability.CURSOR_PAGINATION) }.exceptionOrNull()
        assertTrue(error is CollectorException)
        assertEquals(SystemCollectorError.CAPABILITY_NOT_SUPPORTED, (error as CollectorException).code)
    }

    @Test
    fun publicContractsDoNotExposePddUiOrLinkHelpers() {
        assertEquals(
            setOf("collect"),
            DetailCollector::class.java.declaredMethods.map { it.name }.toSet(),
        )
        val sessionMethods = CollectorSession::class.java.declaredMethods.map { it.name }.toSet()
        assertFalse(sessionMethods.any { it.contains("Sku", true) || it.contains("Shop", true) || it.contains("Share", true) })
        assertFalse(sessionMethods.any { it.contains("sortBy", true) || it.contains("scroll", true) })
    }

    @Test
    fun systemErrorsHaveExplicitSchedulingActions() {
        assertEquals(CollectorErrorAction.RETRY, CollectorErrorPolicy.action(SystemCollectorError.RATE_LIMITED))
        assertEquals(CollectorErrorAction.RETRY, CollectorErrorPolicy.action(SystemCollectorError.TEMPORARY_FAILURE))
        assertEquals(CollectorErrorAction.STOP_TASK, CollectorErrorPolicy.action(SystemCollectorError.AUTH_REQUIRED))
        assertEquals(CollectorErrorAction.STOP_TASK, CollectorErrorPolicy.action(SystemCollectorError.MANUAL_INTERVENTION_REQUIRED))
        assertEquals(CollectorErrorAction.FAIL_ITEM, CollectorErrorPolicy.action(SystemCollectorError.ITEM_NOT_FOUND))
        assertEquals(CollectorErrorAction.FAIL_ITEM, CollectorErrorPolicy.action(SystemCollectorError.ITEM_UNAVAILABLE))
        assertEquals(CollectorErrorAction.FAIL_ITEM, CollectorErrorPolicy.action(SystemCollectorError.PARSE_ERROR))
        assertEquals(CollectorErrorAction.FAIL_ITEM, CollectorErrorPolicy.action(SystemCollectorError.DATA_QUALITY_FAILURE))
        assertEquals(CollectorErrorAction.FAIL_FAST, CollectorErrorPolicy.action(SystemCollectorError.PLATFORM_NOT_SUPPORTED))
        assertEquals(CollectorErrorAction.FAIL_FAST, CollectorErrorPolicy.action(SystemCollectorError.CAPABILITY_NOT_SUPPORTED))
        assertTrue(CollectorErrorPolicy.canRetry(SystemCollectorError.RATE_LIMITED, 0, 2))
        assertTrue(CollectorErrorPolicy.canRetry(SystemCollectorError.TEMPORARY_FAILURE, 1, 2))
        assertFalse(CollectorErrorPolicy.canRetry(SystemCollectorError.RATE_LIMITED, 2, 2))
        assertFalse(CollectorErrorPolicy.canRetry(SystemCollectorError.AUTH_REQUIRED, 0, 2))
    }

    @Test
    fun pddRiskKeepsBaselineBusyPolicyAndRiskCooldownAfterSystemMapping() {
        val mappedRisk = CollectorException(
            code = SystemCollectorError.MANUAL_INTERVENTION_REQUIRED,
            message = "risk control",
            recoveryHint = CollectorRecoveryHint.RISK_POLICY,
        )

        assertEquals(CollectorErrorAction.RETRY, CollectorErrorPolicy.action(mappedRisk))
        assertEquals(
            CollectorRetryDisposition.STOP,
            CollectorErrorPolicy.retryDisposition(mappedRisk, "stop", retriesCompleted = 0, maxRetries = 2),
        )
        assertEquals(
            CollectorRetryDisposition.SKIP,
            CollectorErrorPolicy.retryDisposition(mappedRisk, "skip", retriesCompleted = 0, maxRetries = 2),
        )
        assertEquals(
            CollectorRetryDisposition.RETRY,
            CollectorErrorPolicy.retryDisposition(mappedRisk, "retry", retriesCompleted = 1, maxRetries = 2),
        )
        assertEquals(
            CollectorRetryDisposition.EXHAUSTED,
            CollectorErrorPolicy.retryDisposition(mappedRisk, "retry", retriesCompleted = 2, maxRetries = 2),
        )
        assertEquals(60_000L, CollectorErrorPolicy.cooldownMs(mappedRisk, 15_000L, 60_000L))

        val ordinaryManual = CollectorException(SystemCollectorError.MANUAL_INTERVENTION_REQUIRED)
        assertEquals(CollectorErrorAction.STOP_TASK, CollectorErrorPolicy.action(ordinaryManual))
    }
}
