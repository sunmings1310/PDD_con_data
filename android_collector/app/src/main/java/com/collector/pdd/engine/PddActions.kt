package com.collector.pdd.engine

import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.view.accessibility.AccessibilityWindowInfo
import android.view.accessibility.AccessibilityNodeInfo
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.parser.DetailReader
import com.collector.pdd.service.A11yHelper
import com.collector.pdd.service.CollectA11yService
import com.collector.pdd.service.PasteOverlay
import com.collector.pdd.ui.MainActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.random.Random

/**
 * 拼多多 App 操作封装（文案定位 + 拟人节奏）。
 * 包名：com.xunmeng.pinduoduo
 */
class PddActions(
    private val log: (String) -> Unit,
    private val config: CollectConfig = CollectConfig(),
) {
    private val pkg = "com.xunmeng.pinduoduo"
    private val openedCardKeys = linkedSetOf<String>()
    private var activeSearchKeyword = ""

    private fun service(): CollectA11yService =
        CollectA11yService.instance ?: error("请先开启无障碍服务")

    private fun root(): AccessibilityNodeInfo =
        A11yHelper.root(service()) ?: error("无法读取当前界面")

    suspend fun openPdd() {
        HumanBehavior.pause(config, "think")
        val svc = service()
        val intent = svc.packageManager.getLaunchIntentForPackage(pkg)
            ?: Intent().apply {
                component = ComponentName(pkg, "com.xunmeng.pinduoduo.ui.activity.MainFrameActivity")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        svc.startActivity(intent)
        HumanBehavior.pause(config, "read")
        log("已拉起拼多多")
    }

    suspend fun searchKeyword(keyword: String) {
        if (activeSearchKeyword != keyword) {
            activeSearchKeyword = keyword
            openedCardKeys.clear()
        }
        HumanBehavior.pause(config, "think")
        // 不在首页且也不在搜索输入页时，先回首页
        val onSearchInput = A11yHelper.findTopEditText(service()) != null
        if (!onSearchInput && !isPddHome()) {
            log("当前非首页，先回拼多多首页再搜索…")
            goToPddHome()
        }
        if (!openSearchPage()) {
            log("未能打开搜索页，仍尝试输入关键词")
        }
        HumanBehavior.pause(config, "action")

        val edit = A11yHelper.findTopEditText(service())
            ?: A11yHelper.findEditText(root())
        var inputConfirmed = false
        if (edit != null) {
            A11yHelper.clickNode(service(), edit)
            HumanBehavior.sleepMs(250.0, 450.0)
            val ok = A11yHelper.setText(edit, keyword)
            log(if (ok) "已写入搜索词" else "写入搜索词失败，尝试粘贴")
            if (!ok) {
                try {
                    val cm = service().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(android.content.ClipData.newPlainText("kw", keyword))
                    HumanBehavior.sleepMs(150.0, 280.0)
                    edit.performAction(AccessibilityNodeInfo.ACTION_PASTE)
                } catch (_: Exception) {
                }
            }
            HumanBehavior.sleepMs(180.0, 300.0)
            edit.refresh()
            inputConfirmed = normalizedKeyword(edit.text?.toString().orEmpty()) == normalizedKeyword(keyword)
            log(if (inputConfirmed) "搜索词校验成功" else "搜索词校验失败，执行兜底输入")
            if (!inputConfirmed) inputConfirmed = tryInputKeywordFallback(keyword)
        } else {
            log("未找到搜索输入框，尝试剪贴板粘贴到焦点框")
            inputConfirmed = tryInputKeywordFallback(keyword)
        }
        if (!inputConfirmed) error("搜索词未成功写入：$keyword")
        HumanBehavior.pause(config, "action")

        submitSearch()
        dismissSearchKeyboard()
        if (!waitForSearchResult(keyword)) {
            log("首次提交后商品列表未就绪，重新提交搜索")
            submitSearch()
            dismissSearchKeyboard()
            if (!waitForSearchResult(keyword)) {
                val page = readPageText().replace("\n", " ").take(160)
                error("搜索结果页未就绪 page=$page")
            }
        }
        log("已搜索：$keyword")
    }

    private fun normalizedKeyword(value: String): String =
        value.replace("\\s+".toRegex(), "").lowercase()

    private suspend fun submitSearch(): Boolean {
        val go = findSearchSubmitButton()
        val ok = if (go != null) {
            A11yHelper.clickNode(service(), go)
        } else {
            val screen = A11yHelper.screenRect(service())
            A11yHelper.tap(service(), screen.width() * 0.92f, screen.height() * 0.075f)
        }
        HumanBehavior.sleepMs(650.0, 950.0)
        return ok
    }

    private suspend fun dismissSearchKeyboard() {
        try {
            val svc = service()
            val edit = A11yHelper.findTopEditText(svc)
            edit?.performAction(AccessibilityNodeInfo.ACTION_CLEAR_FOCUS)
            HumanBehavior.sleepMs(160.0, 260.0)
            val imeVisible = svc.windows.any {
                it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD && it.root != null
            }
            if (imeVisible) {
                log("搜索提交后输入法仍显示，执行一次返回收起")
                svc.performGlobalAction(
                    android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK,
                )
                HumanBehavior.sleepMs(250.0, 400.0)
            }
        } catch (e: Exception) {
            log("收起搜索输入法异常: ${e.message}")
        }
    }

    private suspend fun waitForSearchResult(keyword: String): Boolean {
        repeat(12) { round ->
            val page = readPageText()
            val cards = listCardsOrEmpty()
            val noResult = page.contains("暂无相关商品") || page.contains("没有找到相关商品") ||
                page.contains("换个词试试")
            val busy = page.contains("访问人数较多") || page.contains("网络繁忙") ||
                page.contains("稍后再试")
            if (cards.isNotEmpty() || looksLikeSearchList(page) || noResult || busy) {
                log("搜索结果已就绪 keyword=$keyword cards=${cards.size} wait=${round + 1}")
                return true
            }
            HumanBehavior.sleepMs(350.0, 550.0)
        }
        return false
    }

    /** 搜索页提交按钮：文案精确「搜索」，排除拍照/扫码 */
    private fun findSearchSubmitButton(): AccessibilityNodeInfo? {
        val maxTop = (A11yHelper.screenRect(service()).height() * 0.22f).toInt()
        val nodes = listOfNotNull(
            A11yHelper.findByText(root(), "搜索", exact = true, clickableOnly = true),
            A11yHelper.findByTextAllWindows(service(), "搜索", exact = true, clickableOnly = true),
            A11yHelper.findByContentDescAllWindows(service(), "搜索"),
        )
        for (n in nodes) {
            val lab = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
            if (lab.contains("拍照") || lab.contains("扫码") || lab.contains("相机")) continue
            val r = A11yHelper.bounds(n)
            if (r.top in 0 until maxTop && r.width() < A11yHelper.screenRect(service()).width() * 0.35f) {
                return n
            }
        }
        return null
    }

    private suspend fun tryInputKeywordFallback(keyword: String): Boolean {
        try {
            val cm = service().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(android.content.ClipData.newPlainText("kw", keyword))
            HumanBehavior.sleepMs(200.0, 350.0)
            val screen = A11yHelper.screenRect(service())
            // 点搜索页顶部输入带再粘贴
            A11yHelper.tap(service(), screen.width() * 0.40f, screen.height() * 0.08f)
            HumanBehavior.sleepMs(300.0, 500.0)
            val focused = A11yHelper.findTopEditText(service()) ?: A11yHelper.findEditText(root())
            if (focused != null) {
                focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
                if (A11yHelper.setText(focused, keyword)) {
                    log("兜底写入搜索词成功")
                    return true
                }
            }
            log("兜底粘贴仍未确认输入框")
        } catch (e: Exception) {
            log("兜底输入失败: ${e.message}")
        }
        return false
    }

    private fun hasSearchInput(): Boolean =
        A11yHelper.findTopEditText(service()) != null ||
            runCatching { A11yHelper.findEditText(root()) }.getOrNull() != null

    /** 首页热搜条：只点真正顶栏；信息流假搜索条一律改用顶栏比例坐标 */
    private suspend fun openSearchPage(): Boolean {
        if (hasSearchInput()) {
            log("已在搜索输入页")
            return true
        }
        val screen = A11yHelper.screenRect(service())
        // 先回首页顶，避免停在信息流中部
        clickBottomHomeTab()
        HumanBehavior.sleepMs(350.0, 600.0)

        val bar = A11yHelper.findHomeSearchBar(service())
        if (bar != null) {
            val r = A11yHelper.bounds(bar)
            val x = (r.left + r.width() * 0.35f).coerceIn(screen.width() * 0.18f, screen.width() * 0.55f)
            // 用条带真实中心，不再强行压到 0.16 导致点到条带上沿外
            val y = r.exactCenterY().toFloat()
            log(
                "点击首页顶栏搜索条 xy=${x.toInt()},${y.toInt()} " +
                    "bounds=${r.left},${r.top},${r.right},${r.bottom} screen=${screen.width()}x${screen.height()}"
            )
            A11yHelper.tap(service(), HumanBehavior.jitter(x, 12f), HumanBehavior.jitter(y, 6f))
            HumanBehavior.sleepMs(900.0, 1300.0)
            if (hasSearchInput()) {
                log("已进入搜索输入页")
                return true
            }
        } else {
            log("未识别可靠顶栏搜索条，改用比例坐标 screen=${screen.width()}x${screen.height()}")
        }

        // 多档顶栏 y（适配刘海/大屏）；略偏左避开拍照搜
        for (yf in listOf(0.055f, 0.07f, 0.085f, 0.10f, 0.12f)) {
            val x = screen.width() * 0.38f
            val y = screen.height() * yf
            log("顶栏比例点击搜索 xy=${x.toInt()},${y.toInt()} yRatio=$yf")
            A11yHelper.tap(service(), HumanBehavior.jitter(x, 18f), HumanBehavior.jitter(y, 8f))
            HumanBehavior.sleepMs(750.0, 1100.0)
            if (hasSearchInput()) {
                log("比例点击进入搜索页 yRatio=$yf")
                return true
            }
        }
        // 最后再点一次底栏首页后重试最上两档
        clickBottomHomeTab()
        HumanBehavior.sleepMs(500.0, 800.0)
        for (yf in listOf(0.06f, 0.08f)) {
            A11yHelper.tap(
                service(),
                HumanBehavior.jitter(screen.width() * 0.40f, 16f),
                HumanBehavior.jitter(screen.height() * yf, 8f),
            )
            HumanBehavior.sleepMs(800.0, 1200.0)
            if (hasSearchInput()) {
                log("回首页后进入搜索页 yRatio=$yf")
                return true
            }
        }
        return false
    }

    suspend fun scrollList(rounds: Int = 2) {
        val n = HumanBehavior.listScrollRounds(rounds)
        repeat(n) {
            humanSwipe(
                HumanBehavior.jitter(540f, 40f),
                HumanBehavior.jitter(1500f, 80f),
                HumanBehavior.jitter(700f, 80f),
                purpose = "list",
            )
            HumanBehavior.pause(config, "action")
            if (HumanBehavior.shouldBackscroll(config)) {
                humanSwipe(
                    HumanBehavior.jitter(540f, 30f),
                    HumanBehavior.jitter(900f, 60f),
                    HumanBehavior.jitter(1300f, 60f),
                    purpose = "list",
                )
            }
        }
    }

    suspend fun sortByPriceAsc() {
        clickSortTab("价格")
        HumanBehavior.pause(config, "action")
        // 再点一次切升序（有的版本点两次）
        clickSortTab("价格")
        HumanBehavior.pause(config, "read")
        log("已尝试价格排序")
    }

    suspend fun sortBySalesDesc() {
        clickSortTab("销量")
        HumanBehavior.pause(config, "read")
        log("已尝试销量排序")
    }

    private suspend fun clickSortTab(name: String) {
        val n = A11yHelper.findByText(root(), name, exact = true, clickableOnly = true)
            ?: A11yHelper.findByText(root(), name, exact = false, clickableOnly = true)
        if (n != null) {
            A11yHelper.clickNode(service(), n)
        } else {
            log("未找到排序入口：$name")
        }
    }

    private suspend fun humanSwipe(x: Float, y1: Float, y2: Float, purpose: String = "list") {
        A11yHelper.swipe(
            service(),
            x,
            y1,
            y2,
            HumanBehavior.swipeDurationMs(purpose),
        )
    }

    /** Virtualized result lists must move forward deterministically. */
    private suspend fun scrollListForward(rounds: Int = 1) {
        repeat(rounds.coerceIn(1, 4)) {
            humanSwipe(
                HumanBehavior.jitter(540f, 35f),
                HumanBehavior.jitter(1500f, 70f),
                HumanBehavior.jitter(650f, 70f),
                purpose = "list",
            )
            HumanBehavior.pause(config, "action")
        }
    }

    private fun currentProductCards(): List<AccessibilityNodeInfo> {
        val roots = A11yHelper.roots(service()).filter {
            it.packageName?.toString() == pkg
        }
        return roots.flatMap { A11yHelper.visibleProductCards(it) }
            .distinctBy {
                val r = A11yHelper.bounds(it)
                "${r.left},${r.top},${r.right},${r.bottom}"
            }
            .sortedBy { A11yHelper.bounds(it).top }
    }

    fun listCards(): List<AccessibilityNodeInfo> = currentProductCards()

    /** 页面切换/悬浮窗刚关闭时 root 可能短暂为 null，列表恢复流程必须容忍该窗口。 */
    fun listCardsOrEmpty(): List<AccessibilityNodeInfo> {
        return try {
            currentProductCards()
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun peekCardMeta(index: Int): ListCardMeta {
        val cards = listCards()
        if (index !in cards.indices) return ListCardMeta()
        val card = cards[index]
        val text = A11yHelper.dumpText(card)
        val harvest = A11yHelper.harvestIdsAndUrls(card)
        val title = text.lines().map { it.trim() }
            .firstOrNull { it.length >= 6 && !it.startsWith("¥") && !it.startsWith("￥") }
            .orEmpty()
        return ListCardMeta(
            listPrice = A11yHelper.parseListPrice(text),
            itemId = harvest.goodsId.ifBlank { A11yHelper.parseGoodsId(text) },
            imageHint = harvest.images.firstOrNull().orEmpty(),
            titleHint = title.take(80),
        )
    }

    suspend fun openCardAt(index: Int): Pair<Boolean, ListCardMeta> {
        HumanBehavior.pause(config, "think")
        var cards = listCardsOrEmpty()
        repeat(6) {
            if (cards.isNotEmpty()) return@repeat
            HumanBehavior.sleepMs(300.0, 500.0)
            cards = listCardsOrEmpty()
        }
        if (cards.isEmpty()) {
            val page = readPageText().replace("\n", " ").take(140)
            log("列表为空，无法打开第 ${index + 1} 个 page=$page")
            return false to ListCardMeta()
        }
        fun keys(): List<String> = cards.indices.map { visibleIndex ->
            cardKey(peekCardMeta(visibleIndex), visibleIndex)
        }
        var chosen = chooseUnseenCardIndex(keys(), openedCardKeys, index)
        if (chosen == null) {
            for (round in 0 until 8) {
                scrollListForward(1)
                cards = listCardsOrEmpty()
                chosen = chooseUnseenCardIndex(keys(), openedCardKeys, preferredIndex = -1)
                if (chosen != null) break
            }
        }
        val selected = chosen
        if (selected == null || selected !in cards.indices) {
            log("列表翻页后仍无未采集商品（目标序号 ${index + 1}，当前可见 ${cards.size}）")
            return false to ListCardMeta()
        }
        val meta = peekCardMeta(selected)
        val ok = A11yHelper.click(listCards().getOrNull(selected) ?: cards[selected])
        if (ok) openedCardKeys += cardKey(meta, selected)
        HumanBehavior.pause(config, "read")
        log(
            "进入详情 index=${index + 1} visible=${selected + 1} ok=$ok listPrice=${meta.listPrice ?: "-"} " +
                "idHint=${meta.itemId.ifBlank { "-" }}"
        )
        return ok to meta
    }

    private fun cardKey(meta: ListCardMeta, visibleIndex: Int): String = meta.itemId.ifBlank {
        "${meta.titleHint}|${meta.listPrice ?: "-"}|${meta.imageHint}|$visibleIndex"
    }

    fun readPageText(): String = A11yHelper.dumpAllWindows(service())

    fun harvestPage(): A11yHelper.Harvest = A11yHelper.harvestAllWindows(service())

    /**
     * 轻量回顶：默认只滑 1 次，避免反复加载详情增加风控。
     * @param maxRounds 最多上滑次数（1~2）
     */
    suspend fun scrollToTop(maxRounds: Int = 1) {
        val n = maxRounds.coerceIn(1, 2)
        repeat(n) {
            val page = readPageText()
            // 已在详情上部（能看到主图区/顶部分享）则不再狂滑
            if (looksLikeGoodsDetail(page) &&
                (page.contains("分享") || Regex("""\d+/\d+""").containsMatchIn(page.replace("\\s+".toRegex(), "")))
            ) {
                return
            }
            val dm = service().resources.displayMetrics
            humanSwipe(
                HumanBehavior.jitter(dm.widthPixels * 0.5f, 30f),
                HumanBehavior.jitter(dm.heightPixels * 0.28f, 40f),
                HumanBehavior.jitter(dm.heightPixels * 0.72f, 50f),
                purpose = "detail",
            )
            HumanBehavior.sleepMs(200.0, 400.0)
        }
    }

    /**
     * 点底栏打开规格弹层读多规格售价（不提交订单）。
     * 模式A：规格旁直接带 ¥价；
     * 模式B：逐个点规格，读顶部主价（含「确认款式」里 ¥xx + 已选择:N盒装）或到手价/提交订单价。
     */
    suspend fun openAndReadSkuPrices(): String {
        log("======== 开始读取多规格售价 ========")
        HumanBehavior.pause(config, "action")
        // 详情页本身不能当成规格弹层（标题里常有「1瓶/盒」会误匹配）
        if (looksLikeGoodsDetail() && !isSkuPanel(readPageText())) {
            // ok，准备去点底栏打开
        }
        if (!openSkuPanel()) {
            log("未打开规格弹层")
            return ""
        }
        HumanBehavior.sleepMs(500.0, 800.0)
        var panel = readPageText()
        if (!isSkuPanel(panel)) {
            log("打开后不是规格弹层，取消读价（避免误按返回退出详情） preview=${panel.replace("\n", " ").take(80)}")
            if (looksLikePureAddressCheckout(panel)) {
                log("误入纯地址下单页，返回详情…")
                goBackQuiet()
            }
            return ""
        }
        // 模式A：文案里已带各规格价
        var inline = DetailReader.buildSkuFromPanel(panel)
        val options = listSkuOptionLabels()
        // 「感冒用药【1盒】」/ 套餐 1盒 2盒 3盒：价在顶部或提交订单按钮，必须逐个点
        val packageStyle = options.any { it.first.contains("【") || it.first.contains("[") } ||
            panel.contains("套餐") ||
            Regex("""【\s*[一二两三四五六七八九十百\d]+\s*盒\s*】""").containsMatchIn(panel)
        val inlineCount = inline.split("|").map { it.trim() }.count { it.isNotBlank() }
        val confirmStylePanel = panel.contains("确认款式") || panel.contains("包装数量") ||
            panel.contains("一次选多款") ||
            (panel.contains("已选") && Regex("""\d+盒""").containsMatchIn(panel.replace("\\s+".toRegex(), "")))
        // 确认款式：选项带「最后N件」时也要强制逐个点，从上方 ¥ / 已选择 取价
        val clickOptions = if (options.size >= 2) options else listSkuOptionLabels()
        val needClickMode = confirmStylePanel || packageStyle || (
            clickOptions.size >= 2 && (
                inlineCount < clickOptions.size ||
                    panel.contains("到手价") ||
                    panel.contains("提交订单") ||
                    panel.contains("一次选多款") ||
                    (panel.contains("组合") && !Regex("""盒装?[^\n]{0,8}[¥￥]""").containsMatchIn(panel))
                )
            )
        if ((needClickMode && clickOptions.isNotEmpty()) || (inline.isBlank() && clickOptions.size >= 2)) {
            log(
                "多规格模式B：逐个点击规格读上方价（共${clickOptions.size}个）" +
                    "${if (packageStyle) " [套餐型]" else ""}" +
                    "${if (confirmStylePanel) " [确认款式/包装数量]" else ""}"
            )
            val clicked = readSkuPricesByClickingEach(clickOptions)
            if (clicked.isNotBlank()) {
                inline = DetailReader.buildSkuFromPanel(clicked).ifBlank {
                    // 点击结果已是「名称 ¥价」行，再归一
                    clicked.lines().mapNotNull { line ->
                        val m = Regex("""^(.+?)\s*[¥￥]\s*(\d+(?:\.\d{1,2})?)\s*$""").find(line.trim())
                            ?: return@mapNotNull null
                        "${m.groupValues[1].trim()}(售价¥${m.groupValues[2]})"
                    }.joinToString(" | ").ifBlank { inline }
                }
                panel = panel + "\n" + clicked
            }
        }
        log(
            if (inline.isNotBlank()) "多规格解析: ${inline.take(180)}"
            else "规格弹层已开，但未解析到规格价 preview=${panel.replace("\n", " ").take(100)}"
        )
        closeSkuPanel()
        log("======== 多规格读取结束 ========")
        if (inline.isBlank()) return panel
        val synthetic = inline.split("|").map { it.trim() }.filter { it.isNotBlank() }.joinToString("\n") { part ->
            val m = Regex("""^(.+?)\(售价¥([\d.]+)\)$""").find(part)
            if (m != null) "${m.groupValues[1]} ¥${m.groupValues[2]}" else part
        }
        return panel + "\n" + synthetic
    }

    /**
     * 规格按钮文案：
     * - 5盒装 / 10盒装 / 一盒（可带「最后10件」后缀，需剥掉后再认）
     * - 感冒用药【1盒】/ 感冒用药【5盒】（套餐型）
     */
    private fun listSkuOptionLabels(): List<Pair<String, AccessibilityNodeInfo>> {
        val out = linkedMapOf<String, AccessibilityNodeInfo>()
        for (r in A11yHelper.roots(service())) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val t = (n.text?.toString() ?: "").trim().replace("\\s+".toRegex(), "")
                val d = (n.contentDescription?.toString() ?: "").trim().replace("\\s+".toRegex(), "")
                val label = normalizeSkuOptionLabel(t).ifBlank { normalizeSkuOptionLabel(d) }
                if (label.isNotBlank()) {
                    val target = A11yHelper.nearestClickable(n) ?: n
                    out.putIfAbsent(label, target)
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        // 整页补扫：包装数量区的「N盒装」（确认款式常见）
        val page = readPageText().replace("\\s+".toRegex(), "")
        if (out.size < 2 || page.contains("确认款式") || page.contains("包装数量")) {
            val names = mutableListOf<String>()
            Regex("""(\d+盒装)""").findAll(page).forEach { names.add(it.groupValues[1]) }
            Regex("""([^\n【]{0,24}【[一二两三四五六七八九十百\d]+[盒瓶袋件]】)""")
                .findAll(page)
                .forEach { names.add(it.groupValues[1]) }
            for (rawName in names.distinct()) {
                val name = normalizeSkuOptionLabel(rawName).ifBlank { rawName }
                if (!isSkuOptionLabel(name) || out.containsKey(name)) continue
                val node = A11yHelper.findByTextAllWindows(service(), name, exact = false, clickableOnly = true)
                    ?: A11yHelper.findByTextAllWindows(service(), name, exact = false, clickableOnly = false)
                    ?: A11yHelper.findByTextAllWindows(service(), rawName, exact = false, clickableOnly = false)
                if (node != null) {
                    out.putIfAbsent(name, A11yHelper.nearestClickable(node) ?: node)
                }
            }
        }
        log("识别到规格选项: ${out.keys.joinToString(" / ").ifBlank { "(无)" }}")
        return out.entries.map { it.key to it.value }
    }

    /** 剥掉「最后10件/仅剩x件」等库存尾巴，得到纯规格名「1盒装」 */
    private fun normalizeSkuOptionLabel(raw: String): String {
        var t = raw.trim().replace("\\s+".toRegex(), "")
        if (t.isBlank()) return ""
        t = t.replace(Regex("""最后\d+件.*$"""), "")
            .replace(Regex("""仅剩?\d+件.*$"""), "")
            .replace(Regex("""还剩\d+件.*$"""), "")
            .replace(Regex("""库存\d+.*$"""), "")
        // 「1盒装最后10件」剥完后可能仍连在一起时，只取前导规格
        Regex("""^([一二两三四五六七八九十百\d]+[盒瓶袋件](?:装)?)""").find(t)?.let {
            if (isSkuOptionLabel(it.groupValues[1])) return it.groupValues[1]
        }
        return if (isSkuOptionLabel(t)) t else ""
    }

    private fun isSkuOptionLabel(raw: String): Boolean {
        val t = raw.trim().replace("\\s+".toRegex(), "")
        if (t.length !in 2..48) return false
        if (t.contains("提交订单") || t.startsWith("已选") || t.contains("包装数量") ||
            t.contains("一次选多款") || t.contains("到手价") || t.contains("快要抢光") ||
            t.contains("单独购买") || t.contains("免拼购买") || t.contains("发起拼单") ||
            t.contains("人选择") || t.contains("%") || t == "确定" || t.contains("确认款式")
        ) {
            return false
        }
        // 感冒用药【1盒】/ 【2瓶】
        if (Regex("""^.{0,24}【[一二两三四五六七八九十百\d]+[盒瓶袋件]】$""").matches(t)) return true
        // 1盒 / 2盒 / 5盒装 / 一盒 / 2瓶（确认款式「包装数量」）
        if (Regex("""^[一二两三四五六七八九十百\d]+[盒瓶袋件](?:装)?$""").matches(t)) return true
        if (Regex("""^\d+盒\d+袋$""").matches(t)) return true
        return false
    }

    /** 模式B：点每个规格，读上方主价（已选择旁 ¥）/ 到手价 / 提交订单价 */
    private suspend fun readSkuPricesByClickingEach(
        options: List<Pair<String, AccessibilityNodeInfo>>,
    ): String {
        val lines = mutableListOf<String>()
        for ((name, node) in options.take(12)) {
            log("点击规格：$name")
            val short = Regex("""【[一二两三四五六七八九十百\d]+盒】""").find(name)?.value
            val fresh = A11yHelper.findByTextAllWindows(service(), name, exact = false, clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), name, exact = false, clickableOnly = false)
                // 「1盒装最后10件」整段文案
                ?: A11yHelper.findByTextAllWindows(service(), name + "最后", exact = false, clickableOnly = false)
                ?: short?.let {
                    A11yHelper.findByTextAllWindows(service(), it, exact = false, clickableOnly = true)
                        ?: A11yHelper.findByTextAllWindows(service(), it, exact = false, clickableOnly = false)
                }
                ?: node
            A11yHelper.clickNode(service(), A11yHelper.nearestClickable(fresh) ?: fresh)
            HumanBehavior.sleepMs(800.0, 1300.0)
            val page = readPageText()
            val price = extractSelectedSkuPrice(page, selectedName = name)
            if (price != null) {
                lines.add("$name ¥${DetailReader.trimPriceNum(price)}")
                log("规格 $name → 上方价 ¥$price")
            } else {
                log("规格 $name 未读到上方价格 preview=${page.replace("\n", " ").take(100)}")
            }
            if (Random.nextDouble() < 0.35) {
                HumanBehavior.pause(config, "think")
            }
        }
        return lines.joinToString("\n")
    }

    /**
     * 规格弹层取价前清洗。
     * - 「最后2件」粘到价后 → ¥772
     * - 「2件9.9折」不能吃掉价格末位（¥23件9.9折 误成 ¥2）
     */
    private fun sanitizeSkuPriceContext(text: String): String {
        var s = text.replace("\\s+".toRegex(), "")
        // 价 + 促销件数 + 折/包邮：¥232件9.9折 → ¥23
        s = s.replace(Regex("""([¥￥]\d+\.\d{1,2})(\d{1,2})件\d+(?:\.\d+)?折"""), "$1")
            .replace(Regex("""([¥￥]\d+)(\d{1,2})件\d+(?:\.\d+)?折"""), "$1")
            .replace(Regex("""([¥￥]\d+\.\d{1,2})(\d{1,2})件包邮"""), "$1")
            .replace(Regex("""([¥￥]\d+)(\d{1,2})件包邮"""), "$1")
        // 价尾已粘上与「最后N件」相同的 N：¥772最后2件
        s = s.replace(Regex("""([¥￥]\d+\.\d?)(\d)最后\2件"""), "$1")
            .replace(Regex("""([¥￥]\d*?)(\d{1,2})最后\2件"""), "$1")
        // 价后紧跟「最后N件」（N 未进价）
        s = s.replace(Regex("""([¥￥]\d+\.\d{1,2})最后\d{1,2}件"""), "$1")
            .replace(Regex("""([¥￥]\d+)最后\d{1,2}件"""), "$1")
        // 其余库存角标
        s = s.replace(Regex("""最后\d+件"""), "#")
            .replace(Regex("""仅剩?\d+件"""), "#")
            .replace(Regex("""还剩\d+件"""), "#")
        // 独立促销：禁止从 ¥ 价格数字内部开切
        s = s.replace(Regex("""(^|[^¥￥\d])([1-9]\d?)件\d+(?:\.\d+)?折"""), "$1#")
            .replace(Regex("""(^|[^¥￥\d])([1-9]\d?)件包邮"""), "$1#")
        return s
    }


    private fun parseYenPrices(context: String): List<Double> {
        val out = mutableListOf<Double>()
        Regex("""[¥￥](\d+\.\d{1,2})(?![\d])""").findAll(context).forEach { m ->
            m.groupValues[1].toDoubleOrNull()?.let { out.add(it) }
        }
        Regex("""[¥￥](\d+)(?![\d.])(?!件)""").findAll(context).forEach { m ->
            m.groupValues[1].toDoubleOrNull()?.let { out.add(it) }
        }
        return out.filter { it in 0.01..99999.0 }
    }

    /**
     * 当前选中规格价。
     * 「确认款式」：券后¥50.9 / 缩略图旁 ¥ + 已选择（价不在选项按钮上）。
     */
    private fun extractSelectedSkuPrice(page: String, selectedName: String = ""): Double? {
        val compact = sanitizeSkuPriceContext(page)
        val nameCompact = selectedName.replace("\\s+".toRegex(), "")
        fun ok(p: Double?) = p != null && p in 0.01..99999.0

        // 确认款式顶栏：优先券后价，其次券前
        Regex("""券后[价]?[¥￥]?(\d+\.\d{1,2}|\d+)(?![\d])""").find(compact)
            ?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let { if (ok(it)) return it }
        Regex("""券前[¥￥]?(\d+\.\d{1,2}|\d+)(?![\d])""").find(compact)
            ?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let { if (ok(it)) return it }

        Regex("""提交订单[¥￥](\d+\.\d{1,2}|\d+)(?![\d])(?!件)""").find(compact)
            ?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let { if (ok(it)) return it }
        Regex("""到手价[¥￥](\d+\.\d{1,2}|\d+)(?![\d])(?!件)""").find(compact)
            ?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let { if (ok(it)) return it }

        val idxSelected = compact.indexOf("已选")
        if (idxSelected >= 0) {
            val before = compact.substring(0, idxSelected).takeLast(100)
            val prices = parseYenPrices(before)
            val prefer = prices.lastOrNull { it != it.toLong().toDouble() } ?: prices.lastOrNull()
            if (ok(prefer)) return prefer
        }

        if (nameCompact.isNotBlank()) {
            val idx = compact.indexOf("已选")
            if (idx >= 0) {
                val window = compact.substring(idx, (idx + 48).coerceAtMost(compact.length))
                val packInWindow = Regex("""\d+盒(?:装)?""").find(window)?.value.orEmpty()
                if (window.contains(nameCompact) ||
                    (packInWindow.isNotBlank() &&
                        (nameCompact.contains(packInWindow) || packInWindow.contains(nameCompact)))
                ) {
                    val before = compact.substring(0, idx).takeLast(80)
                    parseYenPrices(before).lastOrNull()?.let { if (ok(it)) return it }
                }
            }
        }

        if (compact.contains("已选") || compact.contains("套餐") || compact.contains("确认款式") ||
            compact.contains("包装数量") || compact.contains("一次选多款")
        ) {
            val prices = parseYenPrices(compact)
            val prefer = prices.firstOrNull { it != it.toLong().toDouble() && it in 0.5..9999.0 }
                ?: prices.firstOrNull { it in 0.5..9999.0 }
            if (ok(prefer)) return prefer
        }
        return null
    }

    /** 统计弹层里互不相同的「N盒/N盒装」选项数 */
    private fun countBoxSkuOptions(compact: String): Int =
        Regex("""\d+盒(?:装)?""").findAll(compact).map { it.value }.distinct().count()

    /**
     * 规格采集弹层。
     * 用户确认：点击购买后弹出的界面（含「套餐 1盒/2盒…」「已选」「提交订单」，
     * 即便带「拼多多全程保障」顶栏）都算规格界面。
     */
    private fun isSkuPanel(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        val boxOpts = countBoxSkuOptions(t)
        val packageOpts = Regex("""【[一二两三四五六七八九十百\d]+[盒瓶袋件]】""").findAll(t).count()

        // 通用商品规格弹层：口罩等商品使用「颜色/尺码/款式」而不是药品的 N盒装。
        // 任务 53 的现场同时出现「请选择：颜色」和「选择颜色后，立即支付」。
        val chooseHeader = Regex("""请选择[:：][^，。\n]{1,16}""").containsMatchIn(t)
        val payAfterChoose = Regex("""选择[^，。\n]{1,16}后[,，]?立即(?:支付|购买)""").containsMatchIn(t)
        val genericAttribute = listOf("颜色", "尺码", "规格", "款式", "型号", "数量", "容量", "套餐")
            .any { attr -> t.contains("请选择：$attr") || t.contains("请选择:$attr") }
        if (chooseHeader && payAfterChoose) return true
        if (genericAttribute && t.contains("立即支付")) return true

        // 任务 55 的口罩商品在规格已选中后不再显示「请选择」，而是显示
        // 「已选 + 型号 + 加减数量 + 0元下单/确认收货后付款」。该组合必须仍被识别为规格弹层，
        // 否则采图返回时会把弹层当成未知页面，连续 restore_detail 异常后自动终止任务。
        val selectedHeader = Regex("""已(?:选|选择)[:：][^\n]{2,160}""").containsMatchIn(t)
        val genericDimension = listOf("型号", "颜色", "尺码", "规格", "款式", "容量", "套餐")
            .any { t.contains(it) }
        val quantityControls = t.contains("减少数量") && t.contains("增加数量")
        val checkoutCta = listOf("0元下单", "确认收货后付款", "提交订单", "立即支付", "立即购买")
            .any { t.contains(it) }
        val bracketOptions = Regex("""【[^】]{2,80}】""").findAll(t).map { it.value }.distinct().count()
        if (selectedHeader && genericDimension && checkoutCta && (quantityControls || bracketOptions >= 2)) {
            return true
        }

        // 套餐弹层（截图形态）
        if (t.contains("套餐") && boxOpts >= 2) return true
        if (t.contains("一次选多款") && (boxOpts >= 1 || t.contains("提交订单"))) return true
        if (t.contains("提交订单") && boxOpts >= 2) return true
        if ((t.contains("已选") || t.contains("已选择")) && boxOpts >= 2) return true

        if (t.contains("确认款式") || t.contains("包装数量")) {
            return t.contains("¥") || t.contains("￥") || t.contains("确定") || t.contains("提交订单")
        }
        if (packageOpts >= 2 && (t.contains("提交订单") || t.contains("到手价") || t.contains("组合") || t.contains("套餐"))) {
            return true
        }
        if (t.contains("到手价") && (boxOpts >= 1 || packageOpts >= 1) &&
            (t.contains("尺寸") || t.contains("款式") || t.contains("组合") || t.contains("套餐"))
        ) {
            return true
        }
        // 纯地址下单（无套餐选项）不算规格
        if (looksLikePureAddressCheckout(text)) return false
        return false
    }

    /** 仅地址/支付确认、没有任何套餐多盒选项时，才算误入 */
    private fun looksLikePureAddressCheckout(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        if (t.contains("套餐") || countBoxSkuOptions(t) >= 2 || t.contains("一次选多款")) return false
        return (t.contains("填写地址") || t.contains("选择地址")) ||
            (t.contains("拼多多全程保障") && t.contains("提交订单") && countBoxSkuOptions(t) < 2 && !t.contains("套餐"))
    }

    /** @deprecated 兼容旧名 */
    private fun looksLikeCheckoutSheet(text: String): Boolean = looksLikePureAddressCheckout(text)

    private suspend fun tapScreenCenter50() {
        val screen = A11yHelper.screenRect(service())
        val x = HumanBehavior.jitter(screen.width() * 0.50f, 16f)
        val y = HumanBehavior.jitter(screen.height() * 0.50f, 20f)
        log("点击屏幕中部50% (${x.toInt()},${y.toInt()})")
        A11yHelper.tap(service(), x, y)
    }

    private suspend fun openSkuPanel(): Boolean {
        val before = readPageText()
        if (isSkuPanel(before)) return true
        // 仅点击明确的规格选择入口。禁止把购买、拼单、开药按钮当作规格入口，
        // 也不再用底部随机/坐标点击兜底，确保采集动作不会主动进入下单界面。
        val buttons = findSkuOpenButtons()
        if (buttons.isEmpty()) {
            log("未找到明确规格选择入口，跳过多规格读取（禁止点击购买/下单区域）")
            return false
        }
        for ((lab, node) in buttons) {
            log("点击明确规格入口：$lab".take(48))
            A11yHelper.clickNode(service(), A11yHelper.nearestClickable(node) ?: node)
            HumanBehavior.sleepMs(900.0, 1400.0)
            var page = readPageText()
            if (isSkuPanel(page)) {
                log("已打开规格采集弹层")
                return true
            }
            if (looksLikePureAddressCheckout(page)) {
                log("规格入口异常进入下单页，立即返回并停止本轮规格读取")
                goBackQuiet()
                HumanBehavior.sleepMs(500.0, 850.0)
                return false
            }
            // 任务 56：某些无多规格商品点击「免拼购买/单独购买」会直接离开详情。
            // 此时旧逻辑仍点击下一枚已失效节点并继续坐标兜底，最终把页面推进到系统空窗口。
            // 一旦当前页既不是规格弹层也不是商品详情，只允许返回一次；恢复失败就终止本轮读规格。
            if (!isSkuPanel(page) && !looksLikeGoodsDetail(page)) {
                log("规格入口点击后已离开商品详情，立即返回并停止继续点击失效入口")
                goBackQuiet()
                HumanBehavior.sleepMs(500.0, 850.0)
                val restored = readPageText()
                if (isSkuPanel(restored)) return true
                if (!looksLikeGoodsDetail(restored)) {
                    log("规格入口返回后仍未恢复商品详情，停止规格入口重试")
                    return false
                }
                log("已返回商品详情，本商品停止继续尝试其他规格入口")
                return false
            }
        }
        log("明确规格入口未打开弹层，保持商品详情并结束本轮规格读取")
        return false
    }

    /**
     * 只收集明确的规格选择按钮；购买/下单/拼单/支付/开药入口一律排除。
     */
    private fun findSkuOpenButtons(): List<Pair<String, AccessibilityNodeInfo>> {
        val keywords = listOf("选择规格", "选规格", "请选择", "已选择", "已选")
        val forbidden = listOf("购买", "下单", "发起拼单", "直接拼成", "提交订单", "支付", "开药")
        val screen = A11yHelper.screenRect(service())
        data class Hit(val score: Int, val label: String, val node: AccessibilityNodeInfo)
        val hits = mutableListOf<Hit>()
        for (r in A11yHelper.roots(service())) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val t = ((n.text?.toString() ?: "") + " " + (n.contentDescription?.toString() ?: ""))
                    .replace("\\s+".toRegex(), "")
                val kw = keywords.firstOrNull { t.contains(it) }
                if (kw != null && forbidden.none { t.contains(it) }) {
                    val b = A11yHelper.bounds(n)
                    val target = A11yHelper.nearestClickable(n) ?: n
                    var score = when (kw) {
                        "选择规格", "选规格" -> 100
                        "请选择" -> 95
                        "已选择" -> 90
                        else -> 85
                    }
                    if (b.width() > 0 && b.height() > 0) score += 10
                    if (b.top in (screen.height() * 0.12f).toInt()..(screen.height() * 0.90f).toInt()) score += 5
                    hits.add(Hit(score, t.ifBlank { kw }.take(40), target))
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        // 同文案去重，按分数
        val best = linkedMapOf<String, Hit>()
        for (h in hits.sortedByDescending { it.score }) {
            val key = keywords.firstOrNull { h.label.contains(it) } ?: h.label
            best.putIfAbsent(key, h)
        }
        return best.values.sortedByDescending { it.score }.map { it.label to it.node }
    }

    private suspend fun closeSkuPanel() {
        // 回详情路上若出现「逛逛」，立刻点掉（含继续逛逛/再逛逛等）
        if (dismissContinueBrowsePopup()) {
            HumanBehavior.sleepMs(400.0, 650.0)
            if (looksLikeGoodsDetail(readPageText()) && !isSkuPanel(readPageText())) {
                log("点击含「逛逛」后已回商品详情")
                return
            }
        }
        repeat(2) {
            val page = readPageText()
            if (pageContainsGuangGuang(page) && dismissContinueBrowsePopup()) {
                HumanBehavior.sleepMs(400.0, 650.0)
                if (looksLikeGoodsDetail(readPageText()) && !isSkuPanel(readPageText())) return
            }
            // 已在详情且不像规格弹层：绝不能再 Back（曾误把详情当弹层直接退到列表）
            if (looksLikeGoodsDetail(page) && !isSkuPanel(page) && !pageContainsGuangGuang(page)) {
                log("已在商品详情，跳过关闭规格返回")
                return
            }
            if (!isSkuPanel(page) && !looksLikePureAddressCheckout(page) &&
                !pageContainsGuangGuang(page)
            ) {
                return
            }
            log("关闭规格弹层…")
            // 优先点弹层右上角 X/关闭，避免系统 Back 退详情
            val close = A11yHelper.findByContentDescAllWindows(service(), "关闭")
                ?: A11yHelper.findByTextAllWindows(service(), "关闭", exact = true, clickableOnly = true)
            if (close != null) {
                val r = A11yHelper.bounds(close)
                if (r.top < 900) {
                    A11yHelper.clickNode(service(), close)
                } else {
                    goBackQuiet()
                }
            } else {
                goBackQuiet()
            }
            HumanBehavior.sleepMs(400.0, 700.0)
            // 关弹层后常见「继续逛逛」遮罩，必须点才能回详情
            if (dismissContinueBrowsePopup()) {
                HumanBehavior.sleepMs(400.0, 650.0)
            }
            if (looksLikeGoodsDetail(readPageText()) && !isSkuPanel(readPageText()) &&
                !pageContainsGuangGuang(readPageText())
            ) {
                return
            }
        }
        // 最后再扫一次「逛逛」
        if (!looksLikeGoodsDetail(readPageText()) || isSkuPanel(readPageText()) ||
            pageContainsGuangGuang(readPageText())
        ) {
            dismissContinueBrowsePopup()
            HumanBehavior.sleepMs(350.0, 550.0)
        }
    }

    private fun pageContainsGuangGuang(page: String): Boolean =
        page.contains("逛逛") || page.contains("继续购物")

    /**
     * 规格返回详情时：文案含「逛逛」就点该位置（继续逛逛/再逛逛/去逛逛等）。
     */
    private suspend fun dismissContinueBrowsePopup(): Boolean {
        // 1) 精确常见文案
        val labels = listOf("继续逛逛", "再逛逛", "去逛逛", "继续购物", "逛逛")
        for (label in labels) {
            val n = A11yHelper.findByTextAllWindows(service(), label, exact = true, clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
            if (n == null) continue
            val r = A11yHelper.bounds(n)
            if (r.width() <= 0 || r.height() <= 0) continue
            log("扫到含「逛逛」文案，点击「$label」 bounds=${r.left},${r.top},${r.right},${r.bottom}")
            A11yHelper.clickNode(service(), A11yHelper.nearestClickable(n) ?: n)
            return true
        }
        // 2) 遍历节点：任意 text/desc 含「逛逛」即点该处
        val hit = findNodeContainingGuangGuang()
        if (hit != null) {
            val r = A11yHelper.bounds(hit)
            log("节点含「逛逛」，直接点击 bounds=${r.left},${r.top},${r.right},${r.bottom}")
            A11yHelper.clickNode(service(), A11yHelper.nearestClickable(hit) ?: hit)
            return true
        }
        // 3) 整页有字但节点难点：中下部比例点
        val page = readPageText()
        if (pageContainsGuangGuang(page)) {
            val screen = A11yHelper.screenRect(service())
            for (yf in listOf(0.62f, 0.58f, 0.68f, 0.55f, 0.72f)) {
                val x = screen.width() * 0.50f
                val y = screen.height() * yf
                log("文案有「逛逛」但未定位节点，比例点击 (${x.toInt()},${y.toInt()})")
                A11yHelper.tap(service(), HumanBehavior.jitter(x, 20f), HumanBehavior.jitter(y, 16f))
                HumanBehavior.sleepMs(350.0, 550.0)
                if (!pageContainsGuangGuang(readPageText())) return true
            }
        }
        return false
    }

    /** 全窗口找 text/contentDescription 含「逛逛」的节点（优先可点、偏屏幕中下） */
    private fun findNodeContainingGuangGuang(): AccessibilityNodeInfo? {
        val screen = A11yHelper.screenRect(service())
        var best: AccessibilityNodeInfo? = null
        var bestScore = Int.MIN_VALUE
        for (r in A11yHelper.roots(service())) {
            val queue = ArrayDeque<AccessibilityNodeInfo>()
            queue.add(r)
            while (queue.isNotEmpty()) {
                val n = queue.removeFirst()
                val t = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
                if (t.contains("逛逛") || t.contains("继续购物")) {
                    val b = A11yHelper.bounds(n)
                    if (b.width() > 0 && b.height() > 0) {
                        var score = 0
                        if (n.isClickable) score += 50
                        if (b.centerY() > screen.height() * 0.35f) score += 20
                        if (b.width() in 80..screen.width() && b.height() in 40..400) score += 15
                        // 文案越短越像按钮（「继续逛逛」优于整段说明）
                        score += (40 - t.length).coerceIn(0, 30)
                        if (score > bestScore) {
                            bestScore = score
                            best = n
                        }
                    }
                }
                for (i in 0 until n.childCount) {
                    n.getChild(i)?.let { queue.add(it) }
                }
            }
        }
        return best
    }

    suspend fun openAndReadProductParams(): String {
        var found = false
        for (i in 0 until 12) {
            val page = readPageText()
            val hasDetail = page.contains("商品详情") || page.contains("药品通用名") || page.contains("发货地")
            if (hasDetail) {
                val candidates = A11yHelper.listProductDetailViewAllCandidates(root())
                if (candidates.isEmpty()) {
                    log("本屏未见商品详情-查看全部，继续下滚")
                }
                for ((ci, node) in candidates.withIndex()) {
                    val r = A11yHelper.bounds(node)
                    log("尝试商品详情-查看全部#$ci bounds=${r.left},${r.top},${r.right},${r.bottom}")
                    A11yHelper.clickNode(service(), node)
                    HumanBehavior.pause(config, "read")
                    val after = readPageText()
                    if (isReviewListPage(after) && !isProductParamsPanel(after)) {
                        log("误点到评价查看全部，返回重试")
                        goBack()
                        HumanBehavior.sleepMs(300.0, 600.0)
                        continue
                    }
                    if (isProductParamsPanel(after)) {
                        found = true
                        log("已打开商品参数弹层（第${i + 1}屏 候选$ci）")
                        break
                    }
                    log("未弹出商品参数，返回后试下一候选")
                    goBack()
                    HumanBehavior.sleepMs(250.0, 500.0)
                }
                if (found) break
            }
            humanSwipe(
                HumanBehavior.jitter(540f, 40f),
                HumanBehavior.jitter(1500f, 70f),
                HumanBehavior.jitter(820f, 70f),
                purpose = "detail",
            )
            HumanBehavior.pause(config, "action")
        }
        if (!found) {
            log("未找到「商品详情-查看全部」入口")
            return ""
        }

        val chunks = mutableListOf<String>()
        chunks.add(readPageText())
        repeat(4) {
            humanSwipe(
                HumanBehavior.jitter(540f, 30f),
                HumanBehavior.jitter(1400f, 50f),
                HumanBehavior.jitter(900f, 50f),
                purpose = "detail",
            )
            HumanBehavior.sleepMs(350.0, 700.0)
            chunks.add(readPageText())
        }
        val merged = chunks.joinToString("\n")

        goBack()
        HumanBehavior.sleepMs(300.0, 600.0)
        val still = readPageText()
        if (still.contains("商品参数") && still.contains("批准文号")) {
            A11yHelper.tap(service(), 980f, 380f)
            HumanBehavior.sleepMs(250.0, 500.0)
            if (readPageText().contains("商品参数")) goBack()
        }
        log("商品参数文本长度=${merged.length}")
        return merged
    }

    private fun isProductParamsPanel(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        val hits = listOf("商品参数", "批准文号", "生产企业", "产品剂型", "药品规格", "国药准字")
            .count { t.contains(it) }
        return hits >= 2 || (t.contains("商品参数") && t.contains("品牌"))
    }

    private fun isReviewListPage(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        return (t.contains("商品评价") || t.contains("全部评价") || t.contains("评价(") || t.contains("评价（")) &&
            !t.contains("商品参数") &&
            !t.contains("批准文号")
    }

    /**
     * 采图：点主图 → 长按 →「一键保存全部图片」→ 从相册抓取。
     * 刚进详情时 [alreadyAtTop]=true，跳过上滑回顶。
     */
    suspend fun tryProbeMainImage(goodsId: String = "", alreadyAtTop: Boolean = false): List<String> {
        return try {
            log("======== 开始一键保存采图 ========")
            if (!alreadyAtTop) {
                // 非首屏场景才轻量回顶；进详情首屏主图已在顶部，无需上滑
                scrollToTop(1)
            } else {
                log("刚进详情，跳过上滑，直接点主图保存")
            }
            HumanBehavior.pause(config, "action")
            val sinceMs = System.currentTimeMillis()

            // 1) 点击首图进入大图（识别失败也继续：按用户要求在屏幕 50% 处长按保存）
            val previewOk = openMainImagePreview()
            if (!previewOk) {
                log("预览态未确认，仍在屏幕中部长按尝试保存")
            } else {
                // 预览内往左划 1~3 下徘徊（50% / 30% / 20%）
                wanderMainImagePreviewLeft()
            }

            // 2) 长按屏幕约 50% 区域弹出保存菜单（不依赖 Image 节点）
            if (!openSaveMenuByLongPress()) {
                log("长按未弹出「一键保存」菜单，采图失败（不用截图冒充）")
                leaveImagePreviewIfNeeded(maxBack = 1)
                return emptyList()
            }

            // 3) 点一键保存
            if (!clickSaveAllImages()) {
                log("未点到一键保存，尝试「保存图片」")
                if (!clickSaveSingleImage()) {
                    log("保存图片也未点到")
                    leaveImagePreviewIfNeeded(maxBack = 1)
                    return emptyList()
                }
            }
            repeat(2) {
                clickPermissionIfNeeded()
                HumanBehavior.sleepMs(400.0, 650.0)
            }
            HumanBehavior.sleepMs(1200.0, 1800.0)
            val toast = service().lastToastText
            if (toast.contains("保存") || readPageText().contains("已保存")) {
                log("检测到保存完成提示：$toast".take(60))
            } else {
                log("等待相册写入…")
                HumanBehavior.sleepMs(1000.0, 1600.0)
            }

            // 4) 相册抓取
            var paths = GalleryImagePicker.collectRecent(
                sinceEpochMs = sinceMs, limit = 8, goodsId = goodsId, log = log,
            )
            if (paths.isEmpty()) {
                HumanBehavior.sleepMs(1200.0, 1800.0)
                paths = GalleryImagePicker.collectRecent(
                    sinceEpochMs = sinceMs, limit = 8, goodsId = goodsId, log = log,
                )
            }
            if (paths.isEmpty()) {
                log("一键保存后相册仍无新图（请确认已授予读取相册权限）")
            } else {
                log("一键保存采图成功 ${paths.size} 张")
            }

            // 5) 保存完成后点一次屏幕 50% 区域，回到详情再继续后续步骤（用户确认）
            log("采图完成，点击屏幕中部50%后继续…")
            tapScreenCenter50()
            HumanBehavior.sleepMs(500.0, 800.0)
            if (isSaveMenu(readPageText()) || isPddImageViewer(readPageText())) {
                tapScreenCenter50()
                HumanBehavior.sleepMs(400.0, 650.0)
            }
            // 仍停在预览时再用关闭逻辑（不再优先系统 Back）
            if (!looksLikeGoodsDetail(readPageText())) {
                leaveImagePreviewIfNeeded(maxBack = 0)
            }

            val after = readPageText()
            when {
                looksLikeGoodsDetail(after) -> log("采图后仍在商品详情，可继续后续步骤")
                looksLikeSearchList(after) -> log("警告：采图后已回到列表页，后续取链可能失败")
                isPddImageViewer(after) -> log("警告：仍停在大图预览")
                else -> log("采图后页面类型未确认，将继续后续步骤")
            }
            log("======== 采图结束 ========")
            paths
        } catch (e: Exception) {
            log("采图异常: ${e.message}")
            emptyList()
        }
    }

    /**
     * 拼多多主图大图页（点主图后出现：顶栏 1/7 + 左上角 X，底栏可有「去拼单/查看优惠」）。
     * 与真正商品详情区分：详情有发起拼单/加入购物车/商品详情区，大图页没有。
     */
    private fun isPddImageViewer(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        if (isSaveMenu(text) || t.contains("分享图片")) return true
        // 勿调用 looksLikeSearchList，避免互相递归
        if ((t.contains("综合") && (t.contains("销量") || t.contains("价格"))) ||
            (t.contains("筛选") && t.contains("综合"))
        ) {
            return false
        }
        if (hasRealDetailBuyBar(t)) return false
        val hasPager = Regex("""\d+\s*/\s*\d+""").containsMatchIn(t)
        if (!hasPager) return false
        // 截图形态：页码 + 去拼单/查看优惠；或仅有页码且无详情区
        val viewerChrome = t.contains("去拼单") || t.contains("查看优惠") || t.contains("分享图片")
        if (viewerChrome) return true
        return !t.contains("商品详情") && !t.contains("店铺") && !t.contains("评价") &&
            !t.contains("已拼")
    }

    private fun isFullscreenImagePreview(text: String): Boolean = isPddImageViewer(text)

    private fun isImagePreview(text: String): Boolean = isPddImageViewer(text)

    /** 真正详情底栏（不含大图页上的「去拼单」） */
    private fun hasRealDetailBuyBar(t: String): Boolean {
        return t.contains("发起拼单") || t.contains("领券购买") || t.contains("立即购买") ||
            t.contains("加入购物车") || t.contains("单独购买") || t.contains("免拼购买") ||
            t.contains("去复诊开药") || t.contains("开药购买")
    }

    private fun hasDetailBuyBar(t: String): Boolean = hasRealDetailBuyBar(t)

    fun looksLikeGoodsDetail(text: String = readPageText()): Boolean {
        if (isPddImageViewer(text)) return false
        val t = text.replace("\\s+".toRegex(), "")
        val buy = hasRealDetailBuyBar(t)
        val share = t.contains("分享")
        val shop = t.contains("商品详情") || t.contains("进店") || t.contains("店铺") ||
            t.contains("评价") || t.contains("已拼")
        return buy || (share && shop)
    }

    fun looksLikeSearchList(text: String = readPageText()): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        if (isPddImageViewer(text) || looksLikeGoodsDetail(t)) return false
        return (t.contains("综合") && (t.contains("销量") || t.contains("价格"))) ||
            (t.contains("筛选") && t.contains("综合"))
    }

    /**
     * 商品采集结束后逐层关闭弹层/预览/详情，直到确认回到可继续点击的搜索列表。
     * 旧逻辑只执行一次 Back，分享层或规格层尚未退出时，下一商品会读到空列表。
     */
    suspend fun returnToSearchList(maxBacks: Int = 6): Boolean {
        repeat(maxBacks.coerceIn(1, 8)) { round ->
            // 复制链接后的悬浮窗/输入法关闭会产生短暂无障碍空窗口；先等待，不把它当失败。
            var page = readPageText()
            if (A11yHelper.root(service()) == null || page.isBlank()) {
                log("返回列表第 ${round + 1} 步：等待拼多多界面恢复")
                HumanBehavior.sleepMs(500.0, 850.0)
                return@repeat
            }
            if (isPddHome(page)) {
                log("返回层级过深已到首页，将重新搜索恢复列表")
                return false
            }
            val cards = listCardsOrEmpty()
            if (looksLikeSearchList(page) ||
                (cards.isNotEmpty() && !hasDetailOverlay(page))
            ) {
                log("已确认返回商品列表，卡片=${cards.size}")
                return true
            }
            if (pageContainsGuangGuang(page) && dismissContinueBrowsePopup()) {
                HumanBehavior.sleepMs(350.0, 600.0)
                page = readPageText()
                if (looksLikeSearchList(page) || listCardsOrEmpty().isNotEmpty()) return true
            }
            if (isSaveMenu(page)) {
                log("返回列表第 ${round + 1} 步：先收起保存菜单")
                tapToDismissImageUi()
            } else if (isPddImageViewer(page)) {
                log("返回列表第 ${round + 1} 步：退出大图预览")
                leaveImagePreviewIfNeeded(maxBack = 1)
            } else {
                log("返回列表第 ${round + 1} 步：关闭当前详情/弹层")
                goBack()
            }
            HumanBehavior.sleepMs(450.0, 750.0)
        }
        val page = readPageText()
        val ok = !isPddHome(page) && (looksLikeSearchList(page) ||
            (listCardsOrEmpty().isNotEmpty() && !hasDetailOverlay(page)))
        log(if (ok) "返回商品列表成功" else "多次返回后仍未确认商品列表")
        return ok
    }

    private fun hasDetailOverlay(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        return looksLikeGoodsDetail(text) || isSkuPanel(text) || isPddImageViewer(text) || isSaveMenu(text) ||
            isImageSearchShareOverlay(text) ||
            pageContainsGuangGuang(text) || t.contains("商品参数") || t.contains("批准文号") ||
            (t.contains("确认") && (t.contains("规格") || t.contains("已选择"))) ||
            (t.contains("分享") && (t.contains("微信") || t.contains("复制链接")))
    }

    /**
     * 离开大图：优先点界面/左上角 X 回详情（用户确认：保存后点当前界面即回详情）。
     * 禁止用系统 Back 关预览——容易多退一层到搜索列表。
     */
    private suspend fun leaveImagePreviewIfNeeded(maxBack: Int = 1) {
        var first = readPageText()
        // 任务 58：视频/款式图长按可能弹出「搜索视频同款商品/发送给微信好友/取消」。
        // 该层不是保存菜单也不是大图页；必须先取消，否则后续恢复会把它当成未知页面。
        if (isImageSearchShareOverlay(first)) {
            dismissImageSearchShareOverlay()
            HumanBehavior.sleepMs(400.0, 650.0)
            first = readPageText()
        }
        if (!isSaveMenu(first) && looksLikeGoodsDetail(first)) {
            log("无需返回（保存后已在商品详情）")
            return
        }
        if (looksLikeSearchList(first)) {
            log("警告：离开预览前已在列表，跳过操作以免再退一层")
            return
        }
        // 保存菜单仍在：点空白收起（不用系统返回）
        if (isSaveMenu(first)) {
            log("点击收起保存菜单…")
            tapToDismissImageUi()
            HumanBehavior.sleepMs(400.0, 650.0)
        }
        if (looksLikeGoodsDetail(readPageText())) {
            log("已回到商品详情")
            return
        }
        if (!isPddImageViewer(readPageText()) && !isSaveMenu(readPageText())) {
            log("无需返回（已不在大图预览）")
            return
        }
        // 大图页：先点左上角 X，再点画面中间（与人手一致）
        if (clickImageViewerCloseX()) {
            HumanBehavior.sleepMs(450.0, 700.0)
            if (looksLikeGoodsDetail(readPageText())) {
                log("已点 X 回到商品详情")
                return
            }
        }
        log("点击大图界面回详情…")
        tapToDismissImageUi()
        HumanBehavior.sleepMs(450.0, 700.0)
        if (looksLikeGoodsDetail(readPageText())) {
            log("已点击界面回到商品详情")
            return
        }
        // 仍停在大图时再点一次画面（避免误触下载图标）
        log("再点一次大图中部回详情…")
        tapToDismissImageUi(preferCenter = true)
        HumanBehavior.sleepMs(450.0, 700.0)
        if (looksLikeGoodsDetail(readPageText())) {
            log("已回到商品详情")
            return
        }
        // 最后手段：仅 1 次系统返回（仍失败则交给 ensureOnGoodsDetail 重进）
        if (maxBack > 0 && isPddImageViewer(readPageText())) {
            log("点击未退出大图，尝试一次系统返回…")
            goBackQuiet()
            HumanBehavior.sleepMs(400.0, 650.0)
        }
    }

    private suspend fun clickImageViewerCloseX(): Boolean {
        val labels = listOf("关闭", "close", "Close", "返回")
        for (label in labels) {
            val n = A11yHelper.findByContentDescAllWindows(service(), label)
                ?: A11yHelper.findByTextAllWindows(service(), label, exact = true, clickableOnly = true)
            if (n == null) continue
            val r = A11yHelper.bounds(n)
            // 仅点左上角关闭，避免点到底部「返回」类文案
            if (r.top < 280 && r.left < 280) {
                log("点击大图关闭按钮：$label")
                A11yHelper.clickNode(service(), n)
                return true
            }
        }
        // 坐标点左上角 X（截图位置）
        val dm = service().resources.displayMetrics
        val x = HumanBehavior.jitter(dm.widthPixels * 0.06f, 8f)
        val y = HumanBehavior.jitter(dm.heightPixels * 0.065f, 10f)
        log("坐标点击大图左上角关闭 ($x,$y)".take(48))
        A11yHelper.tap(service(), x, y)
        return true
    }

    /** 点大图中部空白，收起菜单或退出预览（勿点右上角下载/底栏去拼单） */
    private suspend fun tapToDismissImageUi(preferCenter: Boolean = false) {
        val dm = service().resources.displayMetrics
        val points = if (preferCenter) {
            listOf(
                0.50f to 0.42f,
                0.48f to 0.38f,
                0.52f to 0.48f,
            )
        } else {
            listOf(
                0.50f to 0.40f,
                0.45f to 0.36f,
                0.55f to 0.44f,
                0.08f to 0.07f, // 左上角 X 备选
            )
        }
        val (fx, fy) = points.random()
        A11yHelper.tap(
            service(),
            HumanBehavior.jitter(dm.widthPixels * fx, 18f),
            HumanBehavior.jitter(dm.heightPixels * fy, 22f),
        )
    }

    /** 若采图后误退列表，重新点开同一卡片 */
    suspend fun ensureOnGoodsDetail(openIndex: Int): Boolean {
        var page = readPageText()
        if (isImageSearchShareOverlay(page)) {
            log("检测到图片同款/微信分享弹层，先取消后恢复商品详情")
            dismissImageSearchShareOverlay()
            HumanBehavior.sleepMs(400.0, 650.0)
            page = readPageText()
        }
        // 规格读取异常退出时必须先收起弹层；否则规格卡片会被误判成搜索结果卡片。
        if (isSkuPanel(page)) {
            log("检测到规格弹层仍未关闭，先关闭后再恢复商品详情")
            closeSkuPanel()
            HumanBehavior.sleepMs(400.0, 700.0)
            page = readPageText()
        }
        // 读规格返回途中的「逛逛」遮罩：直接点该位置
        if (pageContainsGuangGuang(page)) {
            if (dismissContinueBrowsePopup()) {
                HumanBehavior.sleepMs(400.0, 650.0)
                page = readPageText()
            }
        }
        if (looksLikeGoodsDetail(page) && !pageContainsGuangGuang(page)) return true
        if (isPddImageViewer(page) || isSaveMenu(page)) {
            leaveImagePreviewIfNeeded()
            if (looksLikeGoodsDetail(readPageText())) return true
        }
        if (looksLikeSearchList(readPageText())) {
            log("检测到已离开详情回到列表，重新进入第 ${openIndex + 1} 个商品…")
            val (ok, _) = openCardAt(openIndex)
            HumanBehavior.sleepMs(900.0, 1400.0)
            return ok && looksLikeGoodsDetail()
        }
        // 再试一次「逛逛」
        if (pageContainsGuangGuang(readPageText()) && dismissContinueBrowsePopup()) {
            HumanBehavior.sleepMs(400.0, 650.0)
            if (looksLikeGoodsDetail(readPageText())) return true
        }
        log("当前不在详情且不像列表，无法自动恢复")
        return false
    }

    private fun isSaveMenu(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        return t.contains("一键保存") || t.contains("保存全部图片") ||
            (t.contains("保存图片") && (t.contains("微信") || t.contains("搜索图片") || t.contains("取消")))
    }

    /** 视频/款式图长按后的同款搜索分享层，不属于拼多多保存菜单。 */
    private fun isImageSearchShareOverlay(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        val searchSame = t.contains("搜索视频同款商品") || t.contains("搜索图片同款商品") ||
            t.contains("搜索同款商品")
        return searchSame && t.contains("发送给微信好友") && t.contains("取消")
    }

    private suspend fun dismissImageSearchShareOverlay(): Boolean {
        if (!isImageSearchShareOverlay(readPageText())) return false
        log("检测到图片同款/微信分享弹层，点击取消并停止继续长按")
        val cancel = A11yHelper.findByTextAllWindows(service(), "取消", exact = true, clickableOnly = true)
            ?: A11yHelper.findByTextAllWindows(service(), "取消", exact = true, clickableOnly = false)
        if (cancel != null) {
            A11yHelper.clickNode(service(), A11yHelper.nearestClickable(cancel) ?: cancel)
        } else {
            goBackQuiet()
        }
        HumanBehavior.sleepMs(400.0, 700.0)
        return true
    }

    private suspend fun openMainImagePreview(): Boolean {
        log("点击上方主图进入预览…")
        val screen = A11yHelper.screenRect(service())
        val heroes = A11yHelper.findTopHeroImages(service())
        for (node in heroes.take(3)) {
            A11yHelper.clickNode(service(), node)
            HumanBehavior.sleepMs(900.0, 1300.0)
            if (isImagePreview(readPageText()) || looksLikeImageViewerLoose(readPageText())) {
                log("已进入主图预览(节点)")
                return true
            }
        }
        // 大屏比例坐标点首图区（勿写死 1080 逻辑坐标）
        for (yf in listOf(0.18f, 0.22f, 0.15f, 0.26f, 0.12f)) {
            val x = screen.width() * 0.50f
            val y = screen.height() * yf
            A11yHelper.tap(service(), HumanBehavior.jitter(x, 28f), HumanBehavior.jitter(y, 22f))
            HumanBehavior.sleepMs(900.0, 1300.0)
            if (isImagePreview(readPageText()) || looksLikeImageViewerLoose(readPageText())) {
                log("已进入主图预览(比例 ${yf})")
                return true
            }
        }
        return false
    }

    /** 宽松预览判断：有页码或去拼单底栏即可，避免漏检导致不长按 */
    private fun looksLikeImageViewerLoose(text: String): Boolean {
        if (looksLikeSearchList(text)) return false
        val t = text.replace("\\s+".toRegex(), "")
        if (isSaveMenu(text) || t.contains("分享图片")) return true
        val hasPager = Regex("""\d+\s*/\s*\d+""").containsMatchIn(t)
        return hasPager || (t.contains("去拼单") && !t.contains("商品详情") && !t.contains("评价"))
    }

    /**
     * 主图预览内往左划动徘徊：1 次 50%，2 次 30%，3 次 20%。
     * 左划 = 手指从右往左，切换下一张主图。
     */
    private suspend fun wanderMainImagePreviewLeft() {
        val r = Random.nextDouble()
        val times = when {
            r < 0.50 -> 1
            r < 0.80 -> 2
            else -> 3
        }
        log("主图预览拟人左划 $times 次（分布 50/30/20）")
        val dm = service().resources.displayMetrics
        repeat(times) {
            val y = HumanBehavior.jitter(dm.heightPixels * 0.42f, dm.heightPixels * 0.06f)
            val x1 = HumanBehavior.jitter(dm.widthPixels * 0.82f, 28f)
            val x2 = HumanBehavior.jitter(dm.widthPixels * 0.22f, 28f)
            A11yHelper.swipeTo(
                service(),
                x1,
                y,
                x2,
                HumanBehavior.jitter(y, 18f),
                HumanBehavior.swipeDurationMs("detail"),
            )
            HumanBehavior.sleepMs(350.0, 800.0, bias = "short")
            if (Random.nextDouble() < 0.35) {
                HumanBehavior.pause(config, "think")
            }
        }
    }

    /**
     * 进入首图后：在屏幕约 50%（正中）区域长按弹出保存菜单。
     * 用户确认该位置可稳定唤起「一键保存」。
     */
    private suspend fun openSaveMenuByLongPress(): Boolean {
        val screen = A11yHelper.screenRect(service())
        val points = listOf(
            0.50f to 0.50f, // 主：屏幕正中 50%
            0.50f to 0.45f,
            0.48f to 0.52f,
            0.52f to 0.48f,
            0.50f to 0.55f,
        )
        log("长按屏幕中部(约50%)打开保存菜单… screen=${screen.width()}x${screen.height()}")
        for ((fx, fy) in points) {
            val x = HumanBehavior.jitter(screen.width() * fx, 18f)
            val y = HumanBehavior.jitter(screen.height() * fy, 22f)
            log("长按坐标 (${x.toInt()},${y.toInt()}) ratio=$fx,$fy")
            A11yHelper.longPress(service(), x, y, 1400)
            HumanBehavior.sleepMs(850.0, 1300.0)
            clickPermissionIfNeeded()
            val afterLongPress = readPageText()
            if (isSaveMenu(afterLongPress)) {
                log("保存菜单已弹出(中部长按)")
                return true
            }
            if (isImageSearchShareOverlay(afterLongPress)) {
                log("长按打开的是图片同款/微信分享弹层，取消并终止本轮长按重试")
                dismissImageSearchShareOverlay()
                return false
            }
            log("长按后未见菜单 preview=${afterLongPress.replace("\n", " ").take(80)}")
        }
        return false
    }

    private suspend fun clickSaveAllImages(): Boolean {
        val labels = listOf(
            "一键保存全部图片", "一键保存全部", "保存全部图片", "一键保存",
        )
        for (label in labels) {
            val n = A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
            if (n == null) continue
            val lab = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
            // 避免点到「保存图片」单张：优先含「全部/一键」
            if (!lab.contains("全部") && !lab.contains("一键") && label.contains("一键")) {
                // still allow 一键保存*
            }
            log("点击保存：$lab".take(50))
            A11yHelper.clickNode(service(), n)
            HumanBehavior.sleepMs(700.0, 1100.0)
            return true
        }
        // 菜单第二项坐标（用户截图：保存图片下一行是一键保存）
        log("文案未定位到一键保存，坐标点第二项…")
        for (xy in listOf(540f to 1520f, 540f to 1580f, 540f to 1450f, 540f to 1650f, 540f to 1400f)) {
            A11yHelper.tap(service(), xy.first, xy.second)
            HumanBehavior.sleepMs(600.0, 900.0)
            if (!isSaveMenu(readPageText())) {
                log("坐标点击后菜单已收起，视为点中一键保存")
                return true
            }
        }
        return false
    }

    private suspend fun clickSaveSingleImage(): Boolean {
        val n = A11yHelper.findByTextAllWindows(service(), "保存图片", exact = true, clickableOnly = true)
            ?: A11yHelper.findByTextAllWindows(service(), "保存图片", exact = false, clickableOnly = false)
        if (n == null) return false
        val lab = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
        if (lab.contains("全部") || lab.contains("一键")) return false
        log("点击：$lab".take(40))
        A11yHelper.clickNode(service(), n)
        HumanBehavior.sleepMs(700.0, 1100.0)
        return true
    }

    private suspend fun clickPermissionIfNeeded() {
        val page = readPageText()
        val need = page.contains("照片") || page.contains("存储") || page.contains("文件") ||
            page.contains("权限") || page.contains("媒体") || page.contains("相册") ||
            page.contains("允许访问")
        if (!need) return
        for (label in listOf(
            "允许", "始终允许", "仅在使用中允许", "使用时允许", "同意", "确定", "好的", "立即开始",
        )) {
            val n = A11yHelper.findByTextAllWindows(service(), label, exact = true, clickableOnly = true)
                ?: continue
            log("点击权限：$label")
            A11yHelper.clickNode(service(), n)
            HumanBehavior.sleepMs(400.0, 700.0)
            return
        }
    }

    private suspend fun goBackQuiet() {
        try {
            service().performGlobalAction(
                android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK,
            )
            HumanBehavior.sleepMs(250.0, 450.0)
        } catch (_: Exception) {
        }
    }

    data class ShareCapture(
        val url: String = "",
        val images: List<String> = emptyList(),
        val raw: String = "",
        val goodsId: String = "",
    )

    suspend fun tryCaptureShareLink(): ShareCapture {
        return try {
            scrollToTop(1)
            HumanBehavior.pause(config, "action")
            log("开始分享取链…")
            if (!openSharePanel()) {
                log("未打开分享面板，放弃取链")
                return ShareCapture()
            }
            val panelText = readPageText()
            if (!sharePanelOpened(panelText)) {
                log("仍无复制链接/口令入口")
                // 可能误开了别的层，只回退一次，不再连点分享
                goBack()
                return ShareCapture()
            }
            log("分享面板已打开")
            val labels = A11yHelper.listSharePanelLabels(service())
            if (labels.isNotEmpty()) {
                log("分享面板项: ${labels.joinToString(",").take(120)}")
            }

            val panelHarvest = harvestPage()
            val panelBlob = panelHarvest.blob + "\n" + panelText
            val panelImgs = (panelHarvest.images + A11yHelper.harvestImageHints(root()))
                .filter { GoodsLinkResolver.isProductImageUrl(it) }
                .distinct()
            var fromPanelUrl = GoodsLinkResolver.extractGoodsUrls(panelBlob).firstOrNull().orEmpty()
            var fromPanelId = panelHarvest.goodsId
                .ifBlank { GoodsLinkResolver.extractGoodsId(panelBlob) }

            val beforeClip = readClipboardNow()
            var clip = ""
            var copied = false
            for (label in listOf("复制链接", "复制口令", "复制文案", "复制")) {
                val copy = A11yHelper.findByTextAllWindows(
                    service(), label, exact = label != "复制", clickableOnly = true,
                ) ?: A11yHelper.findByTextAllWindows(
                    service(), label, exact = label != "复制", clickableOnly = false,
                )
                if (copy == null) continue
                val lab = ((copy.text?.toString() ?: "") + (copy.contentDescription?.toString() ?: ""))
                if (label == "复制" && !lab.contains("链接") && !lab.contains("口令") && !lab.contains("文案")) {
                    continue
                }
                log("点击：$lab".take(40))
                A11yHelper.clickNode(service(), copy)
                copied = true
                HumanBehavior.sleepMs(700.0, 1100.0)
                break
            }
            if (!copied) {
                log("文案未点到复制，坐标兜底")
                for (xy in listOf(
                    180f to 1680f, 270f to 1680f, 360f to 1680f, 450f to 1680f,
                    180f to 1780f, 270f to 1780f,
                )) {
                    A11yHelper.tap(service(), xy.first, xy.second)
                    HumanBehavior.sleepMs(450.0, 750.0)
                    if (readPageText().contains("复制成功") || readPageText().contains("已复制")) {
                        break
                    }
                }
            }

            var sawCopyOk = false
            for (i in 0 until 10) {
                val toast = service().lastToastText
                val page = readPageText()
                if (toast.contains("复制成功") || toast.contains("已复制") ||
                    page.contains("复制成功") || page.contains("已复制")
                ) {
                    log("检测到复制成功提示")
                    sawCopyOk = true
                    break
                }
                HumanBehavior.sleepMs(200.0, 350.0)
            }
            if (!sawCopyOk) HumanBehavior.sleepMs(500.0, 800.0)

            if (sharePanelOpened(readPageText())) {
                service().performGlobalAction(
                    android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK,
                )
                HumanBehavior.pause(config, "action")
            }

            val afterCopyBlob = readPageText() + "\n" + harvestPage().blob
            fromPanelUrl = fromPanelUrl
                .ifBlank { GoodsLinkResolver.extractGoodsUrls(afterCopyBlob).firstOrNull().orEmpty() }
            fromPanelId = fromPanelId
                .ifBlank { GoodsLinkResolver.extractGoodsId(afterCopyBlob) }

            clip = readClipboardNow()
            if (!looksLikeShareLink(clip) || clip == beforeClip) {
                log("改用无障碍悬浮窗粘贴取链（不点更多）…")
                clip = PasteOverlay.captureLink(service(), log)
            }
            if (looksLikeShareLink(clip)) {
                log("取链成功 len=${clip.length} preview=${clipPreview(clip)}")
            } else {
                log("粘贴仍失败，尝试 dumpsys 解析当前页商品ID…")
                clip = ""
                val dump = withContext(Dispatchers.IO) { ActivityDumpResolver.probePdd() }
                if (dump.goodsId.isNotBlank() || dump.shareUrl.isNotBlank()) {
                    fromPanelId = fromPanelId.ifBlank { dump.goodsId }
                    fromPanelUrl = fromPanelUrl.ifBlank { dump.shareUrl }
                    log(
                        "dumpsys命中 id=${dump.goodsId.ifBlank { "-" }} " +
                            "url=${dump.shareUrl.ifBlank { "-" }.take(70)}"
                    )
                } else {
                    log("dumpsys 未解析到 goods_id")
                }
            }

            val rawLink = listOf(clip, fromPanelUrl)
                .firstOrNull { looksLikeShareLink(it) }
                .orEmpty()
                .ifBlank { clip }

            var url = extractUrlFromShare(rawLink)
                .ifBlank { fromPanelUrl }
                .ifBlank { GoodsLinkResolver.extractGoodsUrls(rawLink).firstOrNull().orEmpty() }
            var goodsId = GoodsLinkResolver.extractGoodsId(rawLink)
                .ifBlank { fromPanelId }
                .ifBlank { GoodsLinkResolver.extractGoodsId(url) }
            if (url.isBlank() && goodsId.isNotBlank()) {
                url = GoodsLinkResolver.buildGoodsUrl(goodsId)
            }
            if (url.isBlank() && rawLink.contains("http", true)) {
                url = Regex("""https?://[^\s]+""").find(rawLink)?.value
                    ?.trimEnd(',', '.', ')', ']', '，', '。')
                    .orEmpty()
            }

            log(
                "分享取链结束 id=${goodsId.ifBlank { "-" }} " +
                    "url=${if (url.isBlank()) "-" else url.take(80)} rawLen=${rawLink.length}"
            )
            ShareCapture(
                url = url,
                images = panelImgs,
                raw = rawLink.ifBlank { url },
                goodsId = goodsId,
            )
        } catch (e: Exception) {
            log("分享取链异常: ${e.message}")
            try {
                service().performGlobalAction(
                    android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK,
                )
            } catch (_: Exception) {
            }
            ShareCapture()
        }
    }

    private fun sharePanelOpened(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        return t.contains("复制链接") || t.contains("复制口令") || t.contains("生成海报") ||
            t.contains("微信好友") || t.contains("朋友圈") || t.contains("QQ好友") ||
            t.contains("分享给") || t.contains("更多分享") || t.contains("面对面扫码")
    }

    /**
     * 打开分享面板：整个流程只点击一次分享入口，然后等待面板。
     * （旧逻辑会在顶栏点完后再点「分享」文案，表现为连续点两次）
     */
    private suspend fun openSharePanel(): Boolean {
        if (sharePanelOpened(readPageText())) {
            log("分享面板已在展示")
            return true
        }

        val screen = A11yHelper.screenRect(service())
        var tapX: Float? = null
        var tapY: Float? = null
        var how = ""

        val topShare = A11yHelper.findTopShareButton(root())
        if (topShare != null) {
            val r = A11yHelper.bounds(topShare)
            if (r.width() > 0 && r.height() > 0) {
                tapX = r.exactCenterX()
                tapY = r.exactCenterY()
                how = "top-bar"
            }
        }
        if (tapX == null) {
            val share = A11yHelper.findByTextAllWindows(service(), "分享", exact = true, clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), "分享商品", exact = false, clickableOnly = true)
            if (share != null) {
                val r = A11yHelper.bounds(share)
                val lab = ((share.text?.toString() ?: "") + (share.contentDescription?.toString() ?: ""))
                if (r.top < 500 && !lab.contains("分享图片") && !lab.contains("微信") && r.width() > 0) {
                    tapX = r.exactCenterX()
                    tapY = r.exactCenterY()
                    how = "label"
                }
            }
        }
        if (tapX == null) {
            tapX = screen.width() * 0.93f
            tapY = screen.height() * 0.065f
            how = "coord"
        }

        val x = tapX ?: (screen.width() * 0.93f)
        val y = tapY ?: (screen.height() * 0.065f)
        val xi = x.toInt()
        val yi = y.toInt()
        log("click share once via $how at $xi,$yi")
        // tap only once; do not use clickNode (ACTION_CLICK + tap can double-fire)
        A11yHelper.tap(service(), HumanBehavior.jitter(x, 8f), HumanBehavior.jitter(y, 6f))
        return waitSharePanel(rounds = 6)
    }

    private suspend fun waitSharePanel(rounds: Int = 6): Boolean {
        repeat(rounds) {
            HumanBehavior.sleepMs(280.0, 450.0)
            if (sharePanelOpened(readPageText())) {
                log("分享面板已打开")
                return true
            }
        }
        return false
    }

    private fun clipPreview(text: String): String =
        GoodsLinkResolver.normalizeShareText(text).replace("\n", " ").take(100)

    private fun looksLikeShareLink(text: String): Boolean {
        val t = GoodsLinkResolver.normalizeShareText(text)
        if (t.isBlank()) return false
        if (GoodsLinkResolver.extractGoodsUrls(t).isNotEmpty()) return true
        if (GoodsLinkResolver.extractGoodsId(t).isNotBlank()) return true
        if (t.contains("yangkeduo.com", true) || t.contains("pinduoduo.com", true)) return true
        if (t.contains("goods1.html", true) || Regex("""[?&]ps=[A-Za-z0-9_-]+""").containsMatchIn(t)) {
            return true
        }
        if (t.length in 8..800 && (t.contains("￥") || t.contains("€") || t.contains("＄"))) {
            return true
        }
        return false
    }

    private fun readClipboardNow(): String {
        return try {
            val cm = service().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip ?: return ""
            val parts = mutableListOf<String>()
            for (i in 0 until clip.itemCount) {
                val item = clip.getItemAt(i) ?: continue
                item.text?.toString()?.let { if (it.isNotBlank()) parts.add(it) }
                item.htmlText?.let { if (it.isNotBlank()) parts.add(it) }
                item.uri?.toString()?.let { if (it.isNotBlank()) parts.add(it) }
                try {
                    val coerced = item.coerceToText(service())?.toString().orEmpty()
                    if (coerced.isNotBlank()) parts.add(coerced)
                } catch (_: Exception) {
                }
            }
            GoodsLinkResolver.normalizeShareText(parts.distinct().joinToString("\n"))
        } catch (_: Exception) {
            ""
        }
    }

    private fun extractUrlFromShare(raw: String): String {
        if (raw.isBlank()) return ""
        GoodsLinkResolver.extractGoodsUrls(raw).firstOrNull()?.let { return it }
        val id = GoodsLinkResolver.extractGoodsId(raw)
        if (id.isNotBlank()) return GoodsLinkResolver.buildGoodsUrl(id)
        return ""
    }

    suspend fun goBack() {
        service().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        HumanBehavior.pause(config, "action")
    }

    suspend fun humanPause(minMs: Long, maxMs: Long) {
        HumanBehavior.sleepMs(minMs.toDouble(), maxOf(minMs + 1, maxMs).toDouble(), bias = "long")
    }

    suspend fun betweenKeywords() {
        log("返回拼多多首页，准备下一关键词…")
        goToPddHome()
        HumanBehavior.pause(config, "keyword")
        if (config.enableHumanGestures) {
            maybeExtraHumanAction("keyword")
        }
    }

    /** 是否像拼多多首页（底栏首页 + 顶部搜索带） */
    fun isPddHome(text: String = readPageText()): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        val hasHomeTab = t.contains("首页")
        val hasReco = t.contains("推荐") || t.contains("百亿补贴") || t.contains("多多买菜")
        val notList = !(t.contains("综合") && t.contains("销量") && t.contains("价格"))
        val notDetail = !t.contains("发起拼单") && !t.contains("加入购物车")
        return hasHomeTab && hasReco && notList && notDetail
    }

    /** 多关键词之间：退出详情/搜索结果，回到拼多多首页 */
    suspend fun goToPddHome() {
        repeat(8) {
            if (isPddHome()) {
                clickBottomHomeTab()
                HumanBehavior.sleepMs(400.0, 700.0)
                if (isPddHome()) {
                    log("已在拼多多首页")
                    return
                }
            }
            goBackQuiet()
            HumanBehavior.sleepMs(350.0, 600.0)
        }
        clickBottomHomeTab()
        HumanBehavior.sleepMs(500.0, 800.0)
        if (isPddHome()) {
            log("已回到拼多多首页")
        } else {
            log("未能确认首页，仍继续下一关键词搜索")
        }
    }

    private suspend fun clickBottomHomeTab() {
        val screen = A11yHelper.screenRect(service())
        val minTop = (screen.height() * 0.85f).toInt()
        val nodes = A11yHelper.findAllByText(root(), "首页")
        for (n in nodes) {
            val r = A11yHelper.bounds(n)
            if (r.top >= minTop && r.left < screen.width() * 0.35f) {
                log("点击底栏首页")
                A11yHelper.clickNode(service(), n)
                return
            }
        }
        // 坐标兜底：左下角首页
        A11yHelper.tap(service(), screen.width() * 0.10f, screen.height() * 0.96f)
    }

    /**
     * 任务结束/终止：先回拼多多首页，再多路径拉起联机工具主界面。
     * 鸿蒙/华为常拦截后台 startActivity，故叠加：Intent / 通知全屏 / 桌面图标点击 / 最近任务。
     */
    suspend fun finishAndReturnToApp() {
        log("任务结束：返回拼多多首页 → 联机工具主界面…")
        try {
            goToPddHomeQuick()
        } catch (e: Exception) {
            log("回拼多多首页异常: ${e.message}")
        }
        HumanBehavior.sleepMs(400.0, 700.0)

        // 1) 前台服务 Intent + 全屏通知
        try {
            val ok = service().forceOpenMain("采集已结束，正在返回联机工具…")
            log(if (ok) "已请求拉起联机工具（Intent/通知）" else "Intent/通知拉起未确认")
        } catch (e: Exception) {
            log("Intent 拉起异常: ${e.message}")
        }
        HumanBehavior.sleepMs(900.0, 1300.0)
        if (isCollectorForeground()) {
            log("已确认回到联机工具主界面")
            return
        }

        // 2) 桌面找「联机工具」图标点击（华为最稳）
        log("未回到主界面，尝试桌面图标点击…")
        if (bringCollectorViaLauncherIcon()) {
            HumanBehavior.sleepMs(800.0, 1200.0)
            if (isCollectorForeground()) {
                log("已通过桌面图标回到联机工具")
                return
            }
        }

        // 3) 最近任务里点联机工具
        log("尝试最近任务切回联机工具…")
        if (bringCollectorViaRecents()) {
            HumanBehavior.sleepMs(800.0, 1200.0)
            if (isCollectorForeground()) {
                log("已通过最近任务回到联机工具")
                return
            }
        }

        // 4) 再发一次强提醒通知
        try {
            service().forceOpenMain("请点此返回联机工具")
            log("仍未确认回到主界面，已发出返回通知，请手动点通知或桌面图标")
        } catch (_: Exception) {
        }
    }

    /** 结束任务用的快速回首页，避免来回滑太久耽误回 App */
    private suspend fun goToPddHomeQuick() {
        repeat(5) {
            if (isPddHome()) {
                clickBottomHomeTab()
                HumanBehavior.sleepMs(300.0, 500.0)
                if (isPddHome()) {
                    log("已在拼多多首页")
                    return
                }
            }
            goBackQuiet()
            HumanBehavior.sleepMs(280.0, 450.0)
        }
        clickBottomHomeTab()
        HumanBehavior.sleepMs(350.0, 550.0)
    }

    private fun isCollectorForeground(): Boolean {
        val t = readPageText().replace("\\s+".toRegex(), "")
        return (t.contains("联机工具") || t.contains("拼多多采集助手")) &&
            (t.contains("运行日志") || t.contains("停止当前任务") || t.contains("同步版本") ||
                t.contains("忽略电池") || t.contains("无障碍"))
    }

    private suspend fun bringCollectorViaLauncherIcon(): Boolean {
        return try {
            service().performGlobalAction(
                android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME,
            )
            HumanBehavior.sleepMs(700.0, 1000.0)
            val labels = listOf("联机工具", "拼多多采集助手")
            for (label in labels) {
                val n = A11yHelper.findByTextAllWindows(service(), label, exact = true, clickableOnly = false)
                    ?: A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
                    ?: A11yHelper.findByContentDescAllWindows(service(), label)
                if (n != null) {
                    log("桌面点击：$label")
                    A11yHelper.clickNode(service(), A11yHelper.nearestClickable(n) ?: n)
                    return true
                }
            }
            // 部分桌面要左滑翻页找图标
            val dm = service().resources.displayMetrics
            A11yHelper.swipeTo(
                service(),
                dm.widthPixels * 0.85f,
                dm.heightPixels * 0.55f,
                dm.widthPixels * 0.2f,
                dm.heightPixels * 0.55f,
                320,
            )
            HumanBehavior.sleepMs(500.0, 800.0)
            for (label in labels) {
                val n = A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
                if (n != null) {
                    log("桌面翻页后点击：$label")
                    A11yHelper.clickNode(service(), A11yHelper.nearestClickable(n) ?: n)
                    return true
                }
            }
            false
        } catch (e: Exception) {
            log("桌面点击失败: ${e.message}")
            false
        }
    }

    private suspend fun bringCollectorViaRecents(): Boolean {
        return try {
            service().performGlobalAction(
                android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_RECENTS,
            )
            HumanBehavior.sleepMs(700.0, 1000.0)
            val labels = listOf("联机工具", "拼多多采集助手")
            for (label in labels) {
                val n = A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
                    ?: A11yHelper.findByContentDescAllWindows(service(), label)
                if (n != null) {
                    log("最近任务点击：$label")
                    A11yHelper.clickNode(service(), A11yHelper.nearestClickable(n) ?: n)
                    return true
                }
            }
            false
        } catch (e: Exception) {
            log("最近任务切换失败: ${e.message}")
            false
        }
    }

    @Deprecated("use finishAndReturnToApp", ReplaceWith("finishAndReturnToApp()"))
    suspend fun closePddApp() = finishAndReturnToApp()

    /**
     * 详情页拟人：随机组合收藏 / 评价 / 轻滑浏览 / 走神停顿。
     */
    suspend fun maybeDetailHumanGestures() {
        if (!config.enableHumanGestures) return
        val actions = mutableListOf<String>()
        if (Random.nextDouble() < 0.12) actions.add("favorite")
        if (Random.nextDouble() < 0.42) actions.add("reviews")
        if (Random.nextDouble() < 0.55) actions.add("browse")
        if (Random.nextDouble() < 0.28) actions.add("idle")
        if (actions.isEmpty()) {
            // 至少做一次轻滑或短停，避免完全僵直
            actions.add(if (Random.nextBoolean()) "browse" else "idle")
        }
        actions.shuffle()
        log("详情拟人组合：${actions.joinToString("+")}")
        for (a in actions) {
            when (a) {
                "favorite" -> tryClickFavorite()
                "reviews" -> tryPeekReviews()
                "browse" -> randomBrowseDetail("detail_human")
                "idle" -> {
                    log("拟人：详情页走神停顿")
                    HumanBehavior.pause(config, "idle")
                }
            }
            if (Random.nextDouble() < 0.35) {
                HumanBehavior.pause(config, "think")
            }
        }
    }

    /**
     * 两大步骤之间的随机桥接拟人（采图→多规格等），提高轨迹不规则性。
     */
    suspend fun randomBridgeHuman(scene: String) {
        if (!config.enableHumanGestures) {
            HumanBehavior.pause(config, "think")
            return
        }
        val r = Random.nextDouble()
        when {
            r < 0.28 -> {
                log("桥接拟人：短停（$scene）")
                HumanBehavior.pause(config, "think")
            }
            r < 0.52 -> {
                log("桥接拟人：轻滑浏览（$scene）")
                randomBrowseDetail(scene)
            }
            r < 0.68 -> {
                log("桥接拟人：走神（$scene）")
                HumanBehavior.pause(config, "idle")
            }
            r < 0.82 -> {
                log("桥接拟人：回滑再看（$scene）")
                val dm = service().resources.displayMetrics
                val cx = HumanBehavior.jitter(dm.widthPixels * 0.5f, dm.widthPixels * 0.08f)
                humanSwipe(
                    cx,
                    HumanBehavior.jitter(dm.heightPixels * 0.36f, 30f),
                    HumanBehavior.jitter(dm.heightPixels * 0.58f, 30f),
                    purpose = "detail",
                )
                HumanBehavior.pause(config, "read")
            }
            else -> {
                // 连续小动作
                log("桥接拟人：停顿+轻滑（$scene）")
                HumanBehavior.pause(config, "think")
                if (Random.nextDouble() < 0.7) randomBrowseDetail(scene)
            }
        }
    }

    /** 详情页不规则轻滑 1~3 次 */
    private suspend fun randomBrowseDetail(scene: String) {
        val dm = service().resources.displayMetrics
        val rounds = when {
            Random.nextDouble() < 0.50 -> 1
            Random.nextDouble() < 0.75 -> 2
            else -> 3
        }
        log("拟人：详情轻滑 $rounds 次（$scene）")
        repeat(rounds) {
            val cx = HumanBehavior.jitter(dm.widthPixels * 0.48f, dm.widthPixels * 0.10f)
            val down = Random.nextDouble() < 0.72
            val y1 = HumanBehavior.jitter(dm.heightPixels * if (down) 0.66f else 0.36f, 40f)
            val span = dm.heightPixels * Random.nextDouble(0.14, 0.30).toFloat()
            val y2 = if (down) (y1 - span).coerceAtLeast(dm.heightPixels * 0.22f)
            else (y1 + span).coerceAtMost(dm.heightPixels * 0.78f)
            humanSwipe(cx, y1, y2, purpose = "detail")
            when {
                Random.nextDouble() < 0.25 -> HumanBehavior.pause(config, "idle")
                Random.nextDouble() < 0.55 -> HumanBehavior.pause(config, "read")
                else -> HumanBehavior.sleepMs(220.0, 650.0, bias = "short")
            }
        }
    }

    private suspend fun tryClickFavorite() {
        val n = A11yHelper.findByTextAllWindows(service(), "收藏", exact = true, clickableOnly = true)
            ?: A11yHelper.findByContentDescAllWindows(service(), "收藏")
        if (n == null) {
            log("拟人：未找到收藏入口")
            return
        }
        val lab = ((n.text?.toString() ?: "") + (n.contentDescription?.toString() ?: ""))
        if (lab.contains("已收藏")) {
            log("拟人：已是收藏状态，跳过")
            return
        }
        log("拟人动作：点击收藏（约1/10）")
        A11yHelper.clickNode(service(), n)
        HumanBehavior.sleepMs(500.0, 900.0)
    }

    private suspend fun tryPeekReviews() {
        val labels = listOf("评价", "商品评价", "全部评价")
        var hit: AccessibilityNodeInfo? = null
        for (label in labels) {
            hit = A11yHelper.findByTextAllWindows(service(), label, exact = label == "评价", clickableOnly = true)
                ?: A11yHelper.findByTextAllWindows(service(), label, exact = false, clickableOnly = false)
            if (hit != null) break
        }
        if (hit == null) {
            // 轻滑一次再找
            val dm = service().resources.displayMetrics
            humanSwipe(
                HumanBehavior.jitter(dm.widthPixels * 0.5f, 30f),
                dm.heightPixels * 0.70f,
                dm.heightPixels * 0.40f,
                purpose = "detail",
            )
            HumanBehavior.pause(config, "think")
            hit = A11yHelper.findByTextAllWindows(service(), "评价", exact = false, clickableOnly = true)
        }
        if (hit == null) {
            log("拟人：未找到评价入口")
            return
        }
        log("拟人动作：查看评价（约2/5）")
        HumanBehavior.pause(config, "think")
        A11yHelper.clickNode(service(), hit)
        // 进入评价页先读一会儿
        HumanBehavior.pause(config, "read")
        browseReviewsLikeHuman()
        goBackQuiet()
        HumanBehavior.pause(config, "action")
    }

    /** 评价页不规则划动 + 停顿（含偶发回滑/走神） */
    private suspend fun browseReviewsLikeHuman() {
        val dm = service().resources.displayMetrics
        val rounds = Random.nextInt(2, 5) // 2~4 次主划动
        log("拟人：评价页浏览划动 ${rounds} 次")
        repeat(rounds) { i ->
            val cx = HumanBehavior.jitter(dm.widthPixels * 0.48f, dm.widthPixels * 0.10f)
            // 幅度不规则：短滑 / 中滑 / 长滑
            val amp = when (Random.nextInt(3)) {
                0 -> 0.12f to 0.22f // 短
                1 -> 0.22f to 0.34f // 中
                else -> 0.30f to 0.42f // 长
            }
            val yStart = HumanBehavior.jitter(dm.heightPixels * Random.nextDouble(0.58, 0.74).toFloat(), 36f)
            val yEnd = (yStart - dm.heightPixels * Random.nextDouble(amp.first.toDouble(), amp.second.toDouble()).toFloat())
                .coerceAtLeast(dm.heightPixels * 0.22f)
            humanSwipe(cx, yStart, yEnd, purpose = "detail")
            // 划后停顿：阅读 / 思考 / 偶发走神
            when {
                Random.nextDouble() < 0.22 -> {
                    log("拟人：评价页走神停顿")
                    HumanBehavior.pause(config, "idle")
                }
                Random.nextDouble() < 0.45 -> HumanBehavior.pause(config, "read")
                else -> HumanBehavior.pause(config, "think")
            }
            // 偶发回滑再看一眼
            if (HumanBehavior.shouldBackscroll(config) || (i == 0 && Random.nextDouble() < 0.35)) {
                val bx = HumanBehavior.jitter(dm.widthPixels * 0.5f, dm.widthPixels * 0.08f)
                val by1 = HumanBehavior.jitter(dm.heightPixels * 0.38f, 40f)
                val by2 = HumanBehavior.jitter(dm.heightPixels * 0.58f, 40f)
                log("拟人：评价页回滑")
                humanSwipe(bx, by1, by2, purpose = "detail")
                HumanBehavior.pause(config, "think")
            }
            // 偶发极短停顿再继续
            if (Random.nextDouble() < 0.40) {
                HumanBehavior.sleepMs(180.0, 520.0, bias = "short")
            }
        }
        // 离开前再看一眼
        if (HumanBehavior.shouldLongPause(config) || Random.nextDouble() < 0.35) {
            HumanBehavior.pause(config, "read")
        } else {
            HumanBehavior.pause(config, "think")
        }
    }

    /** 轻滑到店铺条区域，尽量读到店铺销量文案 */
    suspend fun peekShopSalesText(): String {
        val first = readPageText()
        if (containsShopSalesHint(first)) return first
        val dm = service().resources.displayMetrics
        humanSwipe(
            HumanBehavior.jitter(dm.widthPixels * 0.5f, 25f),
            dm.heightPixels * 0.62f,
            dm.heightPixels * 0.38f,
            purpose = "detail",
        )
        HumanBehavior.sleepMs(350.0, 600.0)
        val second = readPageText()
        return first + "\n" + second
    }

    private fun containsShopSalesHint(text: String): Boolean {
        val t = text.replace("\\s+".toRegex(), "")
        return t.contains("本店已拼") || t.contains("店铺已拼") || t.contains("全店总售") ||
            t.contains("全店已拼") || t.contains("本店总售") ||
            (t.contains("进店") && t.contains("已拼"))
    }

    private suspend fun tryDismissPddFromRecents() {
        try {
            service().performGlobalAction(
                android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_RECENTS,
            )
            HumanBehavior.sleepMs(700.0, 1000.0)
            val page = readPageText()
            val hit = A11yHelper.findByTextAllWindows(service(), "拼多多", exact = false, clickableOnly = false)
                ?: A11yHelper.findByTextAllWindows(service(), "pinduoduo", exact = false, clickableOnly = false)
            if (hit != null) {
                val r = A11yHelper.bounds(hit)
                val screen = A11yHelper.screenRect(service())
                val x = if (r.width() > 0) r.exactCenterX() else screen.width() * 0.5f
                val y = if (r.height() > 0) r.exactCenterY() else screen.height() * 0.45f
                // 上滑划掉最近任务卡片
                A11yHelper.swipeTo(service(), x, y, x, y - screen.height() * 0.45f, 280)
                HumanBehavior.sleepMs(400.0, 700.0)
            } else if (page.contains("拼多多")) {
                val screen = A11yHelper.screenRect(service())
                A11yHelper.swipeTo(
                    service(),
                    screen.width() * 0.5f,
                    screen.height() * 0.5f,
                    screen.width() * 0.5f,
                    screen.height() * 0.12f,
                    280,
                )
                HumanBehavior.sleepMs(400.0, 700.0)
            }
        } catch (_: Exception) {
        } finally {
            try {
                service().performGlobalAction(
                    android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_HOME,
                )
            } catch (_: Exception) {
            }
        }
    }

    suspend fun betweenItems() {
        HumanBehavior.pause(config, "item")
        if (config.enableHumanGestures) {
            maybeExtraHumanAction("item")
        }
    }

    /**
     * 额外拟人：随机回滑、短暂浏览、走神停顿（不改变业务流程）。
     */
    private suspend fun maybeExtraHumanAction(scene: String) {
        val r = kotlin.random.Random.nextDouble()
        val dm = service().resources.displayMetrics
        val cx = HumanBehavior.jitter(dm.widthPixels * 0.5f, dm.widthPixels * 0.08f)
        val y1 = dm.heightPixels * 0.68f
        val y2 = dm.heightPixels * 0.38f
        when {
            r < 0.32 -> {
                log("拟人动作：随机下滑浏览（$scene）")
                humanSwipe(cx, y1, y2, purpose = "list")
                HumanBehavior.pause(config, "think")
                if (kotlin.random.Random.nextDouble() < 0.55) {
                    log("拟人动作：回滑一下")
                    humanSwipe(cx, y2 + 40f, y1 - 40f, purpose = "list")
                    HumanBehavior.pause(config, "think")
                }
            }
            r < 0.52 -> {
                log("拟人动作：走神停顿（$scene）")
                HumanBehavior.pause(config, "idle")
            }
            r < 0.68 && HumanBehavior.shouldBackscroll(config) -> {
                log("拟人动作：轻微上滑回看（$scene）")
                humanSwipe(cx, y2, y1, purpose = "list")
                HumanBehavior.pause(config, "read")
            }
            r < 0.80 -> {
                log("拟人动作：短暂停顿思考（$scene）")
                HumanBehavior.pause(config, "think")
            }
            else -> {
                // 约 20% 概率不做额外动作，只保留区间等待
            }
        }
        if (HumanBehavior.shouldLongPause(config) && kotlin.random.Random.nextDouble() < 0.4) {
            log("拟人动作：长停顿")
            HumanBehavior.pause(config, "idle")
        }
    }
}

internal fun chooseUnseenCardIndex(
    keys: List<String>,
    seen: Set<String>,
    preferredIndex: Int,
): Int? {
    if (preferredIndex in keys.indices && keys[preferredIndex] !in seen) return preferredIndex
    return keys.indices.firstOrNull { keys[it].isNotBlank() && keys[it] !in seen }
}
