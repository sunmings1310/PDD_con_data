package com.collector.pdd.parser

import com.collector.pdd.data.ProductEntity
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

/**
 * Detail page text parser aligned with desktop detail_parser.
 * Supports bottom bar / subsidy price, product-params modal, and UI junk filters.
 */
object DetailReader {

    private val timeFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")

    private val knownLabels = listOf(
        "\u54c1\u724c", "\u53d1\u8d27\u5730", "\u836f\u54c1\u901a\u7528\u540d", "\u901a\u7528\u540d\u79f0", "\u5546\u54c1\u540d\u79f0",
        "\u836f\u54c1\u89c4\u683c", "\u89c4\u683c", "\u4ea7\u54c1\u5242\u578b", "\u5242\u578b", "\u4f7f\u7528\u5242\u91cf",
        "\u6279\u51c6\u6587\u53f7", "\u56fd\u836f\u51c6\u5b57", "\u836f\u54c1\u5206\u7c7b", "\u6709\u6548\u671f", "\u4fdd\u8d28\u671f",
        "\u836f\u54c1\u7c7b\u522b", "\u7c7b\u76ee", "\u751f\u4ea7\u4f01\u4e1a", "\u751f\u4ea7\u5382\u5bb6", "\u7528\u6cd5",
        "\u4e0a\u5e02\u8bb8\u53ef\u6301\u6709\u4eba", "\u5236\u9020\u5546", "\u67e5\u770b\u5168\u90e8", "\u5546\u54c1\u53c2\u6570", "\u5546\u54c1\u8be6\u60c5",
    )

    private val junkValues = setOf(
        "\u7b5b\u9009", "\u7efc\u5408", "\u9500\u91cf", "\u4ef7\u683c", "\u54c1\u724c", "\u5546\u54c1", "\u5206\u4eab", "\u5ba2\u670d",
        "\u6536\u85cf", "\u5e97\u94fa", "\u8fdb\u5e97", "\u9876\u90e8", "\u767e\u4ebf\u8865\u8d34", "\u6b63\u54c1\u4fdd\u969c",
        "\u54c1\u724c\u6b63\u54c1", "\u514d\u62fc\u8d2d\u4e70", "\u5355\u72ec\u8d2d\u4e70", "\u67e5\u770b\u5168\u90e8", "\u5546\u54c1\u53c2\u6570",
        "\u5546\u54c1\u8be6\u60c5", "\u5e97\u94fa\u8d44\u8d28", "\u5b98\u65b9\u8865\u8d34", "\u60ca\u559c\u7279\u4ef7", "\u54c1\u8d28\u4fdd\u969c",
        "\u552e\u540e\u65e0\u5fe7", "\u62fc\u591a\u591a", "\u767b\u5f55", "\u5df2\u62fc", "\u603b\u552e",
    )

