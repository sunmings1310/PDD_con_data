package com.collector.pdd.engine

import java.net.HttpURLConnection
import java.net.URL
import java.util.regex.Pattern
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 用网络把分享短链 / 落地页解析成 goods_id + 主图（og:image）。
 * 必须用标题关键词校验，避免剪贴板残留/页面推荐商品串号（感冒灵→矿泉水）。
 */
object GoodsLinkResolver {

    data class Resolved(
        val goodsId: String = "",
        val itemUrl: String = "",
        val images: List<String> = emptyList(),
        val title: String = "",
        val rejected: Boolean = false,
        val rejectReason: String = "",
    )

    private val goodsIdParam = Pattern.compile(
        "(?:goods[_]?id|goodsId)=(\\d{8,16})",
        Pattern.CASE_INSENSITIVE,
    )
    /** goods.html?id= / goods2.html?...&id= */
    private val goodsHtmlId = Pattern.compile(
        """goods(?:2)?\.html[^\s"'<>]*?[?&]id=(\d{8,16})""",
        Pattern.CASE_INSENSITIVE,
    )
    private val goodsIdJson = Pattern.compile(
        """["']goods[_]?id["']\s*[:=]\s*["']?(\d{8,16})""",
        Pattern.CASE_INSENSITIVE,
    )
    private val ogImage = Pattern.compile(
        """<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""",
        Pattern.CASE_INSENSITIVE,
    )
    private val ogImageAlt = Pattern.compile(
        """<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']""",
        Pattern.CASE_INSENSITIVE,
    )
    private val ogTitle = Pattern.compile(
        """<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']""",
        Pattern.CASE_INSENSITIVE,
    )
    private val anyHttp = Pattern.compile(
        """https?://[^\s"'<>\u4e00-\u9fff￥€$]+""",
        Pattern.CASE_INSENSITIVE,
    )
    private val bareHostUrl = Pattern.compile(
        """(?:mobile\.)?yangkeduo\.com/[^\s"'<>\u4e00-\u9fff￥€$]+|p\.pinduoduo\.com/[A-Za-z0-9_-]+""",
        Pattern.CASE_INSENSITIVE,
    )
    private val deeplink = Pattern.compile(
        """(?:pinduoduo|yangkeduo)://[^\s"'<>\u4e00-\u9fff￥€$]+""",
        Pattern.CASE_INSENSITIVE,
    )

    fun normalizeShareText(raw: String): String {
        if (raw.isBlank()) return ""
        return raw
            .replace('\u00a0', ' ')
            .replace("\u200b", "")
            .replace("\u200c", "")
            .replace("\u200d", "")
            .replace("\ufeff", "")
            .replace("＆", "&")
            .replace("＝", "=")
            .trim()
    }

    fun extractGoodsId(text: String): String {
        val t = normalizeShareText(text)
        if (t.isBlank()) return ""
        goodsIdParam.matcher(t).let { m -> if (m.find()) return m.group(1).orEmpty() }
        goodsHtmlId.matcher(t).let { m -> if (m.find()) return m.group(1).orEmpty() }
        goodsIdJson.matcher(t).let { m -> if (m.find()) return m.group(1).orEmpty() }
        return ""
    }

    fun extractGoodsUrls(text: String): List<String> {
        val t = normalizeShareText(text)
        if (t.isBlank()) return emptyList()
        val out = mutableListOf<String>()

        fun accept(rawUrl: String) {
            var u = rawUrl.trim().trimEnd(',', '.', ')', ']', '，', '。', '；', ';', '!', '！')
            if (u.startsWith("pinduoduo://", true) || u.startsWith("yangkeduo://", true)) {
                val id = extractGoodsId(u)
                if (id.isNotBlank()) {
                    out.add(buildGoodsUrl(id))
                    return
                }
                // deeplink 里嵌了 http
                anyHttp.matcher(u).let { m ->
                    if (m.find()) {
                        accept(m.group())
                        return
                    }
                }
            }
            if (!u.startsWith("http", true)) {
                u = "https://$u"
            }
            val low = u.lowercase()
            if (low.contains("goods_id=") || low.contains("goodsid=") ||
                low.contains("yangkeduo.com") || low.contains("pinduoduo.com") ||
                low.contains("pinduoduo.cn") || low.contains("yangkeduo.cn")
            ) {
                out.add(u)
            }
        }

        val m1 = anyHttp.matcher(t)
        while (m1.find()) accept(m1.group())
        val m2 = deeplink.matcher(t)
        while (m2.find()) accept(m2.group())
        val m3 = bareHostUrl.matcher(t)
        while (m3.find()) accept(m3.group())

        return out.distinct()
    }

