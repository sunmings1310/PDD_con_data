package com.collector.pdd.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

object A11yHelper {

    private val urlRe = Regex(
        """https?://[^\s"'<>\]\)]+""",
        RegexOption.IGNORE_CASE,
    )
    private val goodsIdRe = Regex(
        """(?:goods[_]?id|goodsId)[=:\\\"'/]+(\d{8,})""",
        RegexOption.IGNORE_CASE,
    )
    private val mallIdRe = Regex(
        """(?:mall[_]?id|mallId|shop[_]?id|shopId)[=:\\\"'/]+(\d{5,})""",
        RegexOption.IGNORE_CASE,
    )
    private val imageUrlRe = Regex(
        """https?://[^\s"'<>\]]*(?:pddpic|mms-material|mms-goods|img\.pddpic|yangkeduo)[^\s"'<>\]]*""",
        RegexOption.IGNORE_CASE,
    )

    fun root(service: AccessibilityService): AccessibilityNodeInfo? =
        service.rootInActiveWindow

    /** 扫所有交互窗口（分享弹层常在独立 window） */
    fun roots(service: AccessibilityService): List<AccessibilityNodeInfo> {
        val out = mutableListOf<AccessibilityNodeInfo>()
        root(service)?.let { out.add(it) }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                service.windows?.forEach { w ->
                    w.root?.let { r ->
                        if (out.none { it == r }) out.add(r)
                    }
                }
            }
        } catch (_: Exception) {
        }
        return out
    }

    fun dumpAllWindows(service: AccessibilityService): String =
        roots(service).joinToString("\n") { dumpText(it) }

    fun harvestAllWindows(service: AccessibilityService): Harvest {
        val texts = mutableListOf<String>()
        val images = mutableListOf<String>()
        var goodsId = ""
        var mallId = ""
        val urls = mutableListOf<String>()
        for (r in roots(service)) {
            val h = harvestIdsAndUrls(r)
            texts.add(h.blob)
            images.addAll(h.images)
            urls.addAll(h.urls)
            if (goodsId.isBlank()) goodsId = h.goodsId
            if (mallId.isBlank()) mallId = h.mallId
            images.addAll(harvestImageHints(r))
        }
        return Harvest(
            goodsId = goodsId,
            mallId = mallId,
            urls = urls.distinct(),
            images = images.distinct().filter { looksLikeImage(it) },
            blob = texts.joinToString("\n"),
        )
    }

    fun collectTexts(node: AccessibilityNodeInfo?, out: MutableList<String>, depth: Int = 0) {
        if (node == null || depth > 45) return
        val t = node.text?.toString()?.trim().orEmpty()
        val d = node.contentDescription?.toString()?.trim().orEmpty()
        val hint = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            node.hintText?.toString()?.trim().orEmpty()
        } else ""
        val viewId = node.viewIdResourceName?.trim().orEmpty()
        if (t.isNotEmpty()) out.add(t)
        if (d.isNotEmpty() && d != t) out.add(d)
        if (hint.isNotEmpty() && hint != t && hint != d) out.add(hint)
        if (viewId.isNotEmpty() && (viewId.contains("goods") || viewId.contains("mall"))) {
            out.add(viewId)
        }
        for (i in 0 until node.childCount) {
            collectTexts(node.getChild(i), out, depth + 1)
        }
    }

    fun dumpText(node: AccessibilityNodeInfo?): String {
        val out = mutableListOf<String>()
        collectTexts(node, out)
        return out.joinToString("\n")
    }

    /** 从节点树收集 URL / goods_id / mall_id / 图片地址 */
    fun harvestIdsAndUrls(node: AccessibilityNodeInfo?): Harvest {
        val texts = mutableListOf<String>()
        collectDeepRaw(node, texts)
        val blob = texts.joinToString("\n")
        val urls = urlRe.findAll(blob).map { it.value.trimEnd('.', ',', ';', ')', ']') }.distinct().toList()
        val images = buildList {
            imageUrlRe.findAll(blob).forEach { add(cleanUrl(it.value)) }
            urls.filter { looksLikeImage(it) }.forEach { add(cleanUrl(it)) }
        }.distinct().filter { !it.contains("share_logo", ignoreCase = true) }
        val goodsId = goodsIdRe.find(blob)?.groupValues?.getOrNull(1).orEmpty()
            .ifBlank {
                Regex("""goods\.html\?[^ \n]*goods_id=(\d{8,})""", RegexOption.IGNORE_CASE)
                    .find(blob)?.groupValues?.getOrNull(1).orEmpty()
            }
            .ifBlank { extractGoodsIdFromViewIds(blob) }
            .ifBlank {
                // p.pinduoduo.com 短链旁偶发带 id
                Regex("""(?:item_id|itemId)[=:\\\"'/]+(\d{8,})""", RegexOption.IGNORE_CASE)
                    .find(blob)?.groupValues?.getOrNull(1).orEmpty()
            }
        val mallId = mallIdRe.find(blob)?.groupValues?.getOrNull(1).orEmpty()
        return Harvest(
            goodsId = goodsId,
            mallId = mallId,
            urls = urls,
            images = images,
            blob = blob,
        )
    }

    private fun extractGoodsIdFromViewIds(blob: String): String {
        // viewId 如 xxx_goods_123456789012 / goodsid_xxx
        Regex("""(?:goods[_]?id|goodsid|item[_]?id)[_/-]?(\d{8,16})""", RegexOption.IGNORE_CASE)
            .find(blob)?.groupValues?.getOrNull(1)?.let { return it }
        return ""
    }

    data class Harvest(
        val goodsId: String = "",
        val mallId: String = "",
        val urls: List<String> = emptyList(),
        val images: List<String> = emptyList(),
        val blob: String = "",
    )

    private fun collectDeepRaw(node: AccessibilityNodeInfo?, out: MutableList<String>, depth: Int = 0) {
        if (node == null || depth > 50) return
        val attrs = mutableListOf(
            node.text?.toString(),
            node.contentDescription?.toString(),
            node.viewIdResourceName,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            attrs.add(node.hintText?.toString())
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            attrs.add(node.tooltipText?.toString())
        }
        attrs.forEach { s ->
            if (!s.isNullOrBlank()) out.add(s)
        }
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                val sd = node.stateDescription?.toString()
                if (!sd.isNullOrBlank()) out.add(sd)
            } catch (_: Exception) {
            }
        }
        // EXTRA: 部分机型把链接放在 extras
        try {
            val extras = node.extras
            if (extras != null) {
                for (key in extras.keySet()) {
                    val v = extras.get(key)?.toString().orEmpty()
                    if (v.isNotBlank()) out.add("$key=$v")
                }
            }
        } catch (_: Exception) {
        }
        for (i in 0 until node.childCount) {
            collectDeepRaw(node.getChild(i), out, depth + 1)
        }
    }

    private fun looksLikeImage(url: String): Boolean {
        val u = url.lowercase()
        if (u.contains("share_logo")) return false
        if (listOf(".css", ".js", ".ttf", ".woff", "/assets/", "/fonts/").any { u.contains(it) }) return false
        return listOf(".jpg", ".jpeg", ".png", ".webp", "/goods/", "mms-material", "mms-goods")
            .any { u.contains(it) }
    }

    private fun cleanUrl(url: String): String =
        url.trim().trimEnd('.', ',', ';', ')', ']', '"', '\'')

    fun findByText(
        root: AccessibilityNodeInfo?,
        text: String,
        exact: Boolean = false,
        clickableOnly: Boolean = false,
    ): AccessibilityNodeInfo? {
        if (root == null) return null
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MAX_VALUE
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val t = (n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: "")
            val compact = t.replace("\\s+".toRegex(), "").trim()
            val hit = if (exact) compact == text || t.trim() == text
            else compact.contains(text) || t.contains(text)
            if (hit) {
                val target = if (clickableOnly) nearestClickable(n) else n
                if (target != null) {
                    val score = compact.length
                    if (score < bestScore) {
                        bestScore = score
                        best = target
                    }
                }
            }
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        return best
    }

    /** 分享弹层常在独立 window，必须扫全部窗口 */
    fun findByTextAllWindows(
        service: AccessibilityService,
        text: String,
        exact: Boolean = false,
        clickableOnly: Boolean = false,
    ): AccessibilityNodeInfo? {
        for (r in roots(service)) {
            findByText(r, text, exact, clickableOnly)?.let { return it }
        }
        return null
    }

    fun findByViewIdAllWindows(service: AccessibilityService, viewId: String): AccessibilityNodeInfo? {
        for (r in roots(service)) {
            try {
                val list = r.findAccessibilityNodeInfosByViewId(viewId)
                if (!list.isNullOrEmpty()) return list[0]
            } catch (_: Exception) {
            }
        }
        return null
    }

    fun findByContentDescAllWindows(
        service: AccessibilityService,
        desc: String,
    ): AccessibilityNodeInfo? {
        for (r in roots(service)) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val d = n.contentDescription?.toString().orEmpty()
                if (d == desc || d.contains(desc)) return n
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        return null
    }

    /** 列出分享面板上可见的短文案，便于排查 */
    fun listSharePanelLabels(service: AccessibilityService): List<String> {
        val keys = listOf("复制", "分享", "微信", "朋友圈", "QQ", "海报", "口令", "更多", "采集")
        val out = mutableListOf<String>()
        for (r in roots(service)) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val t = listOfNotNull(
                    n.text?.toString(),
                    n.contentDescription?.toString(),
                ).joinToString("|").trim()
                if (t.isNotBlank() && t.length <= 20 && keys.any { t.contains(it) }) {
                    out.add(t)
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        return out.distinct().take(40)
    }

    /**
     * 详情顶栏「分享」按钮：优先 contentDescription/文案精确为「分享」，且靠屏幕上方。
     */
    fun findTopShareButton(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (root == null) return null
        val out = mutableListOf<Pair<Int, AccessibilityNodeInfo>>()
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val desc = n.contentDescription?.toString()?.trim().orEmpty()
            val text = n.text?.toString()?.trim().orEmpty()
            val label = if (desc.isNotBlank()) desc else text
            val hit = label == "分享" || label == "分享商品" || label.startsWith("分享") && label.length <= 6
            if (hit) {
                val r = bounds(n)
                if (r.top in 1..420 && r.right > 0) {
                    val target = nearestClickable(n) ?: n
                    out.add(r.top to target)
                }
            }
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        // 越靠上、越靠右越好
        return out.sortedWith(
            compareBy<Pair<Int, AccessibilityNodeInfo>> { it.first }
                .thenByDescending { bounds(it.second).right },
        ).firstOrNull()?.second
    }

    fun findAllByText(root: AccessibilityNodeInfo?, text: String): List<AccessibilityNodeInfo> {
        if (root == null) return emptyList()
        val out = mutableListOf<AccessibilityNodeInfo>()
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val t = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
                .replace("\\s+".toRegex(), "")
            if (t.contains(text)) out.add(n)
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        return out
    }

    /**
     * 只点「商品详情」区块里的「查看全部」。
     * 页面上常有 3 个同名：商品评价 / 店铺评价 / 商品详情——必须排除前两个。
     */
    fun findProductDetailViewAll(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (root == null) return null
        val candidates = findAllByText(root, "查看全部")
        if (candidates.isEmpty()) return null

        // 区块标题（取文案较短的，避免命中整段）
        val sectionHeaders = collectSectionHeaders(root)
        val detailHeader = sectionHeaders
            .filter { it.second.contains("商品详情") && !it.second.contains("评价") }
            .minByOrNull { it.second.length }
        val detailTop = detailHeader?.let { bounds(it.first).top }

        fun localContext(n: AccessibilityNodeInfo, hops: Int = 3): String {
            var cur: AccessibilityNodeInfo? = n
            val parts = mutableListOf<String>()
            repeat(hops) {
                val p = cur?.parent ?: return@repeat
                parts.add(dumpText(p).take(400))
                cur = p
            }
            return parts.joinToString("\n")
        }

        /** 该「查看全部」上方最近的区块标题 */
        fun nearestHeaderAbove(n: AccessibilityNodeInfo): String {
            val top = bounds(n).top
            val above = sectionHeaders
                .map { bounds(it.first).top to it.second }
                .filter { it.first in 1 until top }
                .maxByOrNull { it.first }
            return above?.second.orEmpty()
        }

        fun isReviewHeader(h: String): Boolean {
            val t = h.replace("\\s+".toRegex(), "")
            return t.contains("商品评价") ||
                t.contains("店铺评价") ||
                t.contains("所属店铺评价") ||
                (t.contains("评价") && !t.contains("商品详情"))
        }

        val scored = candidates.mapNotNull { n ->
            val r = bounds(n)
            if (r.width() <= 0 || r.height() <= 0) return@mapNotNull null
            val header = nearestHeaderAbove(n)
            // 硬排除：上一区块是评价
            if (isReviewHeader(header)) return@mapNotNull null

            val local = localContext(n, 3)
            // 局部上下文仍像评价区 → 排除
            if (local.contains("商品评价") && !local.contains("商品详情")) return@mapNotNull null
            if (local.contains("店铺评价") || local.contains("所属店铺评价")) return@mapNotNull null
            if (local.contains("服务满意") && local.contains("正品") && !local.contains("药品通用名")) {
                return@mapNotNull null
            }

            var score = 0
            if (header.contains("商品详情")) score += 200
            if (local.contains("商品详情")) score += 120
            if (local.contains("药品通用名")) score += 100
            if (local.contains("药品规格") || local.contains("发货地")) score += 80
            if (local.contains("品牌") && (local.contains("通用名") || local.contains("规格"))) score += 60
            // 必须在「商品详情」标题下方
            if (detailTop != null) {
                if (r.top < detailTop - 10) return@mapNotNull null
                // 越贴近详情标题下方越好（评价区的查看全部通常更靠上）
                val dist = r.top - detailTop
                score += (300 - (dist / 3)).coerceIn(0, 300)
            } else {
                // 没找到详情标题时，宁可选更靠下且带药品字段的
                score += (r.top / 15).coerceAtMost(80)
            }
            score to n
        }.sortedByDescending { it.first }

        return scored.firstOrNull()?.second
            // 兜底：详情标题下方、最近的那个查看全部
            ?: run {
                if (detailTop == null) return@run null
                candidates
                    .filter { bounds(it).top >= detailTop - 10 }
                    .filter { !isReviewHeader(nearestHeaderAbove(it)) }
                    .minByOrNull { bounds(it).top - detailTop }
            }
    }

    private fun collectSectionHeaders(root: AccessibilityNodeInfo): List<Pair<AccessibilityNodeInfo, String>> {
        val keys = listOf("商品详情", "商品评价", "店铺评价", "所属店铺评价", "店铺资质", "图文详情")
        val out = mutableListOf<Pair<AccessibilityNodeInfo, String>>()
        for (k in keys) {
            for (n in findAllByText(root, k)) {
                val t = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: "")).trim()
                if (t.length in 2..40) out.add(n to t)
            }
        }
        return out.distinctBy { "${bounds(it.first).top}:${it.second}" }
    }

    /** 按得分列出候选，供点击失败时换下一个 */
    fun listProductDetailViewAllCandidates(root: AccessibilityNodeInfo?): List<AccessibilityNodeInfo> {
        val best = findProductDetailViewAll(root) ?: return emptyList()
        val all = findAllByText(root, "查看全部")
        // best 优先，其余按 top 从大到小（偏下优先），供重试
        return listOf(best) + all.filter { it != best }.sortedByDescending { bounds(it).top }
    }

    /** 收集 Image/ImageView 的 contentDescription / extras / 可能的 URL */
    fun harvestImageHints(root: AccessibilityNodeInfo?): List<String> {
        if (root == null) return emptyList()
        val out = mutableListOf<String>()
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val cls = n.className?.toString().orEmpty()
            val desc = n.contentDescription?.toString().orEmpty()
            val text = n.text?.toString().orEmpty()
            val blob = buildString {
                append(desc).append('\n').append(text)
                try {
                    n.extras?.keySet()?.forEach { k ->
                        append('\n').append(n.extras?.get(k)?.toString().orEmpty())
                    }
                } catch (_: Exception) {
                }
            }
            if (cls.contains("Image", ignoreCase = true) || cls.contains("Photo", ignoreCase = true) ||
                cls.contains("ViewPager", ignoreCase = true)
            ) {
                listOf(desc, text, blob).forEach { s ->
                    if (s.startsWith("http")) out.add(cleanUrl(s))
                    urlRe.findAll(s).forEach { out.add(cleanUrl(it.value)) }
                }
            } else {
                imageUrlRe.findAll(blob).forEach { out.add(cleanUrl(it.value)) }
            }
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        return out.distinct().filter { looksLikeImage(it) }
    }

    fun nearestClickable(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        var cur = node
        var hops = 0
        while (cur != null && hops < 8) {
            if (cur.isClickable) return cur
            cur = cur.parent
            hops++
        }
        return node
    }

    fun click(node: AccessibilityNodeInfo?): Boolean {
        if (node == null) return false
        val target = nearestClickable(node) ?: node
        if (target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        return false
    }

    /** ACTION_CLICK 失败时，手势点节点中心（「查看全部 >」等常不可点） */
    suspend fun clickNode(service: AccessibilityService, node: AccessibilityNodeInfo?): Boolean {
        if (node == null) return false
        if (click(node)) return true
        val r = bounds(node)
        if (r.width() <= 0 || r.height() <= 0) return false
        return tap(service, r.exactCenterX(), r.exactCenterY())
    }

    suspend fun tap(service: AccessibilityService, x: Float, y: Float): Boolean =
        suspendCoroutine { cont ->
            val path = Path().apply { moveTo(x, y) }
            val stroke = GestureDescription.StrokeDescription(path, 0, 80)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()
            val ok = service.dispatchGesture(
                gesture,
                object : AccessibilityService.GestureResultCallback() {
                    override fun onCompleted(gestureDescription: GestureDescription?) {
                        cont.resume(true)
                    }

                    override fun onCancelled(gestureDescription: GestureDescription?) {
                        cont.resume(false)
                    }
                },
                null,
            )
            if (!ok) cont.resume(false)
        }

    suspend fun longPress(
        service: AccessibilityService,
        x: Float,
        y: Float,
        durationMs: Long = 1100,
    ): Boolean = suspendCoroutine { cont ->
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs.coerceAtLeast(600))
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val ok = service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    cont.resume(true)
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    cont.resume(false)
                }
            },
            null,
        )
        if (!ok) cont.resume(false)
    }

    fun longClickNode(node: AccessibilityNodeInfo?): Boolean {
        if (node == null) return false
        if (node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)) return true
        val t = nearestClickable(node) ?: node
        return t.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)
    }

    /** 详情页上方主图区域的 Image/Photo 节点 */
    fun findTopHeroImages(service: AccessibilityService, maxTop: Int = 1200): List<AccessibilityNodeInfo> {
        val out = mutableListOf<AccessibilityNodeInfo>()
        for (r in roots(service)) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val cls = n.className?.toString().orEmpty()
                val rect = bounds(n)
                val looksImg = cls.contains("Image", true) || cls.contains("Photo", true) ||
                    cls.contains("ViewPager", true) || cls.contains("Gallery", true)
                if (looksImg && rect.top in 80 until maxTop && rect.height() > 180 && rect.width() > 200) {
                    out.add(n)
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        return out.sortedBy { bounds(it).top }
    }

    fun setText(node: AccessibilityNodeInfo?, value: String): Boolean {
        if (node == null) return false
        var cur: AccessibilityNodeInfo? = node
        for (i in 0 until 6) {
            if (cur == null) break
            if (cur.isEditable || cur.className?.contains("EditText") == true) {
                val args = Bundle()
                args.putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    value
                )
                return cur.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            }
            cur = cur.parent
        }
        return false
    }

    fun findEditText(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (root == null) return null
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val cls = n.className?.toString() ?: ""
            if (n.isEditable || cls.contains("EditText")) return n
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        return null
    }

    fun screenRect(service: AccessibilityService): Rect {
        val dm = service.resources.displayMetrics
        return Rect(0, 0, dm.widthPixels, dm.heightPixels)
    }

    /**
     * 首页**顶部**搜索条（状态栏下方那条）。
     * 必须够宽且 top 落在屏幕上方约 16% 内；再往下的宽条多半是信息流「假搜索」，点了进不了输入页。
     */
    fun findHomeSearchBar(service: AccessibilityService): AccessibilityNodeInfo? {
        val screen = screenRect(service)
        // 真顶栏一般在 8%~16% 高度内；限制 maxTop，避免命中 y≈410 的信息流条
        val maxTop = (screen.height() * 0.16f).toInt().coerceIn(160, 420)
        val minWidth = (screen.width() * 0.42f).toInt()
        val candidates = mutableListOf<Pair<Int, AccessibilityNodeInfo>>()

        for (r in roots(service)) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val rect = bounds(n)
                val text = n.text?.toString().orEmpty()
                val desc = n.contentDescription?.toString().orEmpty()
                val hint = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    n.hintText?.toString().orEmpty()
                } else ""
                val viewId = n.viewIdResourceName.orEmpty().lowercase()
                val cls = n.className?.toString().orEmpty()
                val label = text + desc + hint
                val inTopBand = rect.top in 30 until maxTop && rect.bottom <= maxTop + 100
                val wideEnough = rect.width() >= minWidth
                val cameraOrScan = label.contains("拍照") || label.contains("扫码") ||
                    label.contains("相机") || label.contains("扫描") ||
                    label.contains("图像搜") || viewId.contains("camera") ||
                    viewId.contains("scan") || viewId.contains("photo")
                if (cameraOrScan) {
                    for (i in 0 until n.childCount) {
                        n.getChild(i)?.let { queue.add(it) }
                    }
                    continue
                }
                val searchId = viewId.contains("search") || viewId.contains("tv_search") ||
                    viewId.contains("search_bar") || viewId.contains("searchbar")
                val searchLabel = !label.contains("拍照") && (
                    desc == "搜索" || hint.contains("搜索") || text == "搜索" ||
                        label.contains("搜一搜") || label.contains("搜索商品") ||
                        (desc.contains("搜索") && wideEnough)
                    )
                // 仅顶栏热搜占位；不要把信息流卡片当搜索条
                val promoBar = inTopBand && wideEnough && (
                    label.contains("搜一搜") || label.contains("搜索商品") ||
                        (hint.contains("搜索") && text.length <= 40)
                    )
                val editTop = inTopBand && wideEnough && isSearchInputNode(n)
                if (inTopBand && wideEnough && (searchId || searchLabel || promoBar || editTop)) {
                    val score = rect.top * 10 - rect.width() + if (searchId || searchLabel || editTop) 0 else 50
                    candidates.add(score to n)
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        val best = candidates.minByOrNull { it.first }?.second ?: return null
        val br = bounds(best)
        // 双保险：中心点也不能掉到屏幕 18% 以下
        if (br.exactCenterY() > screen.height() * 0.18f) return null
        return best
    }

    fun isSearchInputNode(n: AccessibilityNodeInfo): Boolean {
        val cls = n.className?.toString().orEmpty()
        if (n.isEditable) return true
        if (cls.contains("EditText") || cls.contains("AutoComplete") ||
            cls.contains("SearchView") || cls.contains("TextField")
        ) {
            return true
        }
        val hint = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            n.hintText?.toString().orEmpty()
        } else ""
        val desc = n.contentDescription?.toString().orEmpty()
        return hint.contains("搜索") || desc.contains("搜索框") || desc.contains("搜索输入")
    }

    fun findTopEditText(service: AccessibilityService): AccessibilityNodeInfo? {
        val maxTop = (screenRect(service).height() * 0.35f).toInt().coerceIn(320, 900)
        var best: AccessibilityNodeInfo? = null
        var bestTop = Int.MAX_VALUE
        for (r in roots(service)) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                if (isSearchInputNode(n)) {
                    val top = bounds(n).top
                    if (top in 20 until maxTop && top < bestTop) {
                        bestTop = top
                        best = n
                    }
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        return best
    }

    suspend fun swipe(
        service: AccessibilityService,
        x: Float,
        y1: Float,
        y2: Float,
        durationMs: Long = 400,
    ): Boolean = swipeTo(service, x, y1, x + (Math.random() * 16 - 8).toFloat(), y2, durationMs)

    suspend fun swipeTo(
        service: AccessibilityService,
        x1: Float,
        y1: Float,
        x2: Float,
        y2: Float,
        durationMs: Long = 400,
    ): Boolean = suspendCoroutine { cont ->
        val path = Path().apply {
            moveTo(x1, y1)
            lineTo(x2, y2)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs.coerceAtLeast(80))
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        val ok = service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    cont.resume(true)
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    cont.resume(false)
                }
            },
            null,
        )
        if (!ok) cont.resume(false)
    }

    fun bounds(node: AccessibilityNodeInfo?): Rect {
        val r = Rect()
        node?.getBoundsInScreen(r)
        return r
    }

    fun visibleProductCards(root: AccessibilityNodeInfo?): List<AccessibilityNodeInfo> {
        if (root == null) return emptyList()
        val out = mutableListOf<Pair<Int, AccessibilityNodeInfo>>()
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        while (queue.isNotEmpty()) {
            val n = queue.removeFirst()
            val t = dumpText(n)
            val hasPrice = t.contains("¥") || t.contains("￥")
            val hasSales = t.contains("已拼") || t.contains("总售") || t.contains("付款")
            if (n.isClickable && hasPrice && t.length in 12..800 && (hasSales || t.length > 30)) {
                val top = bounds(n).top
                if (top > 80) out.add(top to n)
            }
            for (i in 0 until n.childCount) {
                n.getChild(i)?.let { queue.add(it) }
            }
        }
        return out.sortedBy { it.first }
            .map { it.second }
            .distinctBy {
                val r = bounds(it)
                "${r.left},${r.top},${r.right},${r.bottom}"
            }
    }

    fun parseListPrice(cardText: String): Double? {
        Regex("""[¥￥]\s*(\d+(?:\.\d{1,2})?)""")
            .find(cardText)?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let {
                if (it >= 0.1) return it
            }
        return null
    }

    fun parseGoodsId(text: String): String =
        goodsIdRe.find(text.replace("\\s+".toRegex(), ""))?.groupValues?.getOrNull(1).orEmpty()
}