    fun parse(
        pageText: String,
        keyword: String,
        pickTag: String,
        listPrice: Double? = null,
        itemIdHint: String = "",
        shopIdHint: String = "",
        imageHints: List<String> = emptyList(),
        urlHint: String = "",
        skuPanelText: String = "",
    ): ProductEntity {
        val text = pageText.replace("\u200b", "")
        val paramsSection = extractParamsSection(text)
        val prefer = if (paramsSection.isNotBlank()) "$paramsSection\n$text" else text
        val compact = prefer.replace("\\s+".toRegex(), "")

        var brand = cleanField(labelValue(prefer, listOf("\u54c1\u724c")))
        var productName = cleanField(
            labelValue(prefer, listOf("\u836f\u54c1\u901a\u7528\u540d", "\u901a\u7528\u540d\u79f0", "\u5546\u54c1\u540d\u79f0")),
        )
        var spec = cleanField(labelValue(prefer, listOf("\u836f\u54c1\u89c4\u683c", "\u89c4\u683c")))
        val dosage = cleanField(labelValue(prefer, listOf("\u4ea7\u54c1\u5242\u578b", "\u5242\u578b")))
        val expiry = cleanField(labelValue(prefer, listOf("\u6709\u6548\u671f", "\u4fdd\u8d28\u671f")))
        val category = cleanField(
            labelValue(prefer, listOf("\u836f\u54c1\u7c7b\u522b", "\u836f\u54c1\u5206\u7c7b", "\u7c7b\u76ee", "\u6240\u5c5e\u7c7b\u76ee")),
        )
        val manufacturer = cleanField(
            labelValue(
                prefer,
                listOf("\u751f\u4ea7\u4f01\u4e1a", "\u751f\u4ea7\u5382\u5bb6", "\u4e0a\u5e02\u8bb8\u53ef\u6301\u6709\u4eba", "\u5236\u9020\u5546", "\u5382\u5bb6"),
            ),
        )
        val approval = cleanApproval(
            Regex("""\u56fd\u836f\u51c6\u5b57[A-Za-z]?\u5b57?[A-Za-z]?\d+""").find(prefer)?.value.orEmpty()
                .ifBlank { labelValue(prefer, listOf("\u6279\u51c6\u6587\u53f7", "\u56fd\u836f\u51c6\u5b57")) },
        )

        if (brand.isBlank()) {
            brand = cleanField(Regex("""\u3014([^\u3015]{1,20})\u3015""").find(prefer)?.groupValues?.getOrNull(1).orEmpty())
        }
        if (spec.isBlank()) spec = extractSpec(prefer)

        val sellName = buildSellName(prefer, brand, productName, spec, keyword)
        if (productName.isBlank()) productName = sellName

        val shopName = extractShopName(prefer)

        val shopId = shopIdHint.ifBlank {
            Regex("""(?:mall[_]?id|mallId|shop[_]?id|shopId)[=:\\\"'/]+(\d{5,})""", RegexOption.IGNORE_CASE)
                .find(compact)?.groupValues?.getOrNull(1).orEmpty()
        }

        val prices = extractBottomBarPrices(text, compact)
        val displayPrice = prices.display
        val groupPrice = prices.group
        val dealPrice = prices.deal
        val originalPrice = Regex("""\u5373\u5c06\u6062\u590d\s*(\d+(?:\.\d{1,2})?)\s*\u5143""")
            .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: Regex("""(?:\u539f\u4ef7|\u5212\u7ebf\u4ef7)[^0-9\u00a5\uffe5]{0,8}[\u00a5\uffe5]?\s*(\d+(?:\.\d{1,2})?)""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()

        val productSales = Regex("""\u603b\u552e\s*([\d.]+[\u4e07]?\+?)""")
            .find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u8fd1\s*30\s*\u5929\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""^\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""", RegexOption.MULTILINE).find(text)?.groupValues?.getOrNull(1)
            ?: run {
                Regex("""(.{0,4})\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").findAll(text)
                    .firstOrNull { !Regex("""\u672c\u5e97|\u5e97\u94fa|\u5168\u5e97""").containsMatchIn(it.groupValues[1]) }
                    ?.groupValues?.getOrNull(2)
            }
        val shopSales = Regex("""(?:\u8fd1\u671f)?\u672c\u5e97\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u5e97\u94fa\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u5168\u5e97\u603b\u552e\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u5168\u5e97\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u672c\u5e97\u603b\u552e\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u5e97\u94fa[^\n]{0,24}\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            ?: Regex("""\u8fdb\u5e97[^\n]{0,30}\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""").find(text)?.groupValues?.getOrNull(1)
            // 店铺条常见：「旗舰店 … 已拼2.7万」
            ?: Regex("""(?:\u65d7\u8230\u5e97|\u4e13\u8425\u5e97|\u5927\u836f\u623f|\u836f\u623f)[^\n]{0,40}\u5df2\u62fc\s*([\d.]+[\u4e07]?\+?)""")
                .find(text)?.groupValues?.getOrNull(1)

        val commentNum = Regex("""(?:\u8bc4\u4ef7|\u5546\u54c1\u8bc4\u4ef7|\u5168\u90e8\u8bc4\u4ef7|\u6240\u5c5e\u5e97\u94fa\u8bc4\u4ef7)\s*[（(]?\s*([\d.]+[\u4e07]?\+?)""")
            .find(text)?.groupValues?.getOrNull(1)
            ?.let { parseSalesNum(it) } ?: 0

        val couponInfo = extractCoupon(text)
        val skuText = buildSkuFromPanel(skuPanelText)
            .ifBlank { buildSkuPricesText(text, compact, displayPrice) }

        val itemId = itemIdHint.ifBlank {
            Regex("""goods_id[=:\\\"'/]+(\d{8,})""", RegexOption.IGNORE_CASE)
                .find(compact)?.groupValues?.getOrNull(1).orEmpty()
                .ifBlank {
                    Regex("""goods\.html\?[^ \n]*goods_id=(\d{8,})""", RegexOption.IGNORE_CASE)
                        .find(compact)?.groupValues?.getOrNull(1).orEmpty()
                }
        }
        val itemUrl = when {
            urlHint.contains("goods_id=") || urlHint.contains("goods.html") || urlHint.contains("yangkeduo") ->
                normalizeGoodsUrl(urlHint, itemId)
            itemId.isNotBlank() -> "https://mobile.yangkeduo.com/goods.html?goods_id=$itemId"
            else -> urlHint.trim()
        }

        val images = extractImages(text, imageHints)

        val specList = buildSpecListJson(
            linkedMapOf(
                "\u54c1\u724c" to brand,
                "\u53d1\u8d27\u5730" to cleanField(labelValue(prefer, listOf("\u53d1\u8d27\u5730"))),
                "\u89c4\u683c" to spec,
                "\u5242\u578b" to dosage,
                "\u6279\u51c6\u6587\u53f7" to approval,
                "\u751f\u4ea7\u4f01\u4e1a" to manufacturer,
                "\u6709\u6548\u671f" to expiry,
                "\u7c7b\u76ee" to category,
                "\u7528\u6cd5" to cleanField(labelValue(prefer, listOf("\u7528\u6cd5"))),
            )
        )

        return ProductEntity(
            keyword = keyword,
            itemId = itemId,
            sellName = sellName,
            productName = productName,
            brand = brand,
            shopName = shopName,
            shopId = shopId,
            price = listPrice,
            displayPrice = displayPrice,
            groupPrice = groupPrice,
            dealPrice = dealPrice,
            originalPrice = originalPrice,
            salesNum = parseSalesNum(productSales),
            shopSalesNum = parseSalesNum(shopSales),
            commentNum = commentNum,
            spec = spec,
            skuPricesText = skuText,
            skuPrices = skuJsonFromText(skuText),
            dosageForm = dosage,
            approvalNo = approval,
            manufacturer = manufacturer,
            expiry = expiry,
            category = category,
            couponInfo = couponInfo,
            mainImages = images.joinToString("|"),
            itemUrl = itemUrl,
            pickTag = pickTag,
            specList = specList,
            updateTime = LocalDateTime.now().format(timeFmt),
        )
    }

    data class BottomPrices(
        val display: Double? = null,
        val group: Double? = null,
        val deal: Double? = null,
    )

    fun extractBottomBarPrices(text: String, compact: String = text.replace("\\s+".toRegex(), "")): BottomPrices {
        val hasSoloBtn = text.contains("\u5355\u72ec\u8d2d\u4e70") || compact.contains("\u5355\u72ec\u8d2d\u4e70")
        val hasLaunchGroup = text.contains("\u53d1\u8d77\u62fc\u5355") || compact.contains("\u53d1\u8d77\u62fc\u5355")
        val hasMianPin = text.contains("\u514d\u62fc\u8d2d\u4e70") || compact.contains("\u514d\u62fc\u8d2d\u4e70")
        val hasFuzhen = text.contains("去复诊开药") || text.contains("复诊开药") ||
            compact.contains("去复诊开药") || compact.contains("复诊开药")
        // 底栏只有「免拼购买」一个主按钮时：价格算单独购买价，不算拼单价
        val singleMianPinBar = hasMianPin && !hasSoloBtn && !hasLaunchGroup
        // 「去复诊开药」处方药：页面主价即单独购买价（无拼单/免拼底栏）
        val fuzhenBar = hasFuzhen && !hasSoloBtn && !hasMianPin && !hasLaunchGroup

        val mianPinPrice = Regex("""[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)\s*[^\n]{0,16}\u514d\u62fc\u8d2d\u4e70""")
            .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: Regex("""\u514d\u62fc\u8d2d\u4e70[^\n]{0,12}[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: Regex("""\u5feb\u8981\u62a2\u5149[^\n]{0,8}[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()

        val subsidy = Regex("""\u8865\u8d34\u4ef7[^\u00a5\uffe5\n]{0,24}[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
            .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()

        val dealExplicit = Regex("""[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)\s*\u5355\u72ec(?:\u8d2d\u4e70|\u4e70)""")
            .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: Regex("""\u5355\u72ec(?:\u8d2d\u4e70|\u4e70)[^0-9\u00a5\uffe5]{0,12}[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()

        val group = when {
            singleMianPinBar || fuzhenBar -> null
            else -> subsidy
                ?: Regex("""\u9996\u4ef6\s*[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                    .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
                ?: Regex("""[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)\s*(?:\u514d\u62fc\u8d2d\u4e70|\u53d1\u8d77\u62fc\u5355|\u62fc\u5355\u4ef7)""")
                    .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
                ?: Regex("""(?:\u62fc\u5355\u4ef7|\u53d1\u8d77\u62fc\u5355)[^0-9\u00a5\uffe5]{0,12}[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                    .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
                ?: if (hasSoloBtn) mianPinPrice else null
        }

        val limitPrice = Regex("""限量价\s*[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
            .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: Regex("""[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)\s*[^\n]{0,12}限量价""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()

        val display = subsidy
            ?: dealExplicit
            ?: if (singleMianPinBar) mianPinPrice else null
            ?: group
            ?: mianPinPrice
            ?: limitPrice
            ?: Regex("""\u9650\u91cf\u4f4e\u4ef7\s*[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
                .find(text)?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            ?: fallbackPrice(text, compact)

        // 单独购买价识别不出时：用详情价（用户约定）
        val deal = dealExplicit
            ?: if (singleMianPinBar) mianPinPrice else null
            ?: if (fuzhenBar) display else null
            ?: display

        return BottomPrices(display = display, group = group, deal = deal)
    }

    fun parseSalesNum(value: String?): Int {
        if (value.isNullOrBlank()) return 0
        val t = value.replace(",", "").replace("+", "")
        if (t.contains("\u4e07")) {
            val m = Regex("""([\d.]+)""").find(t) ?: return 0
            return (m.groupValues[1].toDouble() * 10000).roundToInt()
        }
        return Regex("""(\d+)""").find(t)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: 0
    }

    private fun extractParamsSection(text: String): String {
        val marker = "---\u5546\u54c1\u53c2\u6570---"
        val idx = text.indexOf(marker)
        if (idx >= 0) return text.substring(idx)
        val i2 = text.indexOf("\u5546\u54c1\u53c2\u6570")
        if (i2 >= 0) return text.substring(i2, minOf(text.length, i2 + 2500))
        val i3 = text.indexOf("\u836f\u54c1\u901a\u7528\u540d")
        if (i3 >= 0) return text.substring(maxOf(0, i3 - 40), minOf(text.length, i3 + 1200))
        return ""
    }

    private fun cleanField(raw: String): String {
        val v = raw.trim()
        if (v.isBlank()) return ""
        if (junkValues.contains(v)) return ""
        return v
    }

    private fun buildSellName(
        text: String,
        brand: String,
        productName: String,
        spec: String,
        keyword: String,
    ): String {
        val composed = listOf(brand, productName, spec).filter { it.isNotBlank() }.joinToString(" ").trim()
        if (composed.length >= 4) return composed.take(120)
        val fromPage = extractSellName(text)
        if (fromPage.isNotBlank() && !junkValues.contains(fromPage)) return fromPage
        return keyword.take(80)
    }

    private fun extractCoupon(text: String): String {
        val hits = Regex(
            """\u6ee1\d+\u51cf\d+|\u5238\u540e[\u00a5\uffe5]?\d+(?:\.\d{1,2})?|\u7acb\u51cf\d+(?:\.\d{1,2})?|\u4f18\u60e0\u5238|\u9886\u5238|\u653f\u5e9c\u8865\u8d34|\u56fd\u5bb6\u8865\u8d34|\u76f4\u63a5\u62fc\u6210|\u5b98\u65b9\u8865\u8d34\d+(?:\.\d+)?\u5143|\u767e\u4ebf\u8865\u8d34"""
        ).findAll(text).map { it.value.trim() }.distinct().take(5).toList()
        return hits.joinToString("\uff1b")
    }

    private fun extractImages(text: String, hints: List<String>): List<String> {
        val found = mutableListOf<String>()
        hints.forEach { if (it.isNotBlank()) found.add(it.trim()) }
        Regex(
            """https?://[^\s"'<>\]]*(?:pddpic|mms-material|mms-goods|img\.pddpic)[^\s"'<>\]]*\.(?:jpg|jpeg|png|webp)[^\s"'<>\]]*""",
            RegexOption.IGNORE_CASE,
        ).findAll(text).forEach { found.add(it.value.trimEnd('.', ',', ';', ')')) }
        return found.map { it.trim() }
            .filter { it.startsWith("http") }
            .filter { !it.contains("share_logo", ignoreCase = true) }
            .filter { u ->
                val x = u.lowercase()
                !x.contains(".css") && !x.contains(".js") && !x.contains(".ttf") &&
                    !x.contains("/assets/") && !x.contains("/fonts/")
            }
            .distinct()
            .take(12)
    }

    private fun normalizeGoodsUrl(raw: String, itemId: String): String {
        var t = raw.trim()
        if (t.startsWith("//")) t = "https:$t"
        if (t.startsWith("yangkeduo.com") || t.startsWith("mobile.yangkeduo.com")) t = "https://$t"
        if (t.startsWith("goods.html") || t.startsWith("/goods")) {
            t = "https://mobile.yangkeduo.com/" + t.trimStart('/')
        }
        val m = Regex("""goods_id=(\d{8,})""", RegexOption.IGNORE_CASE).find(t)
        if (m != null) {
            return "https://mobile.yangkeduo.com/goods.html?goods_id=${m.groupValues[1]}"
        }
        if (itemId.isNotBlank()) {
            return "https://mobile.yangkeduo.com/goods.html?goods_id=$itemId"
        }
        return t
    }

    private fun cleanApproval(raw: String): String {
        if (raw.isBlank()) return ""
        // 至少 6 位数字，避免截成「国药准字Z11」
        val m = Regex("""\u56fd\u836f\u51c6\u5b57[A-Za-z]?\u5b57?[A-Za-z]?\d{6,}""").find(raw)
            ?: Regex("""\u56fd\u836f\u51c6\u5b57[A-Za-z]?\u5b57?[A-Za-z]?\d+""").find(raw)
        return (m?.value ?: raw).replace("\\s+".toRegex(), "").take(40)
    }

    private fun buildSpecListJson(map: Map<String, String>): String {
        val arr = JSONArray()
        for ((k, v) in map) {
            if (v.isBlank()) continue
            val obj = JSONObject()
            obj.put("key", k)
            obj.put("value", v)
            arr.put(obj)
        }
        return arr.toString()
    }

    private fun labelValue(text: String, labels: List<String>): String {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() }
        for (label in labels) {
            val same = Regex("""^$label[\s:：\uFF1A]+(.+)$""", RegexOption.MULTILINE).find(text)
            if (same != null) {
                val v = sanitizeValue(same.groupValues[1])
                if (v.isNotBlank()) return v
            }
            val glued = Regex("""$label([\u4e00-\u9fffA-Za-z0-9][^\n]{0,40})""").find(text)
            if (glued != null) {
                val v = sanitizeValue(glued.groupValues[1])
                if (v.isNotBlank()) return v
            }
            for (i in lines.indices) {
                if (lines[i] == label || lines[i].startsWith("$label:") || lines[i].startsWith("$label\uFF1A")) {
                    val inline = lines[i].removePrefix(label).replace(Regex("""^[:\uFF1A\s]+"""), "")
                    if (inline.isNotBlank()) {
                        val v = sanitizeValue(inline)
                        if (v.isNotBlank()) return v
                    }
                    val next = lines.getOrNull(i + 1).orEmpty()
                    val v = sanitizeValue(next)
                    if (v.isNotBlank()) return v
                }
            }
            val m = Regex("""$label[\s\n:\uFF1A]+([^\n]{1,80})""").find(text)
            if (m != null) {
                val v = sanitizeValue(m.groupValues[1])
                if (v.isNotBlank()) return v
            }
        }
        return ""
    }

    private fun sanitizeValue(raw: String): String {
        var v = raw.trim().replace(Regex("""^[:\uFF1A\s>\uFF1E]+"""), "")
        v = v.split(Regex("""\s*(?:\u67e5\u770b\u5168\u90e8|\u5546\u54c1\u53c2\u6570|\u8fdb\u5e97)"""))[0].trim()
        if (v.isBlank() || v.length > 80) return ""
        if (knownLabels.any { it == v }) return ""
        if (junkValues.contains(v)) return ""
        return v
    }

    private fun extractSellName(text: String): String {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() }
        val skip = Regex(
            """^(\u7efc\u5408|\u9500\u91cf|\u4ef7\u683c|\u7b5b\u9009|\u54c1\u724c|\u5546\u54c1|\u767e\u4ebf|\u5904\u65b9\u836f|\u6b63\u54c1\u9669|\u62fc\u591a\u591a|\u767b\u5f55|\u5206\u4eab|\u5ba2\u670d|\u6536\u85cf|\u5df2\u62fc|\u603b\u552e|\u5546\u54c1\u8be6\u60c5|\u5546\u54c1\u53c2\u6570|\u5e97\u94fa\u8d44\u8d28|\u9876\u90e8|\u5b98\u65b9\u8865\u8d34|\u00a5|\uffe5|\d+(\.\d+)?)$"""
        )
        return lines.firstOrNull {
            it.length >= 6 &&
                !skip.containsMatchIn(it) &&
                !it.startsWith("\u00a5") && !it.startsWith("\uffe5") &&
                !knownLabels.contains(it) &&
                !junkValues.contains(it) &&
                !Regex("""^\u3010[^\u3011]{1,6}\u3011$""").matches(it)
        }?.take(120).orEmpty()
    }

    private fun extractSpec(name: String): String {
        val m = Regex(
            """(\d+(?:\.\d+)?\s*(?:mg|g|ml|\u514b)\s*[*＊\u00d7xX]?\s*\d*\s*(?:\u7247|\u7c92|\u4e38|\u888b|\u76d2|\u652f|\u74f6)?(?:/[^\s，,]{0,12})?)""",
            RegexOption.IGNORE_CASE,
        ).find(name)
        return m?.value?.replace("\\s+".toRegex(), "").orEmpty()
    }

    private fun fallbackPrice(text: String, compact: String): Double? {
        val re = Regex("""[\u00a5\uffe5]\s*(\d+(?:\.\d{1,2})?)""")
        for (m in re.findAll(text)) {
            val idx = m.range.first
            val ctx = text.substring(maxOf(0, idx - 12), minOf(text.length, idx + 28))
            if (ctx.contains("\u8865\u8d34") && !ctx.contains("\u8865\u8d34\u4ef7") && !ctx.contains("\u514d\u62fc")) continue
            if (Regex("""[\u00a5\uffe5]\s*\d+(?:\.\d{1,2})?\s*[-~～]\s*\d""").containsMatchIn(ctx)) continue
            val n = m.groupValues[1].toDoubleOrNull() ?: continue
            if (n >= 0.1) return n
        }
        Regex("""[\u00a5\uffe5](\d+(?:\.\d{1,2})?)[-~～](\d+(?:\.\d{1,2})?)""").find(compact)
            ?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let { return it }
        return null
    }

    /**
     * 提取店铺名。避免误抓标题里的「药房直发」等商品文案。
     * 优先：带「进店/本店已拼/年老店」的旗舰店行；其次独立店铺行。
     */
    fun extractShopName(text: String): String {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() && it.length in 3..48 }

        // 1) 「雪芙蓉大药房旗舰店 … 进店 / 本店已拼」
        val nearAction = Regex(
            """([^\n【]{2,28}(?:旗舰店|专营店|专卖店|大药房|药店))[^\n]{0,36}(?:进店|本店已拼|年老店|回头客)""",
        )
        nearAction.find(text)?.groupValues?.getOrNull(1)?.let { raw ->
            val n = cleanShopName(raw)
            if (isValidShopName(n)) return n
        }

        // 2) 单独成行的店铺名（旗舰店优先）
        val ranked = lines.mapNotNull { line ->
            val n = cleanShopName(line)
            if (!isValidShopName(n)) return@mapNotNull null
            val score = when {
                n.endsWith("旗舰店") -> 100
                n.endsWith("专营店") || n.endsWith("专卖店") -> 90
                n.contains("大药房") -> 80
                n.endsWith("药店") || n.endsWith("药房") -> 70
                else -> 40
            } + if (n.length in 6..22) 10 else 0
            score to n
        }.sortedByDescending { it.first }
        ranked.firstOrNull()?.second?.let { return it }

        // 3) 宽松兜底：仍排除商品标题特征
        val loose = Regex("""([^\n【]{2,24}(?:旗舰店|专营店|专卖店|大药房))""")
            .findAll(text)
            .map { cleanShopName(it.groupValues[1]) }
            .firstOrNull { isValidShopName(it) }
            .orEmpty()
        return loose
    }

    private fun cleanShopName(raw: String): String {
        var n = raw.replace("\\s+".toRegex(), "").trim()
        n = n.split(Regex("""(?:已拼|销量|全店总售|评价|进店|100%|正品|资质|本店已拼)"""))[0].trim()
        n = n.replace(Regex("""本店$"""), "")
        n = n.replace("旗舰店旗舰店", "旗舰店")
        // 去掉前缀杂质
        n = n.replace(Regex("""^(该商品所属|所属店铺|店铺)"""), "")
        return n.take(40)
    }

    private fun isValidShopName(name: String): Boolean {
        if (name.length !in 4..36) return false
        // 标题里「…药房直发」类误匹配
        val junk = listOf(
            "直发", "正品保证", "假一赔", "颗粒", "胶囊", "糖浆", "片剂",
            "袋/盒", "支/盒", "瓶/盒", "RX", "国药准字", "到期", "临期",
            "免拼", "单独购买", "复诊", "开药", "已拼", "最后",
        )
        if (junk.any { name.contains(it) }) return false
        if (Regex("""\d+\s*[g克ml毫升袋盒瓶片]""").containsMatchIn(name)) return false
        return name.contains("旗舰店") || name.contains("专营店") || name.contains("专卖店") ||
            name.contains("大药房") || name.endsWith("药店") || name.endsWith("药房")
    }

    /**
     * 从「尺寸」规格弹层文案解析多规格售价。
     * 例：五盒【家庭特惠装】全家可用+ 最新效期 ¥17.5
     */
    fun buildSkuFromPanel(panelText: String): String {
        if (panelText.isBlank()) return ""
        // 「最后2件」/「2件9.9折」勿误伤价格末位（¥23件9.9折→¥2）
        val cleaned = panelText.replace("\\s+".toRegex(), " ")
            .replace(Regex("""([¥￥]\d+\.\d{1,2})(\d{1,2})件\d+(?:\.\d+)?折"""), "$1")
            .replace(Regex("""([¥￥]\d+)(\d{1,2})件\d+(?:\.\d+)?折"""), "$1")
            .replace(Regex("""([¥￥]\d+\.\d?)(\d)最后\2件"""), "$1")
            .replace(Regex("""([¥￥]\d*?)(\d{1,2})最后\2件"""), "$1")
            .replace(Regex("""([¥￥]\d+\.\d{1,2})最后\d{1,2}件"""), "$1 ")
            .replace(Regex("""([¥￥]\d+)最后\d{1,2}件"""), "$1 ")
            .replace(Regex("""最后\d+件"""), " ")
            .replace(Regex("""仅剩?\d+件"""), " ")
            .replace(Regex("""(^|[^¥￥\d])([1-9]\d?)件\d+(?:\.\d+)?折"""), "$1 ")

        val items = linkedMapOf<String, Double>()
        val re = Regex(
            """((?:[一二两三四五六七八九十百\d]+\s*盒(?:装)?(?:\s*\d+\s*袋)?|[^\n¥￥]{0,6}【[^】\n]{1,40}】)[^\n¥￥]{0,48}?)[¥￥]\s*(\d+\.\d{1,2}|\d+)(?!\d)(?!件)""",
        )
        for (m in re.findAll(cleaned)) {
            var name = cleanSkuName(m.groupValues[1])
            if (!looksLikeSkuName(name)) continue
            val price = m.groupValues[2].toDoubleOrNull() ?: continue
            if (price < 0.01 || price > 99999) continue
            val old = items[name]
            if (old == null || price < old) items[name] = price
        }
        if (items.size < 2) {
            for (line in cleaned.lines().map { it.trim() }.filter { it.length in 4..100 }) {
                if (line.contains("提交订单") || line.startsWith("已选") || line == "尺寸" || line == "款式") continue
                val m = Regex("""^(.+?)[¥￥]\s*(\d+\.\d{1,2}|\d+)\s*$""").find(line) ?: continue
                val name = cleanSkuName(m.groupValues[1])
                val price = m.groupValues[2].toDoubleOrNull() ?: continue
                if (!looksLikeSkuName(name)) continue
                items.putIfAbsent(name, price)
            }
        }
        if (items.isEmpty()) return ""
        return items.entries.joinToString(" | ") { (name, p) ->
            "$name(售价¥${trimNum(p)})"
        }
    }

    private fun cleanSkuName(raw: String): String {
        var n = raw.replace("\\s+".toRegex(), " ").trim()
            .trim('·', '-', '—', '|', ':', '：')
        n = n.replace(Regex("""^(已选|尺寸|款式|数量)\s*"""), "").trim()
        n = n.replace(Regex("""\s*(最后\d+件|仅\d+件).*$"""), "").trim()
        return n.take(80)
    }

    private fun looksLikeSkuName(name: String): Boolean {
        if (name.length < 2 || name.length > 80) return false
        if (name.contains("提交订单") || name.contains("单独购买") || name.contains("免拼购买")) return false
        return name.contains("盒") || name.contains("袋") || name.contains("件") ||
            name.contains("装") || name.contains("【")
    }

    private fun buildSkuPricesText(text: String, compact: String, display: Double?): String {
        val fromPanel = buildSkuFromPanel(text)
        if (fromPanel.isNotBlank()) return fromPanel
        val packs = Regex("""(\d+(?:\u76d2|\u4ef6|\u74f6)\u88c5)""").findAll(compact).map { it.groupValues[1] }.distinct().toList()
        if (packs.isEmpty()) return ""
        val range = Regex("""[\u00a5\uffe5](\d+(?:\.\d{1,2})?)[-~～](\d+(?:\.\d{1,2})?)""").find(compact)
        val lo = range?.groupValues?.getOrNull(1)?.toDoubleOrNull()
        val hi = range?.groupValues?.getOrNull(2)?.toDoubleOrNull()
        val inferred = if (lo != null && hi != null) inferPackPrices(packs, lo, hi) else emptyMap()
        val parts = packs.map { name ->
            val p = inferred[name] ?: if (packs.size == 1) display else null
            if (p != null) "$name(售价¥${trimNum(p)})" else name
        }
        return parts.joinToString(" | ")
    }

    fun inferPackPrices(names: List<String>, lo: Double, hi: Double): Map<String, Double> {
        val packs = names.mapNotNull { n ->
            val num = Regex("""(\d+)""").find(n)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: return@mapNotNull null
            n to num
        }
        if (packs.size < 2 || lo <= 0 || hi <= lo) return emptyMap()
        val maxN = packs.maxOf { it.second }
        val minN = packs.minOf { it.second }
        val unit = lo / minN
        val expectedHi = unit * maxN
        if (kotlin.math.abs(expectedHi - hi) > maxOf(1.0, unit * 0.02)) return emptyMap()
        return packs.associate { (name, n) -> name to ((unit * n * 100).roundToInt() / 100.0) }
    }

    private fun trimNum(v: Double): String =
        if (v == v.toLong().toDouble()) v.toLong().toString() else v.toString()

    /** 供采价流程格式化规格价格 */
    fun trimPriceNum(v: Double): String = trimNum(v)

    private fun skuJsonFromText(text: String): String {
        if (text.isBlank()) return "[]"
        val arr = JSONArray()
        for (part in text.split("|")) {
            val p = part.trim()
            if (p.isBlank()) continue
            val m = Regex("""^(.+?)\(售价¥([\d.]+)\)$""").find(p)
                ?: Regex("""^(.+?)\(\u552e\u4ef7\u00a5([\d.]+)\)$""").find(p)
            val obj = JSONObject()
            obj.put("sku_id", "")
            if (m != null) {
                obj.put("spec", m.groupValues[1].trim())
                obj.put("normal_price", m.groupValues[2].toDoubleOrNull() ?: JSONObject.NULL)
            } else {
                obj.put("spec", p)
                obj.put("normal_price", JSONObject.NULL)
            }
            obj.put("group_price", JSONObject.NULL)
            arr.put(obj)
        }
        return arr.toString()
    }
}