    fun buildGoodsUrl(goodsId: String): String {
        if (goodsId.isBlank()) return ""
        return "https://mobile.yangkeduo.com/goods.html?goods_id=$goodsId"
    }

    /** 拼多多「复制链接」常见：goods1.html?ps=xxx （无 goods_id） */
    fun isPsShareUrl(url: String): Boolean {
        val u = url.lowercase()
        return (u.contains("yangkeduo.com") || u.contains("pinduoduo.com")) &&
            (u.contains("ps=") || u.contains("goods1.html") || u.contains("goods.html"))
    }

    /**
     * 跟跳 goods1.html?ps=xxx → Location 里的 goods_id。
     * 实测：307 Location 形如 goods1.html?goods_id=442061835883&...
     */
    fun expandShareLink(shareUrl: String): Resolved {
        val start = normalizeShareText(shareUrl).trim()
        if (start.isBlank()) return Resolved()
        var directId = extractGoodsId(start)
        if (directId.isNotBlank()) {
            return Resolved(goodsId = directId, itemUrl = buildGoodsUrl(directId))
        }
        // 先抽候选 URL
        val cand = extractGoodsUrls(start).firstOrNull().orEmpty().ifBlank {
            if (start.startsWith("http")) start else ""
        }
        if (cand.isBlank()) return Resolved(itemUrl = "")

        directId = extractGoodsId(cand)
        if (directId.isNotBlank()) {
            return Resolved(goodsId = directId, itemUrl = buildGoodsUrl(directId))
        }

        val followed = followRedirects(cand)
        val id = extractGoodsId(followed.url)
            .ifBlank { extractGoodsId(followed.html) }
        if (id.isNotBlank()) {
            return Resolved(
                goodsId = id,
                itemUrl = buildGoodsUrl(id),
                // 分享口令展开的 ID 视为可信，标题/主图稍后尽量补
            )
        }
        // 至少把短链留下
        return Resolved(itemUrl = cand, rejectReason = "ps_expand_no_id")
    }

    /** 是否像商品主图（排除 css/js/字体等静态资源）；也接受本地相册/导出路径 */
    fun isProductImageUrl(url: String): Boolean {
        val u = url.trim()
        if (u.isBlank()) return false
        val low = u.lowercase()
        val localImg = low.endsWith(".jpg") || low.endsWith(".jpeg") ||
            low.endsWith(".png") || low.endsWith(".webp")
        // 本地文件：导出目录 / 相册绝对路径 / file://
        if (localImg && (
                low.contains("/exports/images/") ||
                    low.contains("\\exports\\images\\") ||
                    low.startsWith("/storage/") ||
                    low.startsWith("/data/") ||
                    low.startsWith("file:") ||
                    (!low.startsWith("http") && (low.contains("/") || low.contains("\\")))
                )
        ) {
            return true
        }
        if (!low.startsWith("http")) return false
        if (low.contains("share_logo")) return false
        if (listOf(".css", ".js", ".ttf", ".woff", ".woff2", ".map", ".json").any { low.contains(it) }) {
            return false
        }
        if (low.contains("/assets/css") || low.contains("/assets/js") || low.contains("/fonts/")) {
            return false
        }
        val looksImg = listOf(
            ".jpg", ".jpeg", ".png", ".webp", "/goods/", "mms-material", "mms-goods",
            "img.pddpic", "pddpic.com", "yangkeduo.com/goods", "t00img", "t01img",
        ).any { low.contains(it) }
        return looksImg
    }

