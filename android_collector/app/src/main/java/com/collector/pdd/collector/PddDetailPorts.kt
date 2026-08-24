package com.collector.pdd.collector

import com.collector.pdd.engine.GoodsLinkResolver
import com.collector.pdd.engine.HumanBehavior
import com.collector.pdd.engine.ListCardMeta
import com.collector.pdd.engine.PddActions
import com.collector.pdd.service.A11yHelper

/** Narrow behavior seam used by the accepted detail flow and its no-SKU runtime gate. */
internal interface PddDetailActions {
    fun readPageText(): String
    suspend fun openCardAt(index: Int): Pair<Boolean, ListCardMeta>
    suspend fun tryProbeMainImage(goodsId: String, alreadyAtTop: Boolean): List<String>
    suspend fun ensureOnGoodsDetail(openIndex: Int): Boolean
    suspend fun randomBridgeHuman(scene: String)
    suspend fun openAndReadProductParams(): String
    /** Legacy Phase 6A capability; accepted default detail flow must never invoke it. */
    suspend fun openAndReadSkuPrices(): String
    suspend fun peekShopSalesText(): String
    suspend fun maybeDetailHumanGestures()
    fun looksLikeGoodsDetail(): Boolean
    suspend fun tryCaptureShareLink(): PddActions.ShareCapture
    fun harvestPage(): A11yHelper.Harvest
    suspend fun pause(minMs: Double, maxMs: Double)
}

internal class PddDetailActionAdapter(private val delegate: PddActions) : PddDetailActions {
    override fun readPageText(): String = delegate.readPageText()
    override suspend fun openCardAt(index: Int) = delegate.openCardAt(index)
    override suspend fun tryProbeMainImage(goodsId: String, alreadyAtTop: Boolean) =
        delegate.tryProbeMainImage(goodsId, alreadyAtTop)
    override suspend fun ensureOnGoodsDetail(openIndex: Int) = delegate.ensureOnGoodsDetail(openIndex)
    override suspend fun randomBridgeHuman(scene: String) = delegate.randomBridgeHuman(scene)
    override suspend fun openAndReadProductParams() = delegate.openAndReadProductParams()
    override suspend fun openAndReadSkuPrices() = delegate.openAndReadSkuPrices()
    override suspend fun peekShopSalesText() = delegate.peekShopSalesText()
    override suspend fun maybeDetailHumanGestures() = delegate.maybeDetailHumanGestures()
    override fun looksLikeGoodsDetail() = delegate.looksLikeGoodsDetail()
    override suspend fun tryCaptureShareLink() = delegate.tryCaptureShareLink()
    override fun harvestPage() = delegate.harvestPage()
    override suspend fun pause(minMs: Double, maxMs: Double) {
        HumanBehavior.sleepMs(minMs, maxMs)
    }
}

internal data class PddResolvedLink(
    val platformProductId: String = "",
    val itemUrl: String = "",
    val images: List<String> = emptyList(),
    val title: String = "",
    val rejected: Boolean = false,
    val rejectReason: String = "",
)

internal interface PddDetailLinks {
    fun extractProductId(value: String): String
    fun buildProductUrl(platformProductId: String): String
    fun extractProductUrls(value: String): List<String>
    suspend fun expandShareLink(value: String): PddResolvedLink
    suspend fun resolveLink(
        rawShare: String,
        hintUrl: String,
        hintProductId: String,
        expectTokens: List<String>,
    ): PddResolvedLink
    fun isProductImageUrl(value: String): Boolean
}

internal object PddDetailLinkAdapter : PddDetailLinks {
    override fun extractProductId(value: String) = GoodsLinkResolver.extractGoodsId(value)
    override fun buildProductUrl(platformProductId: String) = GoodsLinkResolver.buildGoodsUrl(platformProductId)
    override fun extractProductUrls(value: String) = GoodsLinkResolver.extractGoodsUrls(value)
    override suspend fun expandShareLink(value: String) = GoodsLinkResolver.expandShareLink(value).toPortResult()
    override suspend fun resolveLink(
        rawShare: String,
        hintUrl: String,
        hintProductId: String,
        expectTokens: List<String>,
    ) = GoodsLinkResolver.resolve(rawShare, hintUrl, hintProductId, expectTokens).toPortResult()
    override fun isProductImageUrl(value: String) = GoodsLinkResolver.isProductImageUrl(value)

    private fun GoodsLinkResolver.Resolved.toPortResult() = PddResolvedLink(
        platformProductId = goodsId,
        itemUrl = itemUrl,
        images = images,
        title = title,
        rejected = rejected,
        rejectReason = rejectReason,
    )
}

internal data class PddDetailRuntime(
    val actions: PddDetailActions,
    val links: PddDetailLinks,
)

internal class PddDetailTestSession(
    val runtime: PddDetailRuntime,
) : CollectorSession {
    override suspend fun start() = Unit
    override suspend fun browseCandidate(position: Int, readMinMs: Long, readMaxMs: Long) = false
    override suspend fun betweenKeywords() = Unit
    override suspend fun reset() = Unit
    override suspend fun finish() = Unit
    override suspend fun betweenItems() = Unit
}
