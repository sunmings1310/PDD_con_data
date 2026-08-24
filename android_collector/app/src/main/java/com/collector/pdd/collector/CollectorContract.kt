package com.collector.pdd.collector

import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.ProductEntity

enum class CollectorCapability {
    SEARCH,
    DETAIL,
    PRICE_SORT,
    SALES_SORT,
    OFFSET_PAGINATION,
    CURSOR_PAGINATION,
}

enum class IdentityKind { PLATFORM_PRODUCT_ID, PLATFORM_SKU_ID }

enum class DynamicField { PRICE, ORIGINAL_PRICE, SALES, SKU_PRICE, SKU_STOCK, PROMOTION }

data class CollectorCapabilities(
    val capabilities: Set<CollectorCapability>,
    val supportedIdentity: Set<IdentityKind>,
    val supportedDynamicFields: Set<DynamicField>,
) {
    fun supports(capability: CollectorCapability): Boolean = capability in capabilities
}

data class PlatformIdentity(
    val platform: String,
    val platformProductId: String,
    val platformSkuId: String? = null,
)

data class SearchRequest(
    val keyword: String,
    val limit: Int = 20,
    val cursor: String? = null,
    val sort: SearchSort = SearchSort.DEFAULT,
    val prefetchPages: Int = 0,
)

enum class SearchSort { DEFAULT, PRICE_ASC, SALES_DESC }

data class SearchResult(
    val candidates: List<SearchCandidate>,
    val nextCursor: String? = null,
)

data class SearchRestoreResult(val restored: Boolean, val researched: Boolean)

data class SearchCandidate(
    val position: Int,
    val identity: PlatformIdentity? = null,
    val listPrice: Double? = null,
)

data class RawResult(
    val platform: String,
    val evidence: String = "",
    val identity: PlatformIdentity? = null,
    val dynamicFields: Map<DynamicField, Any?> = emptyMap(),
    val pageStatus: String = "unknown",
    val parseStatus: String = "not_attempted",
    val fieldSources: String = "{}",
    val parserVersion: String = "",
    val capabilities: CollectorCapabilities? = null,
    /** 原始业务证据按采集阶段分组；上传前仍会执行最小敏感字段过滤。 */
    val sources: List<RawSource> = emptyList(),
)

data class RawSource(
    val type: String,
    val sourceIdentifier: String,
    val capturedAtEpochMs: Long,
    val contentType: String = "text/plain; charset=utf-8",
    val schemaHint: String? = null,
    val payload: String,
)

internal data class DetailParseRequest(
    val pageText: String,
    val keyword: String,
    val pickTag: String,
    val listPrice: Double? = null,
    val itemIdHint: String = "",
    val shopIdHint: String = "",
    val imageHints: List<String> = emptyList(),
    val urlHint: String = "",
    val skuPanelText: String = "",
)

data class DetailCollectionRequest(
    val keyword: String,
    val pickTag: String,
    val openIndex: Int,
    val log: (String) -> Unit,
)

data class DetailCollectionResult(
    val product: ProductEntity? = null,
    val raw: RawResult,
    val quality: QualityDecision? = null,
    val failureAction: String? = null,
    val failureMessage: String? = null,
    val paramsCaptured: Boolean = false,
)

data class QualityDecision(
    val pageStatus: String,
    val parseStatus: String,
    val qualityStatus: String,
    val missingFields: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
) {
    val accepted: Boolean get() = pageStatus == "product" && qualityStatus != "quarantined"
}

enum class SystemCollectorError {
    TEMPORARY_FAILURE,
    AUTH_REQUIRED,
    RATE_LIMITED,
    ITEM_NOT_FOUND,
    ITEM_UNAVAILABLE,
    PARSE_ERROR,
    DATA_QUALITY_FAILURE,
    MANUAL_INTERVENTION_REQUIRED,
    PLATFORM_NOT_SUPPORTED,
    CAPABILITY_NOT_SUPPORTED,
}

class CollectorException(
    val code: SystemCollectorError,
    message: String = code.name,
    val evidence: String = message,
    val recoveryHint: CollectorRecoveryHint = CollectorRecoveryHint.DEFAULT,
) : RuntimeException(message)

enum class CollectorRecoveryHint { DEFAULT, RISK_POLICY }

interface CollectorSession {
    suspend fun start()
    suspend fun browseCandidate(position: Int, readMinMs: Long, readMaxMs: Long): Boolean
    suspend fun betweenKeywords()
    suspend fun reset()
    suspend fun finish()
    suspend fun betweenItems()
}

interface SearchCollector {
    suspend fun search(session: CollectorSession, request: SearchRequest): SearchResult
    suspend fun restore(session: CollectorSession, request: SearchRequest): SearchRestoreResult
}

interface DetailCollector {
    suspend fun collect(session: CollectorSession, request: DetailCollectionRequest): DetailCollectionResult
}

interface Collector {
    val platform: String
    val capabilities: CollectorCapabilities
    val searchCollector: SearchCollector
    val detailCollector: DetailCollector
    fun createSession(log: (String) -> Unit, config: CollectConfig): CollectorSession
    fun mapError(platformError: String): SystemCollectorError
}

fun Collector.requireCapability(capability: CollectorCapability) {
    if (!capabilities.supports(capability)) {
        throw CollectorException(
            SystemCollectorError.CAPABILITY_NOT_SUPPORTED,
            "$platform does not support ${capability.name.lowercase()}",
        )
    }
}

suspend fun Collector.search(session: CollectorSession, request: SearchRequest): SearchResult {
    requireCapability(CollectorCapability.SEARCH)
    when (request.sort) {
        SearchSort.DEFAULT -> Unit
        SearchSort.PRICE_ASC -> requireCapability(CollectorCapability.PRICE_SORT)
        SearchSort.SALES_DESC -> requireCapability(CollectorCapability.SALES_SORT)
    }
    return searchCollector.search(session, request)
}

suspend fun Collector.restoreSearch(session: CollectorSession, request: SearchRequest): SearchRestoreResult {
    requireCapability(CollectorCapability.SEARCH)
    return searchCollector.restore(session, request)
}

suspend fun Collector.collectDetail(
    session: CollectorSession,
    request: DetailCollectionRequest,
): DetailCollectionResult {
    requireCapability(CollectorCapability.DETAIL)
    return detailCollector.collect(session, request)
}
