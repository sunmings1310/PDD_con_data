package com.collector.pdd.data

import com.collector.pdd.BuildConfig
import com.collector.pdd.collector.RawSource
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

object OutboxPayload {
    private val sensitiveKey = Regex(
        "(?i)^(?:cookie|set-cookie|authorization|proxy-authorization|session[_-]?token|access[_-]?token|refresh[_-]?token|device[_-]?(?:key|credential)|password)$",
    )
    private val sensitiveLine = Regex(
        "(?i)^(?:cookie|set-cookie|authorization|proxy-authorization|session[_-]?token|access[_-]?token|refresh[_-]?token|device[_-]?(?:key|credential)|password)\\s*[:=].*$",
        setOf(RegexOption.MULTILINE),
    )
    private val sensitiveQuery = Regex("(?i)([?&](?:token|access_token|auth|authorization|session|device_key)=)[^&#\\s]+")
    private val personalLine = Regex(
        "(?im)^(?:.*1\\d{2}\\*{4}\\d{4}.*|.*(?:\\d+栋|\\d+幢|\\d+单元|\\d+室|\\d+号).*|.*(?:微信|支付宝|银行卡)支付.*)$",
    )
    private val unrelatedSystemUiLine = Regex(
        "(?im)^(?:.*通知[:：].*|.*(?:短信同步|通话记录同步|设备备份失败).*|.*com\\.android\\.systemui:id/.*|" +
            ".*联机工具通知.*|.*手机信号.*|.*电池电量.*|蓝牙开启。?|(?:上午|下午|晚上)?\\d{1,2}:\\d{2}|[345]G)\\s*$",
    )

    internal fun sanitizeRaw(value: String): String = value
        .replace(sensitiveLine, "<redacted-sensitive-line>")
        .replace(sensitiveQuery, "$1<redacted>")
        .replace(personalLine, "<redacted-personal-line>")
        .replace(unrelatedSystemUiLine, "")
        .lines().joinToString("\n") { it.trimEnd() }
        .replace(Regex("\n{3,}"), "\n\n")

    private fun sanitizeJsonValue(value: Any?): Any? = when (value) {
        is JSONObject -> JSONObject().also { output ->
            value.keys().forEach { key ->
                output.put(key, if (sensitiveKey.matches(key)) "<redacted>" else sanitizeJsonValue(value.get(key)))
            }
        }
        is JSONArray -> JSONArray().also { output ->
            for (index in 0 until value.length()) output.put(sanitizeJsonValue(value.get(index)))
        }
        is String -> sanitizeRaw(value)
        else -> value
    }

    internal fun sanitizeSourcePayload(source: RawSource): String {
        if (!source.contentType.contains("json", ignoreCase = true)) return sanitizeRaw(source.payload)
        val raw = source.payload.trim()
        return runCatching {
            val parsed: Any = if (raw.startsWith("[")) JSONArray(raw) else JSONObject(raw)
            sanitizeJsonValue(parsed).toString()
        }.getOrElse { sanitizeRaw(source.payload) }
    }

    fun product(
        product: ProductEntity,
        platformCode: String,
        captureId: String? = null,
        rawSources: List<RawSource> = emptyList(),
    ): JSONObject {
        val fieldSources = runCatching { JSONObject(product.fieldSources) }.getOrElse { JSONObject() }
        val commentObserved = fieldSources.optString("comment_num") != "none"
        val skuObserved = fieldSources.optString("sku") == "sku_panel"
        val urls = JSONArray()
        val files = JSONArray()
        product.mainImages.split("|").map { it.trim() }.filter { it.isNotEmpty() }.forEach { value ->
            when {
                value.startsWith("http://") || value.startsWith("https://") -> urls.put(value)
                value.startsWith("file://") && files.length() < 12 -> files.put(value.removePrefix("file://"))
                (File(value).exists() || value.startsWith("/")) && files.length() < 12 -> files.put(value)
            }
        }
        val result = JSONObject()
            .put("platform_code", platformCode)
            .put("keyword", product.keyword)
            .put("item_id", product.itemId)
            .put("sell_name", product.sellName)
            .put("product_name", product.productName)
            .put("brand", product.brand)
            .put("shop_name", product.shopName)
            .put("shop_id", product.shopId)
            .put("spec", product.spec)
            .put("sku_prices_text", if (skuObserved) product.skuPricesText else JSONObject.NULL)
            .put("sku_prices", if (skuObserved) product.skuPrices else JSONObject.NULL)
            .put("dosage_form", product.dosageForm)
            .put("approval_no", product.approvalNo)
            .put("manufacturer", product.manufacturer)
            .put("expiry", product.expiry)
            .put("category", product.category)
            .put("coupon_info", product.couponInfo)
            .put("item_url", product.itemUrl)
            .put("pick_tag", product.pickTag)
            .put("spec_list", product.specList)
            .put("sales_num", product.salesNum ?: JSONObject.NULL)
            .put("shop_sales_num", product.shopSalesNum ?: JSONObject.NULL)
            .put("comment_num", if (commentObserved) product.commentNum else JSONObject.NULL)
            .put("price", product.price ?: JSONObject.NULL)
            .put("display_price", product.displayPrice ?: JSONObject.NULL)
            .put("group_price", product.groupPrice ?: JSONObject.NULL)
            .put("deal_price", product.dealPrice ?: JSONObject.NULL)
            .put("original_price", product.originalPrice ?: JSONObject.NULL)
            .put("image_urls", urls)
            .put("local_image_paths", files)
            .put("local_image_count", files.length())
            .put("parse_status", product.parseStatus)
            .put("page_status", product.pageStatus)
            .put("quality_status", product.qualityStatus)
            .put("field_sources", fieldSources)
            .put("parser_version", product.parserVersion)
            .put("quality_rules_version", product.qualityRulesVersion)
        if (!captureId.isNullOrBlank() && rawSources.isNotEmpty()) {
            val sources = JSONArray()
            rawSources.forEach { source ->
                sources.put(JSONObject()
                    .put("type", source.type)
                    .put("source_identifier", source.sourceIdentifier)
                    .put("captured_at_epoch_ms", source.capturedAtEpochMs)
                    .put("content_type", source.contentType)
                    .put("schema_hint", source.schemaHint)
                    .put("payload", sanitizeSourcePayload(source)))
            }
            result.put("raw_capture", JSONObject()
                .put("capture_id", captureId)
                .put("platform", platformCode)
                .put("platform_product_id", product.itemId)
                .put("collected_at_epoch_ms", System.currentTimeMillis())
                .put("collector_version", BuildConfig.VERSION_NAME)
                .put("parser_version", product.parserVersion)
                .put("sources", sources))
        }
        return result
    }

    fun localImageCount(payload: JSONObject): Int = payload.optJSONArray("local_image_paths")?.length() ?: 0
}
