package com.collector.pdd.collector

import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.ProductEntity
import com.collector.pdd.engine.GoodsLinkResolver
import com.collector.pdd.engine.AccessGuard
import com.collector.pdd.engine.AccessIssueType
import com.collector.pdd.engine.PddActions
import com.collector.pdd.engine.HumanBehavior
import com.collector.pdd.parser.DetailReader
import com.collector.pdd.parser.ProductQualityGate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

class PddCollector : Collector {
    override val platform: String = "pinduoduo"
    override val capabilities = CollectorCapabilities(
        capabilities = setOf(
            CollectorCapability.SEARCH,
            CollectorCapability.DETAIL,
            CollectorCapability.PRICE_SORT,
            CollectorCapability.SALES_SORT,
            CollectorCapability.OFFSET_PAGINATION,
        ),
        supportedIdentity = setOf(IdentityKind.PLATFORM_PRODUCT_ID),
        supportedDynamicFields = setOf(
            DynamicField.PRICE,
            DynamicField.ORIGINAL_PRICE,
            DynamicField.SALES,
            DynamicField.SKU_PRICE,
            DynamicField.PROMOTION,
        ),
    )

    override val searchCollector: SearchCollector = PddSearchCollector
    override val detailCollector: DetailCollector = PddDetailCollector

    override fun createSession(log: (String) -> Unit, config: CollectConfig): CollectorSession =
        PddCollectorSession(PddActions(log, config))

    internal fun normalizeForCompatibility(request: DetailParseRequest): ProductEntity =
        PddDetailCollector.normalize(request)

    internal fun applyQualityForCompatibility(
        pageText: String,
        product: ProductEntity,
    ): Pair<ProductEntity, QualityDecision> = PddDetailCollector.applyQuality(pageText, product)

    override fun mapError(platformError: String): SystemCollectorError = mapPddError(platformError)
}

private fun mapPddError(platformError: String): SystemCollectorError = when (platformError.trim().lowercase()) {
    "login_required", "auth_required" -> SystemCollectorError.AUTH_REQUIRED
    "challenge", "risk", "verification_required" -> SystemCollectorError.MANUAL_INTERVENTION_REQUIRED
    "busy", "rate_limited", "too_many_requests" -> SystemCollectorError.RATE_LIMITED
    "not_found", "item_not_found" -> SystemCollectorError.ITEM_NOT_FOUND
    "sold_out", "delisted", "item_unavailable" -> SystemCollectorError.ITEM_UNAVAILABLE
    "parse_error", "malformed" -> SystemCollectorError.PARSE_ERROR
    "quality_failed", "quarantined" -> SystemCollectorError.DATA_QUALITY_FAILURE
    else -> SystemCollectorError.TEMPORARY_FAILURE
}

private object PddSearchCollector : SearchCollector {
    override suspend fun search(session: CollectorSession, request: SearchRequest): SearchResult {
        val actions = session.pddActions("search")
        actions.searchKeyword(request.keyword)
        when (request.sort) {
            SearchSort.DEFAULT -> Unit
            SearchSort.PRICE_ASC -> actions.sortByPriceAsc()
            SearchSort.SALES_DESC -> actions.sortBySalesDesc()
        }
        if (request.prefetchPages > 0) actions.scrollList(request.prefetchPages)
        return SearchResult(actions.searchCandidates(request.limit))
    }

    override suspend fun restore(session: CollectorSession, request: SearchRequest): SearchRestoreResult {
        val actions = session.pddActions("search restore")
        if (actions.returnToSearchList()) return SearchRestoreResult(restored = true, researched = false)
        val restored = runCatching {
            search(session, request)
            actions.looksLikeSearchList() || actions.listCardsOrEmpty().isNotEmpty()
        }.getOrDefault(false)
        return SearchRestoreResult(restored = restored, researched = true)
    }
}

private data class PddResolvedLink(
    val platformProductId: String = "",
    val itemUrl: String = "",
    val images: List<String> = emptyList(),
    val title: String = "",
    val rejected: Boolean = false,
    val rejectReason: String = "",
)

