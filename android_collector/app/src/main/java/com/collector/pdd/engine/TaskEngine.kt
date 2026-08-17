package com.collector.pdd.engine

import com.collector.pdd.CollectorApp
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.CollectTarget
import com.collector.pdd.data.ProductEntity
import com.collector.pdd.data.TaskEntity
import com.collector.pdd.data.OutboxEntity
import com.collector.pdd.data.OutboxPayload
import com.collector.pdd.parser.DetailReader
import com.collector.pdd.parser.ProductQualityGate
import com.collector.pdd.service.CollectA11yService
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.atomic.AtomicBoolean
import java.util.UUID

class TaskEngine(
    private val log: (String) -> Unit,
    private val onProductCollected: (suspend (localTaskId: Long, outboxId: String, product: ProductEntity, remoteItemId: Long?) -> Unit)? = null,
    private val onTaskFinished: (suspend (localTaskId: Long, status: String) -> Unit)? = null,
    /** 每成功发起一次关键词搜索（含价格/销量重搜）回调一次 */
    private val onKeywordSearched: (suspend (keyword: String) -> Unit)? = null,
    /** Excel 逐行目标完成后回传匹配成功/失败，驱动 Web 明细实时状态。 */
    private val onTargetFinished: (suspend (target: CollectTarget, matched: Boolean, message: String) -> Unit)? = null,
    /** 连续动作异常时保存现场并上报服务端。 */
    private val onActionAnomaly: (suspend (localTaskId: Long, actionName: String, message: String, pageText: String, consecutiveCount: Int) -> Unit)? = null,
) {
    private val stopFlag = AtomicBoolean(false)
    private var job: Job? = null
    private var consecutiveActionAnomalies: Int = 0
    @Volatile var currentTaskId: Long? = null
        private set

    private val timeFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")

    private class AccessIssueException(val issue: AccessIssue) : RuntimeException(issue.evidence)

    private data class AccessRuntime(
        var batchCount: Int = 0,
        var consecutiveSoldOut: Int = 0,
    )

    fun isRunning(): Boolean = job?.isActive == true

    private suspend fun searchKeywordCounted(actions: PddActions, keyword: String) {
        actions.searchKeyword(keyword)
        try {
            onKeywordSearched?.invoke(keyword)
        } catch (_: Exception) {
        }
    }

    private suspend fun reportTargetResult(target: CollectTarget, matched: Boolean, message: String) {
        try {
            onTargetFinished?.invoke(target, matched, message)
        } catch (e: Exception) {
            log("目标结果上报失败 item=${target.remoteItemId ?: "-"}: ${e.message}")
        }
    }

    /** 确保每件商品结束后都有可用列表；返回栈异常时重搜当前关键词兜底。 */
    private suspend fun recordActionAnomaly(
        config: CollectConfig,
        localTaskId: Long,
        actionName: String,
        message: String,
        pageText: String = "",
    ) {
        consecutiveActionAnomalies++
        log("动作异常[$actionName] 连续=$consecutiveActionAnomalies: $message")
        try {
            onActionAnomaly?.invoke(localTaskId, actionName, message, pageText.take(4000), consecutiveActionAnomalies)
        } catch (e: Exception) {
            log("异常现场上报失败: ${e.message}")
        }
        val threshold = config.anomalyStopThreshold
        if (threshold > 0 && consecutiveActionAnomalies >= threshold) {
            stopFlag.set(true)
            log("连续动作异常达到阈值 $threshold，自动终止本次任务")
        }
    }

    private suspend fun restoreSearchList(actions: PddActions, keyword: String): Boolean {
        if (actions.returnToSearchList()) return true
        log("未恢复商品列表，重新搜索【$keyword】后继续后续商品")
        return try {
            searchKeywordCounted(actions, keyword)
            actions.scrollList(2)
            val ok = actions.looksLikeSearchList() || actions.listCardsOrEmpty().isNotEmpty()
            log(if (ok) "重新搜索后商品列表已恢复" else "重新搜索后列表仍为空")
            ok
        } catch (e: Exception) {
            log("重新搜索恢复列表失败: ${e.message}")
            false
        }
    }

    fun stop() {
        stopFlag.set(true)
        job?.cancel()
        log("正在停止任务…")
    }

    fun start(scope: kotlinx.coroutines.CoroutineScope, config: CollectConfig) {
        if (isRunning()) {
            log("任务正在运行中")
            return
        }
        if (!CollectA11yService.isEnabled()) {
            log("请先开启无障碍服务（联机工具）")
            return
        }
        val kws = config.keywords.map { it.trim() }.filter { it.isNotEmpty() }
        if (kws.isEmpty()) {
            log("请先输入关键词")
            return
        }
        stopFlag.set(false)
        consecutiveActionAnomalies = 0
        job = scope.launch {
            try {
                runTask(config.copy(keywords = kws))
            } catch (e: CancellationException) {
                log("任务已取消")
                throw e
            } catch (e: Exception) {
                log("任务异常: ${e.message}")
            }
        }
    }

    private suspend fun runTask(config: CollectConfig) = coroutineScope {
        val db = CollectorApp.instance.database
        val now = LocalDateTime.now().format(timeFmt)
        val taskId = db.taskDao().insert(
            TaskEntity(
                taskName = "手机采集",
                startTime = now,
                keywordList = config.targets.takeIf { it.isNotEmpty() }
                    ?.joinToString(",") { it.keyword }
                    ?: config.keywords.joinToString(","),
                status = "running",
                remoteTaskId = config.remoteTaskId,
            )
        )
        currentTaskId = taskId
        CollectA11yService.instance?.updateNotification("采集中 task=$taskId")
        log(
                "任务启动 task_id=$taskId 关键词数=${config.targets.takeIf { it.isNotEmpty() }?.size ?: config.keywords.size} " +
                "匹配目标=${config.targets.count { it.requiresMatch }} " +
                "N=${config.maxDetailPerKeyword} 商品间隔=${config.itemGapMinMs / 1000}~${config.itemGapMaxMs / 1000}s " +
                "批次=${config.batchSize}/${config.batchCooldownMs / 1000}s 繁忙=${config.busyResponse} 拟人=${config.humanLevel}"
        )

        val actions = PddActions(log, config)
        val accessRuntime = AccessRuntime()
        var total = 0
        var success = 0
        var fail = 0
        var endStatus = "finished"

        try {
            actions.openPdd()

            val workItems = config.targets.takeIf { it.isNotEmpty() }
                ?: config.keywords.map { CollectTarget(keyword = it) }
            for ((idx, target) in workItems.withIndex()) {
                val kw = target.keyword
                ensureActive()
                if (stopFlag.get()) break
                if (idx > 0) {
                    log("关键词间隙拟人休息…")
                    actions.betweenKeywords()
                }
                log(
                    "======= 开始关键词：$kw" +
                        if (target.requiresMatch) {
                            " 目标准字=${target.targetApproval} 目标规格=${target.targetSpec} ======="
                        } else {
                            " ======="
                        }
                )
                try {
                    searchKeywordCounted(actions, kw)

                    if (config.taskType == "nurture") {
                        actions.scrollList(2)
                        total++
                        val (opened, _) = actions.openCardAt(0)
                        if (opened) {
                            HumanBehavior.sleepMs(config.readMinMs.toDouble(), config.readMaxMs.toDouble())
                            restoreSearchList(actions, kw)
                            success++
                            reportTargetResult(target, true, "账号养护浏览完成")
                        } else {
                            fail++
                            reportTargetResult(target, false, "账号养护未找到可浏览商品")
                        }
                        continue
                    }

                    val n = config.maxDetailPerKeyword.coerceAtLeast(1)
                    if (target.requiresMatch) {
                        // 匹配任务必须从搜索结果顶部开始核对，禁止预先滚动跳过首屏商品。
                        log("【$kw】逐个核对前 $n 个，命中准字+规格后停止")
                        var found = false
                        for (i in 0 until n) {
                            ensureActive()
                            if (stopFlag.get()) break
                            total++
                            val slot = "target_match_${i + 1}"
                            val ok = if (confirmed(config, kw, slot)) true else collectOneWithPolicy(
                                actions, dbTaskId = taskId, keyword = kw,
                                pickTag = slot,
                                openIndex = i,
                                target = target,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) {
                                success++
                                found = true
                                break
                            }
                            if (!stopFlag.get()) actions.betweenItems()
                        }
                        if (!found && !stopFlag.get()) {
                            fail++
                            val message = "匹配失败：前 $n 个商品未找到准字=${target.targetApproval}、规格=${target.targetSpec}"
                            log(message)
                            reportTargetResult(target, false, message)
                        } else if (found) {
                            reportTargetResult(
                                target,
                                true,
                                "采集成功，准字=${target.targetApproval}、规格=${target.targetSpec}匹配成功",
                            )
                        }
                    } else {
                        // 普通采集保留轻量浏览；搜索动作自身已确认结果页就绪。
                        actions.scrollList(2)
                        log("【$kw】搜索列表，采集前 $n 个")
                        for (i in 0 until n) {
                            ensureActive()
                            if (stopFlag.get()) break
                            total++
                            val slot = "default_top_${i + 1}"
                            val ok = if (confirmed(config, kw, slot)) true else collectOneWithPolicy(
                                actions, dbTaskId = taskId, keyword = kw,
                                pickTag = slot,
                                openIndex = i,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) success++ else fail++
                            if (!stopFlag.get()) actions.betweenItems()
                        }
                    }

                    // 2) 价格第 1
                    if (!target.requiresMatch && config.enablePriceSort && !stopFlag.get() && isActive) {
                        log("拟人休息后执行：价格升序…")
                        actions.betweenItems()
                        try {
                            searchKeywordCounted(actions, kw)
                            actions.sortByPriceAsc()
                            total++
                            val ok = if (confirmed(config, kw, "price_asc_first")) true else collectOneWithPolicy(
                                actions, dbTaskId = taskId, keyword = kw,
                                pickTag = "price_asc_first",
                                openIndex = 0,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) success++ else fail++
                        } catch (e: Exception) {
                            fail++
                            log("价格排序采集失败: ${e.message}")
                        }
                    }

                    // 3) 销量第 1
                    if (!target.requiresMatch && config.enableSalesSort && !stopFlag.get() && isActive) {
                        log("拟人休息后执行：销量降序…")
                        actions.betweenItems()
                        try {
                            searchKeywordCounted(actions, kw)
                            actions.sortBySalesDesc()
                            total++
                            val ok = if (confirmed(config, kw, "sales_desc_first")) true else collectOneWithPolicy(
                                actions, dbTaskId = taskId, keyword = kw,
                                pickTag = "sales_desc_first",
                                openIndex = 0,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) success++ else fail++
                        } catch (e: Exception) {
                            fail++
                            log("销量排序采集失败: ${e.message}")
                        }
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    fail++
                    log("关键词失败 $kw err=${e.message}")
                    if (target.requiresMatch) {
                        reportTargetResult(target, false, "采集失败：${e.message ?: "未知异常"}")
                    }
                }
            }

            endStatus = when {
                stopFlag.get() -> "stopped"
                success == 0 && fail > 0 -> "failed"
                else -> "finished"
            }
        } catch (e: CancellationException) {
            endStatus = "stopped"
            throw e
        } catch (e: Exception) {
            endStatus = "failed"
            log("任务异常退出: ${e.message}")
        } finally {
            withContext(NonCancellable) {
                val task = db.taskDao().get(taskId)?.copy(
                    endTime = LocalDateTime.now().format(timeFmt),
                    totalCount = total,
                    successCount = success,
                    failCount = fail,
                    status = endStatus,
                )
                if (task != null) db.taskDao().update(task)
                CollectA11yService.instance?.updateNotification("采集结束 $endStatus")
                log("任务结束 status=$endStatus total=$total success=$success fail=$fail")
                try {
                    // 终止/完成：先回拼多多首页，再回联机工具主界面
                    actions.finishAndReturnToApp()
                } catch (e: Exception) {
                    log("返回联机工具失败: ${e.message}")
                }
                try {
                    onTaskFinished?.invoke(taskId, endStatus)
                } catch (e: Exception) {
                    log("任务结束确认入队失败，将在 Agent 恢复时补偿: ${e.message}")
                }
                currentTaskId = null
            }
        }
    }

    private suspend fun afterItem(config: CollectConfig, runtime: AccessRuntime) {
        runtime.batchCount++
        if (config.batchSize > 0 && runtime.batchCount >= config.batchSize && !stopFlag.get()) {
            runtime.batchCount = 0
            val seconds = config.batchCooldownMs / 1000
            log("已完成 ${config.batchSize} 个商品，本批冷却 ${seconds} 秒…")
            if (config.batchCooldownMs > 0) delay(config.batchCooldownMs)
        }
    }

    private fun confirmed(config: CollectConfig, keyword: String, pickTag: String): Boolean {
        val key = "$keyword|$pickTag"
        if (key !in config.confirmedSlots) return false
        log("Checkpoint 已确认，跳过重复采集【$keyword/$pickTag】")
        return true
    }

    private suspend fun collectOneWithPolicy(
        actions: PddActions,
        dbTaskId: Long,
        keyword: String,
        pickTag: String,
        openIndex: Int,
        config: CollectConfig,
        runtime: AccessRuntime,
        target: CollectTarget? = null,
    ): Boolean {
        var retries = 0
        while (!stopFlag.get()) {
            try {
                val ok = collectOne(actions, dbTaskId, keyword, pickTag, openIndex, target, config)
                runtime.consecutiveSoldOut = 0
                if (ok) consecutiveActionAnomalies = 0
                afterItem(config, runtime)
                return ok
            } catch (e: AccessIssueException) {
                if (e.issue.type == AccessIssueType.SOLD_OUT) {
                    runtime.consecutiveSoldOut++
                    log("检测到售罄/下架：${e.issue.evidence}，连续 ${runtime.consecutiveSoldOut} 个")
                    runCatching { restoreSearchList(actions, keyword) }
                    val threshold = config.soldOutStopThreshold
                    if (threshold > 0 && runtime.consecutiveSoldOut >= threshold) {
                        log("连续售罄达到阈值 $threshold，停止本次任务")
                        stopFlag.set(true)
                    }
                    afterItem(config, runtime)
                    return false
                }

                runtime.consecutiveSoldOut = 0
                val issueLabel = if (e.issue.type == AccessIssueType.RISK) "疑似风控" else "访问繁忙"
                recordActionAnomaly(config, dbTaskId, "access_guard", e.issue.evidence, actions.readPageText())
                if (stopFlag.get()) return false
                val response = config.busyResponse.lowercase()
                log("检测到$issueLabel：${e.issue.evidence}，回复策略=$response")
                if (response == "stop") {
                    stopFlag.set(true)
                    log("已按策略停止本次任务")
                    return false
                }
                if (response == "skip") {
                    runCatching { restoreSearchList(actions, keyword) }
                    log("已按策略跳过当前商品")
                    afterItem(config, runtime)
                    return false
                }
                if (retries >= config.busyRetryCount) {
                    log("自动重试次数已用完（${config.busyRetryCount} 次），跳过当前商品")
                    runCatching { restoreSearchList(actions, keyword) }
                    afterItem(config, runtime)
                    return false
                }

                retries++
                val base = if (e.issue.type == AccessIssueType.RISK) {
                    config.riskCooldownMs
                } else {
                    config.busyCooldownMs
                }
                val cooldown = (base * retries).coerceAtMost(30 * 60 * 1000L)
                log("第 $retries 次恢复：冷却 ${cooldown / 1000} 秒后重试当前商品")
                runCatching { actions.goToPddHome() }
                delay(cooldown)
                searchKeywordCounted(actions, keyword)
                actions.scrollList(2)
            }
        }
        return false
    }

    private suspend fun collectOne(
        actions: PddActions,
        dbTaskId: Long,
        keyword: String,
        pickTag: String,
        openIndex: Int,
        target: CollectTarget? = null,
        config: CollectConfig,
    ): Boolean {
        return try {
            val (opened, listMeta) = actions.openCardAt(openIndex)
            if (!opened) {
                recordActionAnomaly(config, dbTaskId, "open_card", "列表为空或第 ${openIndex + 1} 个商品无法打开", actions.readPageText())
                return false
            }
            AccessGuard.detect(actions.readPageText())?.let { throw AccessIssueException(it) }

            // 1) 刚进详情主图在顶部：先一键保存采图
            HumanBehavior.sleepMs(900.0, 1600.0)
            val probeImages = actions.tryProbeMainImage(listMeta.itemId, alreadyAtTop = true)
            // 采图曾误把详情主图「1/5」当大图预览再 Back，导致退到列表；此处强制校验并重进
            if (!actions.ensureOnGoodsDetail(openIndex)) {
                recordActionAnomaly(config, dbTaskId, "restore_detail", "采图后未能停留在商品详情", actions.readPageText())
                AccessGuard.detect(actions.readPageText())?.let { throw AccessIssueException(it) }
                log("采图后未能停留在商品详情，放弃本条后续取链/读参")
                return false
            }

            // 采图后先轻读一屏价格（底栏弹层打开后可能消失）
            HumanBehavior.sleepMs(350.0, 800.0)
            var priceText = actions.readPageText()
            var shopSalesText = ""
            var skuPanelText = ""
            var paramsText = ""

            // 2) 商品信息采集：永久固定在采图之后，固定顺序（不再随机）
            //    多规格 → 商品参数 → 店铺销量 → 详情拟人
            val midSteps = listOf("sku", "params", "shop_sales", "human")
            log("采图后固定执行商品信息采集：${midSteps.joinToString(" → ")}")
            for ((idx, step) in midSteps.withIndex()) {
                if (idx > 0) {
                    try {
                        actions.randomBridgeHuman("step_$step")
                    } catch (_: Exception) {
                    }
                }
                when (step) {
                    "shop_sales" -> {
                        shopSalesText = try {
                            actions.peekShopSalesText()
                        } catch (_: Exception) {
                            ""
                        }
                        priceText = priceText + "\n" + actions.readPageText()
                    }
                    "human" -> {
                        try {
                            actions.maybeDetailHumanGestures()
                        } catch (e: Exception) {
                            log("详情拟人动作异常: ${e.message}")
                        }
                    }
                    "sku" -> {
                        skuPanelText = try {
                            actions.openAndReadSkuPrices()
                        } catch (e: Exception) {
                            log("多规格读取失败: ${e.message}")
                            ""
                        }
                        if (!actions.ensureOnGoodsDetail(openIndex)) {
                            log("读规格后已离开详情，尝试恢复失败")
                        }
                        priceText = priceText + "\n" + actions.readPageText()
                    }
                    "params" -> {
                        paramsText = try {
                            actions.openAndReadProductParams()
                        } catch (e: Exception) {
                            log("商品参数读取失败: ${e.message}")
                            ""
                        }
                        if (!actions.ensureOnGoodsDetail(openIndex)) {
                            log("读参数后已离开详情，尝试恢复失败")
                        }
                    }
                }
            }

            // 3) 分享取链放较后（读参/规格后常需回顶）
            try {
                actions.randomBridgeHuman("before_share")
            } catch (_: Exception) {
            }
            if (!actions.ensureOnGoodsDetail(openIndex)) {
                log("取链前不在详情页，跳过分享取链")
            }
            log("开始复制链接解析…")
            val share = if (actions.looksLikeGoodsDetail()) {
                actions.tryCaptureShareLink()
            } else {
                PddActions.ShareCapture()
            }

            val harvest = actions.harvestPage()
            val mainText = actions.readPageText()

            // 6) 无障碍解析商品字段
            val a11yPageText = buildString {
                append(priceText)
                append('\n')
                if (shopSalesText.isNotBlank()) {
                    append(shopSalesText)
                    append('\n')
                }
                append(mainText)
                if (paramsText.isNotBlank()) {
                    append('\n')
                    append("---商品参数---\n")
                    append(paramsText)
                }
                if (skuPanelText.isNotBlank()) {
                    append('\n')
                    append("---多规格售价---\n")
                    append(skuPanelText)
                }
            }
            var product = DetailReader.parse(
                pageText = a11yPageText,
                keyword = keyword,
                pickTag = pickTag,
                listPrice = listMeta.listPrice,
                itemIdHint = listMeta.itemId,
                shopIdHint = harvest.mallId,
                imageHints = emptyList(),
                urlHint = "",
                skuPanelText = skuPanelText,
            ).copy(taskId = dbTaskId)
            if (target?.requiresMatch == true) {
                val match = ProductTargetMatcher.match(
                    expectedApproval = target.targetApproval,
                    expectedName = target.targetName,
                    expectedSpec = target.targetSpec,
                    expectedManufacturer = target.targetManufacturer,
                    actualApproval = product.approvalNo,
                    actualName = product.productName.ifBlank { product.sellName },
                    actualSpec = product.spec,
                    actualManufacturer = product.manufacturer,
                )
                if (!match.matched) {
                    log(
                        "匹配跳过【$pickTag】" +
                            "准字=${match.actualApproval.ifBlank { "-" }}/${match.expectedApproval} " +
                            "规格=${match.actualSpec.ifBlank { "-" }}/${match.expectedSpec} " +
                            "准字命中=${match.approvalMatched} 规格命中=${match.specMatched}"
                    )
                    restoreSearchList(actions, keyword)
                    return false
                }
                log(
                    "匹配命中【$pickTag】准字=${product.approvalNo} 规格=${product.spec} " +
                        "item=${target.remoteItemId ?: "-"}"
                )
            }
            if (product.skuPricesText.isNotBlank()) {
                log("多规格售价已写入: ${product.skuPricesText.take(180)}")
            }

            // 6) 分享结果直接写入；网络负责 ps= 短链展开 + 补图
            var shareId = share.goodsId
                .ifBlank { GoodsLinkResolver.extractGoodsId(share.url) }
                .ifBlank { GoodsLinkResolver.extractGoodsId(share.raw) }
            var shareUrl = when {
                share.url.isNotBlank() -> share.url
                shareId.isNotBlank() -> GoodsLinkResolver.buildGoodsUrl(shareId)
                else -> GoodsLinkResolver.extractGoodsUrls(share.raw).firstOrNull().orEmpty()
            }
            // 复制链接常见：goods1.html?ps=UvSyTr2i6T → 307 出 goods_id
            if (shareId.isBlank() && (shareUrl.contains("ps=", true) ||
                    shareUrl.contains("goods1.html", true) ||
                    share.raw.contains("ps=", true))
            ) {
                log("检测到 ps= 分享链，正在展开…")
                val expanded = try {
                    withContext(Dispatchers.IO) {
                        GoodsLinkResolver.expandShareLink(
                            shareUrl.ifBlank { share.raw },
                        )
                    }
                } catch (e: Exception) {
                    log("ps= 展开失败: ${e.message}")
                    GoodsLinkResolver.Resolved()
                }
                if (expanded.goodsId.isNotBlank()) {
                    shareId = expanded.goodsId
                    shareUrl = expanded.itemUrl.ifBlank {
                        GoodsLinkResolver.buildGoodsUrl(expanded.goodsId)
                    }
                    log("ps= 展开成功 id=$shareId")
                } else if (expanded.itemUrl.isNotBlank() && shareUrl.isBlank()) {
                    shareUrl = expanded.itemUrl
                }
            }
            if (shareId.isNotBlank() || shareUrl.isNotBlank()) {
                product = product.copy(
                    itemId = shareId.ifBlank { product.itemId },
                    itemUrl = shareUrl.ifBlank { product.itemUrl },
                )
                log(
                    "已写入分享链 id=${product.itemId.ifBlank { "-" }} " +
                        "url=${product.itemUrl.ifBlank { "-" }.take(90)}"
                )
            } else if (share.raw.isNotBlank()) {
                val prev = share.raw.replace("\n", " ").take(100)
                if (prev.contains("http", true) || prev.contains("ps=", true) ||
                    prev.contains("yangkeduo", true)
                ) {
                    log("分享有内容但未解析出链 preview=$prev")
                } else {
                    log("分享未拿到链接（非URL文本已忽略）")
                }
            } else {
                log("分享未拿到链接，无法写商品ID/链接")
            }

            val expectTokens = listOf(keyword, product.productName, product.brand, product.sellName)
                .flatMap { it.split(" ", "　", "/", "·", ",") }
                .map { it.trim() }
                .filter { it.length >= 2 }
                .distinct()
            val resolved = try {
                GoodsLinkResolver.resolve(
                    rawShare = share.raw.take(4000),
                    hintUrl = shareUrl.ifBlank { product.itemUrl },
                    hintGoodsId = shareId.ifBlank { product.itemId },
                    expectTokens = expectTokens,
                )
            } catch (e: Exception) {
                log("网络解析跳过: ${e.message}")
                GoodsLinkResolver.Resolved()
            }
            if (resolved.rejected && resolved.itemUrl.isBlank() && resolved.goodsId.isBlank()) {
                log("网络补图跳过（防串号）: ${resolved.rejectReason}")
            } else if (resolved.goodsId.isNotBlank()) {
                // 仅当分享没拿到 ID，或网络 ID 与分享一致时，才用网络结果
                val idOk = shareId.isBlank() || shareId == resolved.goodsId
                if (idOk) {
                    log(
                        "网络补齐 id=${resolved.goodsId} 图=${resolved.images.size} " +
                            "title=${resolved.title.take(40)}"
                    )
                    product = product.copy(
                        itemId = resolved.goodsId,
                        itemUrl = resolved.itemUrl.ifBlank {
                            GoodsLinkResolver.buildGoodsUrl(resolved.goodsId)
                        },
                    )
                    if (resolved.images.isNotEmpty()) {
                        product = product.copy(mainImages = resolved.images.joinToString("|"))
                    }
                } else {
                    log("网络ID与分享不一致，保留分享ID share=$shareId net=${resolved.goodsId}")
                    if (resolved.images.isNotEmpty() && product.mainImages.isBlank()) {
                        product = product.copy(mainImages = resolved.images.joinToString("|"))
                    }
                }
            } else {
                if (resolved.itemUrl.isNotBlank() && product.itemUrl.isBlank()) {
                    product = product.copy(itemUrl = resolved.itemUrl)
                    log("网络仅拿到短链，已写入链接")
                }
                if (resolved.images.isNotEmpty() && product.mainImages.isBlank()) {
                    product = product.copy(mainImages = resolved.images.joinToString("|"))
                }
                if (resolved.rejectReason.isNotBlank()) {
                    log("网络未解析出ID: ${resolved.rejectReason}")
                }
            }

            val localImgs = buildList {
                if (listMeta.imageHint.isNotBlank()) add(listMeta.imageHint)
                addAll(probeImages)
                addAll(share.images)
                addAll(harvest.images)
            }.filter { GoodsLinkResolver.isProductImageUrl(it) }.distinct()
            if (product.mainImages.isBlank() && localImgs.isNotEmpty()) {
                product = product.copy(mainImages = localImgs.joinToString("|"))
            }
            // 若采图时还没有商品ID，用最终 ID 重命名提示即可；不再截图冒充
            if (product.mainImages.isBlank()) {
                log("图片为空：一键保存/相册抓取未成功（请看上方「开始一键保存采图」日志）")
            }
            if (product.mainImages.isNotBlank()) {
                product = product.copy(
                    mainImages = product.mainImages.split("|")
                        .filter { GoodsLinkResolver.isProductImageUrl(it) }
                        .distinct()
                        .joinToString("|"),
                )
            }
            // 有 ID 无链接时补全
            if (product.itemId.isNotBlank() && product.itemUrl.isBlank()) {
                product = product.copy(itemUrl = GoodsLinkResolver.buildGoodsUrl(product.itemId))
            }

            val (checkedProduct, quality) = ProductQualityGate.apply(a11yPageText, product)
            product = checkedProduct
            if (!quality.accepted) {
                recordActionAnomaly(
                    config,
                    dbTaskId,
                    "quality_gate",
                    "page=${quality.pageStatus} parse=${quality.parseStatus} quality=${quality.qualityStatus} missing=${quality.missingFields}",
                    a11yPageText,
                )
                log("质量门禁拒绝【$pickTag】：page=${quality.pageStatus} missing=${quality.missingFields}")
                restoreSearchList(actions, keyword)
                return false
            }

            val remoteTask = config.remoteTaskId
            if (remoteTask == null) {
                CollectorApp.instance.database.productDao().insert(product)
            } else {
                val payload = OutboxPayload.product(product, config.platformCode)
                val outboxId = "p-$remoteTask-${UUID.randomUUID()}"
                val remoteItemId = target?.remoteItemId?.takeIf { target.requiresMatch }
                val event = OutboxEntity(
                    outboxId = outboxId,
                    eventType = "product",
                    remoteTaskId = remoteTask,
                    taskItemId = remoteItemId,
                    payloadJson = payload.toString(),
                    requiredImageCount = OutboxPayload.localImageCount(payload),
                    jobId = config.remoteJobId,
                    attemptId = config.attemptId,
                    leaseToken = config.leaseToken,
                    workerId = config.workerId,
                    traceId = config.traceId,
                    checkpointVersion = config.checkpointVersion,
                )
                CollectorApp.instance.database.outboxDao().insertProductAndOutbox(product, event)
                try {
                    onProductCollected?.invoke(dbTaskId, outboxId, product, remoteItemId)
                } catch (e: Exception) {
                    // Product + outbox are already durable.  Network delivery is retried by AgentCoordinator.
                    log("商品已进入待上报队列 outbox=$outboxId err=${e.message}")
                }
            }
            log(
                "采集并持久化【$pickTag】id=${product.itemId.ifBlank { "-" }} " +
                    "展示价=${product.displayPrice ?: "-"} 单买=${product.dealPrice ?: "-"} " +
                    "准字=${product.approvalNo.ifBlank { "-" }} 厂家=${product.manufacturer.ifBlank { "-" }} " +
                    "图=${if (product.mainImages.isBlank()) 0 else product.mainImages.split("|").size} " +
                    "链=${if (product.itemUrl.isBlank()) "-" else "有"} " +
                    "参数=${if (paramsText.isBlank()) "未开" else "已开"}"
            )
            // 必须确认回到可点击的商品列表；返回栈异常时自动重新搜索。
            restoreSearchList(actions, keyword)
            true
        } catch (e: AccessIssueException) {
            throw e
        } catch (e: Exception) {
            log("本条失败 $pickTag err=${e.message}")
            try { restoreSearchList(actions, keyword) } catch (_: Exception) {}
            false
        }
    }

}