    /**
     * 标题/页面是否像当前采集的商品。
     * expectTokens 如：感冒灵颗粒、桐岭堂
     */
    fun titleMatches(title: String, expectTokens: List<String>): Boolean {
        if (title.isBlank()) return false
        val t = title.replace("\\s+".toRegex(), "").lowercase()
        val tokens = expectTokens.map { it.replace("\\s+".toRegex(), "") }.filter { it.length >= 2 }
        if (tokens.isEmpty()) return true
        val hitLong = tokens.any { it.length >= 3 && t.contains(it.lowercase()) }
        if (hitLong) return true
        val hitShort = tokens.count { t.contains(it.lowercase()) }
        return hitShort >= 2
    }

    suspend fun resolve(
        rawShare: String,
        hintUrl: String = "",
        hintGoodsId: String = "",
        expectTokens: List<String> = emptyList(),
    ): Resolved = withContext(Dispatchers.IO) {
        val candidates = mutableListOf<String>()
        if (hintUrl.isNotBlank()) candidates.add(hintUrl.trim())
        candidates.addAll(extractGoodsUrls(rawShare))
        if (hintGoodsId.isNotBlank()) candidates.add(buildGoodsUrl(hintGoodsId))

        val uniq = candidates.distinct().filter { it.isNotBlank() }
        if (uniq.isEmpty()) return@withContext Resolved()

        // 优先处理复制链接口令：goods1.html?ps=xxx → 307 Location 含 goods_id
        for (cand in uniq.filter { isPsShareUrl(it) || it.contains("ps=", true) }.ifEmpty { uniq }) {
            val expanded = expandShareLink(cand)
            if (expanded.goodsId.isNotBlank()) {
                val images = fetchProductImages(expanded.goodsId, expectTokens)
                return@withContext Resolved(
                    goodsId = expanded.goodsId,
                    itemUrl = expanded.itemUrl.ifBlank { buildGoodsUrl(expanded.goodsId) },
                    images = images,
                    title = "",
                )
            }
        }

        var lastReject = ""
        for (cand in uniq.take(4)) {
            var goodsId = extractGoodsId(cand).ifBlank { hintGoodsId }
            var itemUrl = cand
            var htmlProbe = ""
            val fromSharePassword = cand.contains("ps=", true) || cand.contains("goods1.html", true)

            if (goodsId.isBlank() || !itemUrl.contains("goods_id=", true)) {
                val followed = followRedirects(itemUrl)
                if (followed.url.isNotBlank()) {
                    itemUrl = followed.url
                    goodsId = extractGoodsId(followed.url).ifBlank { goodsId }
                    htmlProbe = followed.html
                    if (goodsId.isBlank() && htmlProbe.isNotBlank()) {
                        goodsId = extractGoodsId(htmlProbe)
                    }
                }
            }
            if (goodsId.isBlank() && htmlProbe.isBlank()) {
                htmlProbe = fetchHtml(itemUrl)
                goodsId = extractGoodsId(htmlProbe)
            }
            if (goodsId.isBlank()) {
                lastReject = "no_goods_id from $cand"
                continue
            }
            itemUrl = buildGoodsUrl(goodsId)

            // 来自分享口令/复制链接的 ID 直接信任，不再用泛标题「拼多多商城」卡死
            if (fromSharePassword || (hintGoodsId.isNotBlank() && hintGoodsId == goodsId)) {
                val images = fetchProductImages(goodsId, expectTokens)
                return@withContext Resolved(
                    goodsId = goodsId,
                    itemUrl = itemUrl,
                    images = images,
                )
            }

            val html = fetchHtml(itemUrl).ifBlank { htmlProbe }
            if (html.isBlank()) {
                return@withContext Resolved(goodsId = goodsId, itemUrl = itemUrl)
            }
            var title = ""
            val tm = ogTitle.matcher(html)
            if (tm.find()) title = tm.group(1).orEmpty()
            if (title.isBlank()) {
                val m = Pattern.compile("""<title>([^<]+)</title>""", Pattern.CASE_INSENSITIVE)
                    .matcher(html)
                if (m.find()) title = m.group(1).orEmpty()
            }

            // 泛标题不算有效标题
            val genericTitle = title.contains("拼多多") && !titleMatches(title, expectTokens)
            if (expectTokens.isNotEmpty() && title.isNotBlank() && !genericTitle) {
                if (!titleMatches(title, expectTokens)) {
                    lastReject = "title_mismatch title=$title"
                    // 仍保留 ID（来自明确 goods_id 链接时）
                    if (cand.contains("goods_id=", true)) {
                        return@withContext Resolved(goodsId = goodsId, itemUrl = itemUrl, title = title)
                    }
                    continue
                }
            }

            val images = mutableListOf<String>()
            listOf(ogImage, ogImageAlt).forEach { p ->
                val m = p.matcher(html)
                while (m.find()) {
                    val u = cleanImg(m.group(1).orEmpty())
                    if (isProductImageUrl(u)) images.add(u)
                }
            }
            images.addAll(extractImagesFromHtml(html))

            return@withContext Resolved(
                goodsId = goodsId,
                itemUrl = itemUrl,
                images = images.distinct(),
                title = title,
            )
        }

        val fallbackUrl = uniq.firstOrNull().orEmpty()
        if (fallbackUrl.isNotBlank()) {
            return@withContext Resolved(
                itemUrl = fallbackUrl,
                rejected = false,
                rejectReason = lastReject,
            )
        }
        Resolved(rejected = true, rejectReason = lastReject.ifBlank { "no_candidate" })
    }