private object PddDetailCollector : DetailCollector {
    override suspend fun collect(session: CollectorSession, request: DetailCollectionRequest): DetailCollectionResult {
        val actions = (session as? PddCollectorSession)?.actions
            ?: throw CollectorException(SystemCollectorError.CAPABILITY_NOT_SUPPORTED, "PDD detail requires PDD session")
        val log = request.log
        val searchCapturedAt = System.currentTimeMillis()
        val searchPageText = actions.readPageText()
        val (opened, listMeta) = actions.openCardAt(request.openIndex)
        if (!opened) {
            return DetailCollectionResult(
                raw = RawResult("pinduoduo", actions.readPageText()),
                failureAction = "open_card",
                failureMessage = "列表为空或第 ${request.openIndex + 1} 个商品无法打开",
            )
        }
        detect(actions.readPageText())?.let { throw it }

        HumanBehavior.sleepMs(900.0, 1600.0)
        val probeImages = actions.tryProbeMainImage(listMeta.itemId, alreadyAtTop = true)
        if (!actions.ensureOnGoodsDetail(request.openIndex)) {
            val page = actions.readPageText()
            detect(page)?.let { throw it }
            return DetailCollectionResult(
                raw = RawResult("pinduoduo", page),
                failureAction = "restore_detail",
                failureMessage = "采图后未能停留在商品详情",
            )
        }

        HumanBehavior.sleepMs(350.0, 800.0)
        var priceText = actions.readPageText()
        var shopSalesText = ""
        var paramsText = ""
        // Accepted baseline deliberately excludes automatic SKU panel interaction.
        // SKU_PANEL remains a representable RawSource type, but normal collection
        // must not open purchase controls or enumerate combinations.
        val midSteps = listOf("params", "shop_sales", "human")
        log("采图后固定执行商品信息采集：${midSteps.joinToString(" → ")}")
        for ((idx, step) in midSteps.withIndex()) {
            if (idx > 0) runCatching { actions.randomBridgeHuman("step_$step") }
            when (step) {
                "params" -> {
                    paramsText = runCatching { actions.openAndReadProductParams() }
                        .onFailure { log("商品参数读取失败: ${it.message}") }.getOrDefault("")
                    if (!actions.ensureOnGoodsDetail(request.openIndex)) log("读参数后已离开详情，尝试恢复失败")
                }
                "shop_sales" -> {
                    shopSalesText = runCatching { actions.peekShopSalesText() }.getOrDefault("")
                    priceText += "\n" + actions.readPageText()
                }
                "human" -> runCatching { actions.maybeDetailHumanGestures() }
                    .onFailure { log("详情拟人动作异常: ${it.message}") }
            }
        }

        runCatching { actions.randomBridgeHuman("before_share") }
        if (!actions.ensureOnGoodsDetail(request.openIndex)) log("取链前不在详情页，跳过分享取链")
        log("开始复制链接解析…")
        val share = if (actions.looksLikeGoodsDetail()) actions.tryCaptureShareLink() else PddActions.ShareCapture()
        val harvest = actions.harvestPage()
        val mainText = actions.readPageText()
        val pageText = buildString {
            append(priceText).append('\n')
            if (shopSalesText.isNotBlank()) append(shopSalesText).append('\n')
            append(mainText)
            if (paramsText.isNotBlank()) append("\n---商品参数---\n").append(paramsText)
        }
        var product = normalize(
            DetailParseRequest(
                pageText, request.keyword, request.pickTag, listMeta.listPrice, listMeta.itemId,
                harvest.mallId, emptyList(), "", "",
            )
        )

        var shareId = share.goodsId
            .ifBlank { extractProductId(share.url) }
            .ifBlank { extractProductId(share.raw) }
        var shareUrl = when {
            share.url.isNotBlank() -> share.url
            shareId.isNotBlank() -> buildProductUrl(shareId)
            else -> extractProductUrls(share.raw).firstOrNull().orEmpty()
        }
        if (shareId.isBlank() && (shareUrl.contains("ps=", true) || shareUrl.contains("goods1.html", true) || share.raw.contains("ps=", true))) {
            log("检测到 ps= 分享链，正在展开…")
            val expanded = runCatching { withContext(Dispatchers.IO) { expandShareLink(shareUrl.ifBlank { share.raw }) } }
                .onFailure { log("ps= 展开失败: ${it.message}") }.getOrDefault(PddResolvedLink())
            if (expanded.platformProductId.isNotBlank()) {
                shareId = expanded.platformProductId
                shareUrl = expanded.itemUrl.ifBlank { buildProductUrl(shareId) }
                log("ps= 展开成功 id=$shareId")
            } else if (expanded.itemUrl.isNotBlank() && shareUrl.isBlank()) shareUrl = expanded.itemUrl
        }
        if (shareId.isNotBlank() || shareUrl.isNotBlank()) {
            product = product.copy(itemId = shareId.ifBlank { product.itemId }, itemUrl = shareUrl.ifBlank { product.itemUrl })
            log("已写入分享链 id=${product.itemId.ifBlank { "-" }} url=${product.itemUrl.ifBlank { "-" }.take(90)}")
        }

        val expectTokens = listOf(request.keyword, product.productName, product.brand, product.sellName)
            .flatMap { it.split(" ", "　", "/", "·", ",") }.map(String::trim).filter { it.length >= 2 }.distinct()
        val resolved = runCatching {
            resolveLink(share.raw.take(4000), shareUrl.ifBlank { product.itemUrl }, shareId.ifBlank { product.itemId }, expectTokens)
        }.onFailure { log("网络解析跳过: ${it.message}") }.getOrDefault(PddResolvedLink())
        if (resolved.rejected && resolved.itemUrl.isBlank() && resolved.platformProductId.isBlank()) {
            log("网络补图跳过（防串号）: ${resolved.rejectReason}")
        } else if (resolved.platformProductId.isNotBlank()) {
            val idOk = shareId.isBlank() || shareId == resolved.platformProductId
            if (idOk) {
                product = product.copy(
                    itemId = resolved.platformProductId,
                    itemUrl = resolved.itemUrl.ifBlank { buildProductUrl(resolved.platformProductId) },
                    mainImages = resolved.images.takeIf { it.isNotEmpty() }?.joinToString("|") ?: product.mainImages,
                )
            } else if (resolved.images.isNotEmpty() && product.mainImages.isBlank()) {
                product = product.copy(mainImages = resolved.images.joinToString("|"))
            }
        } else {
            if (resolved.itemUrl.isNotBlank() && product.itemUrl.isBlank()) product = product.copy(itemUrl = resolved.itemUrl)
            if (resolved.images.isNotEmpty() && product.mainImages.isBlank()) product = product.copy(mainImages = resolved.images.joinToString("|"))
        }

        val localImages = buildList {
            if (listMeta.imageHint.isNotBlank()) add(listMeta.imageHint)
            addAll(probeImages); addAll(share.images); addAll(harvest.images)
        }.filter(::isProductImageUrl).distinct()
        if (product.mainImages.isBlank() && localImages.isNotEmpty()) product = product.copy(mainImages = localImages.joinToString("|"))
        if (product.mainImages.isNotBlank()) {
            product = product.copy(mainImages = product.mainImages.split("|").filter(::isProductImageUrl).distinct().joinToString("|"))
        }
        if (product.itemId.isNotBlank() && product.itemUrl.isBlank()) product = product.copy(itemUrl = buildProductUrl(product.itemId))
        val (checked, quality) = applyQuality(pageText, product)
        val capturedAt = System.currentTimeMillis()
        val sources = buildList {
            add(RawSource(
                type = "SEARCH",
                sourceIdentifier = "search-card:${request.openIndex}",
                capturedAtEpochMs = searchCapturedAt,
                contentType = "application/json",
                payload = JSONObject()
                    .put("keyword", request.keyword)
                    .put("open_index", request.openIndex)
                    .put("list_price", listMeta.listPrice ?: JSONObject.NULL)
                    .put("item_id_hint", listMeta.itemId)
                    .put("title_hint", listMeta.titleHint)
                    .put("image_hint", listMeta.imageHint)
                    .put("page_text", searchPageText)
                    .toString(),
            ))
            add(RawSource("DETAIL", "goods-detail", capturedAt, payload = pageText))
            if (shopSalesText.isNotBlank()) add(RawSource("SHOP", "shop-sales", capturedAt, payload = shopSalesText))
            if (checked.couponInfo.isNotBlank()) {
                add(RawSource("PROMOTION", "detail-promotion", capturedAt, payload = pageText))
            }
            val media = (localImages + checked.mainImages.split("|").filter(String::isNotBlank)).distinct()
            if (media.isNotEmpty()) add(RawSource(
                "MEDIA", "product-media", capturedAt, contentType = "application/json",
                payload = JSONObject().put("items", JSONArray(media.mapIndexed { index, url ->
                    JSONObject().put("url", url).put("type", "image").put("order", index)
                })).toString(),
            ))
            if (harvest.blob.isNotBlank() || harvest.urls.isNotEmpty() || share.raw.isNotBlank()) {
                add(RawSource(
                    "EMBEDDED", "accessibility-harvest", capturedAt, contentType = "application/json",
                    payload = JSONObject()
                        .put("goods_id", harvest.goodsId)
                        .put("mall_id", harvest.mallId)
                        .put("urls", JSONArray(harvest.urls))
                        .put("images", JSONArray(harvest.images))
                        .put("blob", harvest.blob)
                        .put("share", share.raw)
                        .toString(),
                ))
            }
            if (paramsText.isNotBlank()) add(RawSource("OTHER", "product-params", capturedAt, payload = paramsText))
        }
        return DetailCollectionResult(
            product = checked,
            raw = RawResult(
                platform = "pinduoduo",
                evidence = pageText,
                identity = checked.itemId.takeIf(String::isNotBlank)?.let { PlatformIdentity("pinduoduo", it) },
                dynamicFields = mapOf(
                    DynamicField.PRICE to checked.displayPrice,
                    DynamicField.ORIGINAL_PRICE to checked.originalPrice,
                    DynamicField.SALES to checked.salesNum,
                    DynamicField.SKU_PRICE to checked.skuPrices,
                    DynamicField.PROMOTION to checked.couponInfo,
                ),
                pageStatus = quality.pageStatus,
                parseStatus = quality.parseStatus,
                fieldSources = checked.fieldSources,
                parserVersion = checked.parserVersion,
                capabilities = PddCollector().capabilities,
                sources = sources,
            ),
            quality = quality,
            paramsCaptured = paramsText.isNotBlank(),
        )
    }

