package com.collector.pdd.parser

import com.collector.pdd.data.ProductEntity
import org.json.JSONObject

object ProductQualityGate {
    const val PARSER_VERSION = "pdd-android-2"
    const val QUALITY_RULES_VERSION = "phase3-1"

    data class Decision(
        val pageStatus: String,
        val parseStatus: String,
        val qualityStatus: String,
        val missingFields: List<String> = emptyList(),
        val warnings: List<String> = emptyList(),
    ) {
        val accepted: Boolean
            get() = pageStatus == "product" && qualityStatus != "quarantined"
    }

    fun classifyPage(pageText: String): String {
        val compact = pageText.replace("\\s+".toRegex(), "")
        if (compact.isBlank()) return "malformed"
        if (listOf("登录后继续", "手机号登录", "手机登录", "验证码登录", "请先登录").any(compact::contains)) {
            return "login_required"
        }
        if (listOf("完成验证", "安全验证", "拖动滑块", "操作频繁", "验证后继续").any(compact::contains)) {
            return "challenge"
        }
        if (listOf("系统繁忙", "访问人数较多", "网络繁忙", "稍后再试").any(compact::contains)) {
            return "busy"
        }
        if (listOf("商品已售罄", "商品已下架", "已下架").any(compact::contains)) return "sold_out"
        if (listOf("商品不存在", "商品已失效", "页面不存在", "找不到该商品").any(compact::contains)) {
            return "not_found"
        }
        val markers = listOf("商品详情", "立即购买", "免拼购买", "单独购买", "去拼单", "拼单价", "已拼")
        return if (markers.count(compact::contains) >= 2) "product" else "malformed"
    }

    fun evaluate(pageText: String, product: ProductEntity): Decision {
        val pageStatus = classifyPage(pageText)
        if (pageStatus != "product") {
            return Decision(pageStatus, "not_attempted", "quarantined")
        }
        val missing = mutableListOf<String>()
        if (product.itemId.isBlank()) missing += "item_id"
        if (product.sellName.isBlank() && product.productName.isBlank()) missing += "name"
        if (product.itemUrl.isBlank() || !product.itemUrl.contains("goods_id=${product.itemId}")) missing += "item_url"
        if (listOf(product.price, product.displayPrice, product.groupPrice, product.dealPrice).none { it != null && it > 0.0 }) {
            missing += "price"
        }
        if (missing.isNotEmpty()) return Decision(pageStatus, "failed", "quarantined", missing)
        val warnings = buildList {
            if ((product.skuPrices.isBlank() || product.skuPrices == "[]") && product.skuPricesText.isBlank()) add("sku_missing")
            if (product.salesNum == null) add("sales_missing")
        }
        return Decision(
            pageStatus,
            if (warnings.isEmpty()) "success" else "partial",
            if (warnings.isEmpty()) "passed" else "warning",
            warnings = warnings,
        )
    }

    fun apply(pageText: String, product: ProductEntity): Pair<ProductEntity, Decision> {
        val decision = evaluate(pageText, product)
        val sources = runCatching { JSONObject(product.fieldSources) }.getOrElse { JSONObject() }
        if (!sources.has("item_id")) sources.put("item_id", "detail_or_share")
        if (!sources.has("item_url")) sources.put("item_url", "share_or_derived")
        if (!sources.has("name")) sources.put("name", "detail_text")
        if (!sources.has("price")) sources.put("price", "list_or_detail")
        return product.copy(
            pageStatus = decision.pageStatus,
            parseStatus = decision.parseStatus,
            qualityStatus = decision.qualityStatus,
            fieldSources = sources.toString(),
            parserVersion = PARSER_VERSION,
            qualityRulesVersion = QUALITY_RULES_VERSION,
        ) to decision
    }
}