    private fun fetchProductImages(goodsId: String, expectTokens: List<String>): List<String> {
        if (goodsId.isBlank()) return emptyList()
        // 未登录 H5 常只有 share_logo；多试几个落地页，能捞到主图更好
        val pages = listOf(
            buildGoodsUrl(goodsId),
            "https://mobile.yangkeduo.com/goods1.html?goods_id=$goodsId",
            "https://mobile.yangkeduo.com/goods2.html?goods_id=$goodsId",
        )
        val out = mutableListOf<String>()
        for (p in pages) {
            val html = fetchHtml(p)
            if (html.isBlank()) continue
            out.addAll(extractImagesFromHtml(html))
            if (out.isNotEmpty()) break
            // 正文里若能命中关键词，再宽一点捞图
            if (expectTokens.isNotEmpty() && titleMatches(html.take(4000), expectTokens)) {
                out.addAll(extractImagesFromHtml(html, loose = true))
                if (out.isNotEmpty()) break
            }
        }
        return out.distinct()
    }

    private fun extractImagesFromHtml(html: String, loose: Boolean = false): List<String> {
        val decoded = html
            .replace("\\u002F", "/")
            .replace("\\/", "/")
            .replace("&amp;", "&")
        val out = mutableListOf<String>()
        listOf(ogImage, ogImageAlt).forEach { p ->
            val m = p.matcher(decoded)
            while (m.find()) {
                val u = cleanImg(m.group(1).orEmpty())
                if (isProductImageUrl(u)) out.add(u)
            }
        }
        // JSON 字段里的主图
        val fieldRe = Pattern.compile(
            """"(?:thumb_url|hd_thumb_url|hd_url|image_url|pic_url|main_image)"\s*:\s*"(https?://[^"]+)"""",
            Pattern.CASE_INSENSITIVE,
        )
        val fm = fieldRe.matcher(decoded)
        while (fm.find()) {
            val u = cleanImg(fm.group(1).orEmpty())
            if (isProductImageUrl(u)) out.add(u)
        }
        val imgRe = Pattern.compile(
            if (loose) {
                """https?://[^"'\\\s]+(?:pddpic|yangkeduo|t00img|t01img)[^"'\\\s]*\.(?:jpg|jpeg|png|webp)[^"'\\\s]*"""
            } else {
                """https?://[^"'\\\s]+(?:img\.pddpic|mms-material|mms-goods|t00img|t01img)[^"'\\\s]*\.(?:jpg|jpeg|png|webp)[^"'\\\s]*"""
            },
            Pattern.CASE_INSENSITIVE,
        )
        val im = imgRe.matcher(decoded)
        var n = 0
        while (im.find() && n < 8) {
            val u = cleanImg(im.group())
            if (isProductImageUrl(u)) {
                out.add(u)
                n++
            }
        }
        return out
    }