    private fun detect(pageText: String): CollectorException? = AccessGuard.detect(pageText)?.let {
        val platformError = when (it.type) {
            AccessIssueType.SOLD_OUT -> "sold_out"
            AccessIssueType.RISK -> "risk"
            AccessIssueType.BUSY -> "busy"
        }
        CollectorException(
            code = mapPddError(platformError),
            message = it.evidence,
            recoveryHint = if (it.type == AccessIssueType.RISK) {
                CollectorRecoveryHint.RISK_POLICY
            } else {
                CollectorRecoveryHint.DEFAULT
            },
        )
    }

    fun normalize(request: DetailParseRequest): ProductEntity = DetailReader.parse(
        pageText = request.pageText,
        keyword = request.keyword,
        pickTag = request.pickTag,
        listPrice = request.listPrice,
        itemIdHint = request.itemIdHint,
        shopIdHint = request.shopIdHint,
        imageHints = request.imageHints,
        urlHint = request.urlHint,
        skuPanelText = request.skuPanelText,
    )

    fun applyQuality(pageText: String, product: ProductEntity): Pair<ProductEntity, QualityDecision> {
        val (checked, decision) = ProductQualityGate.apply(pageText, product)
        return checked to QualityDecision(
            pageStatus = decision.pageStatus,
            parseStatus = decision.parseStatus,
            qualityStatus = decision.qualityStatus,
            missingFields = decision.missingFields,
            warnings = decision.warnings,
        )
    }

