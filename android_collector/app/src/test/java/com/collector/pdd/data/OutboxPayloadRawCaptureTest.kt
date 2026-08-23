package com.collector.pdd.data

import com.collector.pdd.collector.RawSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class OutboxPayloadRawCaptureTest {
    @Test
    fun rawSourcesAreGroupedAndCredentialsAreFiltered() {
        val product = ProductEntity(
            itemId = "972503815108",
            sellName = "真实商品",
            displayPrice = 44.37,
            parserVersion = "pdd-android-1",
        )
        val payload = OutboxPayload.product(
            product,
            "pinduoduo",
            captureId = "cap-1123-12345678",
            rawSources = listOf(
                RawSource("DETAIL", "goods-detail", 1L, payload = "商品详情\nAuthorization: secret\n短信通知：个人消息"),
                RawSource("SKU", "sku-panel", 2L, payload = "规格 一件 ￥44.37"),
            ),
        )
        val capture = payload.getJSONObject("raw_capture")
        assertEquals("cap-1123-12345678", capture.getString("capture_id"))
        assertEquals(2, capture.getJSONArray("sources").length())
        val detail = capture.getJSONArray("sources").getJSONObject(0).getString("payload")
        assertFalse(detail.contains("secret"))
        assertFalse(detail.contains("个人消息"))
        assertTrue(detail.contains("redacted-sensitive-line"))
    }

    @Test
    fun missingObservationIsJsonNullButObservedZeroRemainsZero() {
        val missing = ProductEntity(
            itemId = "1",
            sellName = "商品",
            commentNum = 0,
            skuPrices = "[]",
            fieldSources = """{"comment_num":"none","sku":"none"}""",
        )
        val missingPayload = OutboxPayload.product(missing, "pinduoduo")
        assertTrue(missingPayload.isNull("comment_num"))
        assertTrue(missingPayload.isNull("sku_prices"))

        val zero = missing.copy(fieldSources = """{"comment_num":"detail_text","sku":"sku_panel"}""")
        val zeroPayload = OutboxPayload.product(zero, "pinduoduo")
        assertEquals(0, zeroPayload.getInt("comment_num"))
        assertEquals("[]", zeroPayload.getString("sku_prices"))
    }

    @Test
    fun jsonRawSourceRemainsValidAfterSensitiveUiLinesAreFiltered() {
        val source = RawSource(
            "SEARCH",
            "search-card:0",
            1L,
            contentType = "application/json",
            payload = JSONObject()
                .put("keyword", "品牌洗发水")
                .put("page_text", "商品列表\n短信通知：个人消息\n¥29.90")
                .put("authorization", "secret")
                .toString(),
        )
        val sanitized = JSONObject(OutboxPayload.sanitizeSourcePayload(source))
        assertEquals("品牌洗发水", sanitized.getString("keyword"))
        assertTrue(sanitized.getString("page_text").contains("¥29.90"))
        assertFalse(sanitized.getString("page_text").contains("个人消息"))
        assertEquals("<redacted>", sanitized.getString("authorization"))
    }
}