    private fun cleanImg(u: String): String =
        u.trim().replace("&amp;", "&").trimEnd(',', '.', ')', ']')

    private data class FollowResult(val url: String, val html: String = "")

    private fun followRedirects(start: String): FollowResult {
        var current = start
        var lastHtml = ""
        repeat(8) {
            val conn = (URL(current).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 10000
                readTimeout = 10000
                requestMethod = "GET"
                setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 " +
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                )
                setRequestProperty("Accept", "text/html,application/xhtml+xml,*/*")
                setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9")
                setRequestProperty("Referer", "https://mobile.yangkeduo.com/")
            }
            try {
                val code = conn.responseCode
                // 有的机型 header 大小写不同；再扫一遍全部头
                var loc = conn.getHeaderField("Location").orEmpty()
                if (loc.isBlank()) {
                    loc = conn.headerFields?.entries
                        ?.firstOrNull { it.key.equals("Location", true) }
                        ?.value?.firstOrNull().orEmpty()
                }
                if (code in 300..399 && loc.isNotBlank()) {
                    conn.disconnect()
                    current = if (loc.startsWith("http")) loc
                    else URL(URL(current), loc).toString()
                    // ps= → goods_id= 就在 Location 里
                    if (extractGoodsId(current).isNotBlank()) return FollowResult(current)
                    return@repeat
                }
                // 200：读一小段 HTML，找 meta refresh / goods_id
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                lastHtml = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                    .orEmpty().take(200_000)
                conn.disconnect()
                if (extractGoodsId(current).isNotBlank()) return FollowResult(current, lastHtml)
                if (extractGoodsId(lastHtml).isNotBlank()) {
                    val id = extractGoodsId(lastHtml)
                    return FollowResult(buildGoodsUrl(id), lastHtml)
                }
                // meta refresh
                val meta = Pattern.compile(
                    """http-equiv=["']refresh["'][^>]+content=["'][^"']*url=([^"']+)["']""",
                    Pattern.CASE_INSENSITIVE,
                ).matcher(lastHtml)
                val next = when {
                    meta.find() -> meta.group(1).orEmpty()
                    else -> {
                        // window.location / location.href
                        val js = Pattern.compile(
                            """(?:window\.)?location(?:\.href)?\s*=\s*["']([^"']+)["']""",
                            Pattern.CASE_INSENSITIVE,
                        ).matcher(lastHtml)
                        if (js.find()) js.group(1).orEmpty() else ""
                    }
                }
                if (next.isNotBlank() && next != current) {
                    current = if (next.startsWith("http")) next
                    else try {
                        URL(URL(current), next).toString()
                    } catch (_: Exception) {
                        next
                    }
                    if (extractGoodsId(current).isNotBlank()) return FollowResult(current, lastHtml)
                    return@repeat
                }
                return FollowResult(current, lastHtml)
            } catch (_: Exception) {
                try {
                    conn.disconnect()
                } catch (_: Exception) {
                }
                return FollowResult(current, lastHtml)
            }
        }
        return FollowResult(current, lastHtml)
    }

    private fun fetchHtml(url: String): String {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 10000
            readTimeout = 12000
            requestMethod = "GET"
            setRequestProperty(
                "User-Agent",
                "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            )
            setRequestProperty("Accept", "text/html,application/xhtml+xml")
            setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9")
        }
        return try {
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty().take(400_000)
        } catch (_: Exception) {
            ""
        } finally {
            try {
                conn.disconnect()
            } catch (_: Exception) {
            }
        }
    }
}