    private fun extractProductId(value: String): String = GoodsLinkResolver.extractGoodsId(value)
    private fun buildProductUrl(platformProductId: String): String = GoodsLinkResolver.buildGoodsUrl(platformProductId)
    private fun extractProductUrls(value: String): List<String> = GoodsLinkResolver.extractGoodsUrls(value)
    private suspend fun expandShareLink(value: String): PddResolvedLink = GoodsLinkResolver.expandShareLink(value).asAdapterResult()
    private suspend fun resolveLink(
        rawShare: String,
        hintUrl: String,
        hintProductId: String,
        expectTokens: List<String>,
    ): PddResolvedLink = GoodsLinkResolver.resolve(rawShare, hintUrl, hintProductId, expectTokens).asAdapterResult()

    private fun isProductImageUrl(value: String): Boolean = GoodsLinkResolver.isProductImageUrl(value)

    private fun GoodsLinkResolver.Resolved.asAdapterResult() = PddResolvedLink(
        platformProductId = goodsId,
        itemUrl = itemUrl,
        images = images,
        title = title,
        rejected = rejected,
        rejectReason = rejectReason,
    )
}

private class PddCollectorSession(val actions: PddActions) : CollectorSession {
    override suspend fun start() = actions.openPdd()
    override suspend fun browseCandidate(position: Int, readMinMs: Long, readMaxMs: Long): Boolean {
        val opened = actions.openCardAt(position).first
        if (opened) HumanBehavior.sleepMs(readMinMs.toDouble(), readMaxMs.toDouble())
        return opened
    }
    override suspend fun betweenKeywords() = actions.betweenKeywords()
    override suspend fun reset() = actions.goToPddHome()
    override suspend fun finish() = actions.finishAndReturnToApp()
    override suspend fun betweenItems() = actions.betweenItems()
}

private fun CollectorSession.pddActions(operation: String): PddActions =
    (this as? PddCollectorSession)?.actions
        ?: throw CollectorException(
            SystemCollectorError.CAPABILITY_NOT_SUPPORTED,
            "PDD $operation requires PDD session",
        )

private fun PddActions.searchCandidates(limit: Int): List<SearchCandidate> = listCardsOrEmpty()
    .take(limit).indices.map { index ->
        val meta = peekCardMeta(index)
        SearchCandidate(
            position = index,
            identity = meta.itemId.takeIf(String::isNotBlank)?.let { PlatformIdentity("pinduoduo", it) },
            listPrice = meta.listPrice,
        )
    }
