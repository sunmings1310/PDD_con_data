package com.collector.pdd.collector

import com.collector.pdd.engine.ListCardMeta
import com.collector.pdd.engine.PddActions
import com.collector.pdd.engine.collectDetailThroughRegistry
import com.collector.pdd.service.A11yHelper
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class AcceptedBaselineNoSkuRuntimeTest {
    @Test
    fun taskEngineRegistryPddDetailBehaviorKeepsSkuInteractionDisabled() = runBlocking {
        val actions = SpyDetailActions()
        val links = FakeDetailLinks()
        val collector = CollectorRegistry.require("pinduoduo") as PddCollector
        val session = collector.createDetailTestSession(actions, links)

        val result = collectDetailThroughRegistry(
            "pinduoduo",
            session,
            DetailCollectionRequest("感冒灵", "default_top_1", 0) {},
        )

        assertNotNull(result.product)
        assertTrue(result.quality?.accepted == true)
        assertEquals(0, actions.purchaseEntryActions)
        assertEquals(0, actions.openSkuPanelActions)
        assertEquals(0, actions.combinationSelectionActions)
        assertEquals(0, result.raw.sources.count { it.type == "SKU_PANEL" })
        assertTrue(result.raw.sources.any { it.type == "DETAIL" })
        assertTrue(result.raw.sources.all { it.schemaHint == "pdd-a11y-v1" })
        assertFalse(actions.calls.any { call ->
            call.contains("purchase", ignoreCase = true) ||
                call.contains("sku", ignoreCase = true) ||
                call.contains("combination", ignoreCase = true)
        })

        val legacyRead = collector.normalizeForCompatibility(
            DetailParseRequest(
                pageText = actions.page,
                keyword = "感冒灵",
                pickTag = "default_top_1",
                itemIdHint = "12345678",
                skuPanelText = """
                    包装选择
                    1盒 ¥9.90
                    2盒 ¥18.00
                """.trimIndent(),
            ),
        )
        assertEquals(2, JSONArray(legacyRead.skuPrices).length())
    }

    @Test
    fun genericRawSourceDoesNotInheritPddSchema() {
        val generic = RawSource("DETAIL", "generic-detail", 1L, payload = "raw")
        assertEquals(null, generic.schemaHint)
    }

    @Test
    fun sourceScanRemainsAuxiliaryDefenseOnly() {
        val actions = File("src/main/java/com/collector/pdd/engine/PddActions.kt").readText()
        assertFalse(actions.contains("GenericSkuContract"))
        assertFalse(actions.contains("readSkuPricesByClickingCombinations"))
        assertFalse(actions.contains("findSkuPurchaseEntryButtons"))
    }
}

private class SpyDetailActions : PddDetailActions {
    val calls = mutableListOf<String>()
    var purchaseEntryActions = 0
    var openSkuPanelActions = 0
    var combinationSelectionActions = 0
    val page = """
        商品详情
        测试牌 感冒灵颗粒 正品家庭装
        ￥9.90
        已拼100件
        goods_id=12345678
        立即购买
    """.trimIndent()

    private fun called(name: String) {
        calls += name
    }

    override fun readPageText(): String {
        called("read_detail")
        return page
    }

    override suspend fun openCardAt(index: Int): Pair<Boolean, ListCardMeta> {
        called("open_card")
        return true to ListCardMeta(listPrice = 9.90, itemId = "12345678", titleHint = "测试牌 感冒灵颗粒")
    }

    override suspend fun tryProbeMainImage(goodsId: String, alreadyAtTop: Boolean): List<String> {
        called("probe_media")
        return emptyList()
    }

    override suspend fun ensureOnGoodsDetail(openIndex: Int): Boolean {
        called("ensure_detail")
        return true
    }

    override suspend fun randomBridgeHuman(scene: String) = called("human_bridge")

    override suspend fun openAndReadProductParams(): String {
        called("read_params")
        return "品牌\n测试牌"
    }

    override suspend fun openAndReadSkuPrices(): String {
        called("open_sku_purchase_panel_and_select_combination")
        purchaseEntryActions += 1
        openSkuPanelActions += 1
        combinationSelectionActions += 1
        return ""
    }

    override suspend fun peekShopSalesText(): String {
        called("read_shop_sales")
        return ""
    }

    override suspend fun maybeDetailHumanGestures() = called("detail_human")

    override fun looksLikeGoodsDetail(): Boolean {
        called("is_detail")
        return true
    }

    override suspend fun tryCaptureShareLink(): PddActions.ShareCapture {
        called("capture_share")
        return PddActions.ShareCapture(goodsId = "12345678")
    }

    override fun harvestPage(): A11yHelper.Harvest {
        called("harvest_detail")
        return A11yHelper.Harvest(goodsId = "12345678")
    }

    override suspend fun pause(minMs: Double, maxMs: Double) = called("pause")
}

private class FakeDetailLinks : PddDetailLinks {
    override fun extractProductId(value: String) = "12345678"
    override fun buildProductUrl(platformProductId: String) =
        "https://mobile.yangkeduo.com/goods.html?goods_id=$platformProductId"
    override fun extractProductUrls(value: String) = emptyList<String>()
    override suspend fun expandShareLink(value: String) = PddResolvedLink(platformProductId = "12345678")
    override suspend fun resolveLink(
        rawShare: String,
        hintUrl: String,
        hintProductId: String,
        expectTokens: List<String>,
    ) = PddResolvedLink(
        platformProductId = "12345678",
        itemUrl = buildProductUrl("12345678"),
    )
    override fun isProductImageUrl(value: String) = false
}
