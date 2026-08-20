package com.collector.pdd.parser

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class RawCaptureReplayTest {
    @Test
    fun replayExistingRawCaptureWithoutNetwork() {
        val capturePaths = System.getenv("PDD_CAPTURE_DIRS").orEmpty().split(File.pathSeparator)
            .filter(String::isNotBlank)
        assumeTrue("PDD_CAPTURE_DIRS is required for explicit replay", capturePaths.isNotEmpty())
        val results = org.json.JSONArray()
        capturePaths.forEach { capturePath ->
        val captureDir = File(capturePath)
        val manifest = JSONObject(File(captureDir, "manifest.json").readText(Charsets.UTF_8))
        val sources = manifest.getJSONArray("sources")
        fun source(type: String): File? = (0 until sources.length())
            .map { sources.getJSONObject(it) }
            .firstOrNull { it.getString("type") == type }
            ?.getString("storage_reference")
            ?.let { File(captureDir, it) }

	        val search = runCatching { JSONObject(source("SEARCH")!!.readText(Charsets.UTF_8)) }
	            .getOrDefault(JSONObject())
	        val uploadRef = manifest.getJSONObject("product_upload").getString("storage_reference")
	        val upload = JSONObject(File(captureDir, uploadRef).readText(Charsets.UTF_8))
	        val detail = source("DETAIL")!!.readText(Charsets.UTF_8)
        val sku = source("SKU")?.readText(Charsets.UTF_8).orEmpty()
        val parsed = DetailReader.parse(
            pageText = detail,
	            keyword = search.optString("keyword").ifBlank { upload.optString("keyword") },
            pickTag = "offline_replay",
	            listPrice = search.optDouble("list_price").takeUnless(Double::isNaN)
	                ?: upload.optDouble("display_price").takeUnless(Double::isNaN),
	            itemIdHint = search.optString("item_id_hint").ifBlank { manifest.getString("platform_product_id") },
            skuPanelText = sku,
        )
        val checked = ProductQualityGate.apply(detail, parsed).first

        if (manifest.getString("capture_id") == "cap-1124-24dc79be-aa59-4cda-a182-a01abba58a7c") {
            assertEquals("【TOCI】水杨酸洗发水控油蓬松清爽去屑止痒柔顺修护持久留香洗头膏", checked.sellName)
            assertEquals("TOCI山茶花特护控油洗发水", checked.productName)
            assertFalse(checked.manufacturer == "名称")
            assertFalse(checked.spec == "类型")
            assertEquals("", checked.skuPricesText)
        }
        assertEquals("pdd-android-2", checked.parserVersion)
        results.put(JSONObject()
            .put("capture_id", manifest.getString("capture_id"))
            .put("platform_code", "pinduoduo")
            .put("keyword", checked.keyword)
            .put("item_id", checked.itemId)
            .put("sell_name", checked.sellName)
            .put("product_name", checked.productName)
            .put("brand", checked.brand)
            .put("shop_name", checked.shopName)
            .put("shop_id", checked.shopId)
            .put("price", checked.price ?: JSONObject.NULL)
            .put("display_price", checked.displayPrice ?: JSONObject.NULL)
            .put("group_price", checked.groupPrice ?: JSONObject.NULL)
            .put("deal_price", checked.dealPrice ?: JSONObject.NULL)
            .put("original_price", checked.originalPrice ?: JSONObject.NULL)
            .put("sales_num", checked.salesNum ?: JSONObject.NULL)
            .put("shop_sales_num", checked.shopSalesNum ?: JSONObject.NULL)
            .put("comment_num", if (JSONObject(checked.fieldSources).getString("comment_num") == "none") JSONObject.NULL else checked.commentNum)
            .put("manufacturer", checked.manufacturer)
            .put("spec", checked.spec)
            .put("sku_prices_text", checked.skuPricesText.ifBlank { JSONObject.NULL })
            .put("sku_prices", checked.skuPrices.takeUnless { it == "[]" } ?: JSONObject.NULL)
            .put("dosage_form", checked.dosageForm)
            .put("approval_no", checked.approvalNo)
            .put("expiry", checked.expiry)
            .put("category", checked.category)
            .put("coupon_info", checked.couponInfo)
            .put("item_url", checked.itemUrl)
            .put("pick_tag", checked.pickTag)
            .put("spec_list", checked.specList)
            .put("field_sources", JSONObject(checked.fieldSources))
            .put("parse_status", checked.parseStatus)
            .put("page_status", checked.pageStatus)
            .put("quality_status", checked.qualityStatus)
            .put("parser_version", checked.parserVersion)
            .put("quality_rules_version", checked.qualityRulesVersion))
        }
        val output = JSONObject().put("network_access", false).put("results", results)
        System.getenv("PDD_REPLAY_OUTPUT").orEmpty().takeIf(String::isNotBlank)?.let {
            File(it).writeText(output.toString(2), Charsets.UTF_8)
        }
        println(output.toString())
    }
}
