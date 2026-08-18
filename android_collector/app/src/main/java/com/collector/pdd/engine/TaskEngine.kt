package com.collector.pdd.engine

import com.collector.pdd.CollectorApp
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.CollectTarget
import com.collector.pdd.data.AppDatabase
import com.collector.pdd.data.ProductEntity
import com.collector.pdd.data.TaskEntity
import com.collector.pdd.data.OutboxEntity
import com.collector.pdd.data.OutboxPayload
import com.collector.pdd.collector.Collector
import com.collector.pdd.collector.CollectorRegistry
import com.collector.pdd.collector.CollectorSession
import com.collector.pdd.collector.CollectorException
import com.collector.pdd.collector.CollectorErrorAction
import com.collector.pdd.collector.CollectorErrorPolicy
import com.collector.pdd.collector.CollectorRetryDisposition
import com.collector.pdd.collector.DetailCollectionRequest
import com.collector.pdd.collector.SearchRequest
import com.collector.pdd.collector.SearchSort
import com.collector.pdd.collector.SystemCollectorError
import com.collector.pdd.collector.search
import com.collector.pdd.collector.restoreSearch
import com.collector.pdd.collector.collectDetail
import com.collector.pdd.service.CollectA11yService
import kotlinx.coroutines.CancellationException
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
    private val databaseProvider: () -> AppDatabase = { CollectorApp.instance.database },
    private val accessibilityEnabled: () -> Boolean = { CollectA11yService.isEnabled() },
    private val updateNotification: (String) -> Unit = { CollectA11yService.instance?.updateNotification(it) },
) {
    private val stopFlag = AtomicBoolean(false)
    private var job: Job? = null
    private var consecutiveActionAnomalies: Int = 0
    @Volatile var currentTaskId: Long? = null
        private set

    private val timeFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")

    private data class AccessRuntime(
        var batchCount: Int = 0,
        var consecutiveSoldOut: Int = 0,
    )

    fun isRunning(): Boolean = job?.isActive == true

    private suspend fun searchKeywordCounted(
        collector: Collector,
        actions: CollectorSession,
        keyword: String,
        sort: SearchSort = SearchSort.DEFAULT,
        prefetchPages: Int = 0,
    ) {
        collector.search(actions, SearchRequest(keyword, sort = sort, prefetchPages = prefetchPages))
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

    private suspend fun restoreSearchList(collector: Collector, actions: CollectorSession, keyword: String): Boolean {
        return try {
            val result = collector.restoreSearch(
                actions,
                SearchRequest(keyword, prefetchPages = 2),
            )
            if (result.researched) {
                log("未恢复商品列表，已重新搜索【$keyword】")
                try { onKeywordSearched?.invoke(keyword) } catch (_: Exception) {}
            }
            log(if (result.restored) "商品列表已恢复" else "商品列表仍不可用")
            result.restored
        } catch (e: CollectorException) {
            if (CollectorErrorPolicy.action(e) == CollectorErrorAction.FAIL_FAST) throw e
            log("重新搜索恢复列表失败 code=${e.code}: ${e.message}")
            false
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
        if (!accessibilityEnabled()) {
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

    internal suspend fun awaitCompletionForTest() {
        job?.join()
    }

    private suspend fun runTask(config: CollectConfig) = coroutineScope {
        val db = databaseProvider()
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
        updateNotification("采集中 task=$taskId")
        log(
                "任务启动 task_id=$taskId 关键词数=${config.targets.takeIf { it.isNotEmpty() }?.size ?: config.keywords.size} " +
                "匹配目标=${config.targets.count { it.requiresMatch }} " +
                "N=${config.maxDetailPerKeyword} 商品间隔=${config.itemGapMinMs / 1000}~${config.itemGapMaxMs / 1000}s " +
                "批次=${config.batchSize}/${config.batchCooldownMs / 1000}s 繁忙=${config.busyResponse} 拟人=${config.humanLevel}"
        )

        val accessRuntime = AccessRuntime()
        var total = 0
        var success = 0
        var fail = 0
        var endStatus = "finished"
        var sessionForCleanup: CollectorSession? = null

        try {
            val collector = CollectorRegistry.require(config.platformCode)
            val actions = collector.createSession(log, config)
            sessionForCleanup = actions
            actions.start()

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
                    searchKeywordCounted(
                        collector,
                        actions,
                        kw,
                        prefetchPages = if (target.requiresMatch) 0 else 2,
                    )

                    if (config.taskType == "nurture") {
                        total++
                        val opened = actions.browseCandidate(0, config.readMinMs, config.readMaxMs)
                        if (opened) {
                            restoreSearchList(collector, actions, kw)
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
                                collector, actions, dbTaskId = taskId, keyword = kw,
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
                        log("【$kw】搜索列表，采集前 $n 个")
                        for (i in 0 until n) {
                            ensureActive()
                            if (stopFlag.get()) break
                            total++
                            val slot = "default_top_${i + 1}"
                            val ok = if (confirmed(config, kw, slot)) true else collectOneWithPolicy(
                                collector, actions, dbTaskId = taskId, keyword = kw,
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
                            searchKeywordCounted(collector, actions, kw, sort = SearchSort.PRICE_ASC)
                            total++
                            val ok = if (confirmed(config, kw, "price_asc_first")) true else collectOneWithPolicy(
                                collector, actions, dbTaskId = taskId, keyword = kw,
                                pickTag = "price_asc_first",
                                openIndex = 0,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) success++ else fail++
                        } catch (e: CollectorException) {
                            if (CollectorErrorPolicy.action(e) == CollectorErrorAction.FAIL_FAST) throw e
                            fail++
                            log("价格排序采集失败 code=${e.code}: ${e.message}")
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
                            searchKeywordCounted(collector, actions, kw, sort = SearchSort.SALES_DESC)
                            total++
                            val ok = if (confirmed(config, kw, "sales_desc_first")) true else collectOneWithPolicy(
                                collector, actions, dbTaskId = taskId, keyword = kw,
                                pickTag = "sales_desc_first",
                                openIndex = 0,
                                config = config,
                                runtime = accessRuntime,
                            )
                            if (ok) success++ else fail++
                        } catch (e: CollectorException) {
                            if (CollectorErrorPolicy.action(e) == CollectorErrorAction.FAIL_FAST) throw e
                            fail++
                            log("销量排序采集失败 code=${e.code}: ${e.message}")
                        } catch (e: Exception) {
                            fail++
                            log("销量排序采集失败: ${e.message}")
                        }
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: CollectorException) {
                    if (CollectorErrorPolicy.action(e) == CollectorErrorAction.FAIL_FAST) throw e
                    fail++
                    log("关键词失败 $kw code=${e.code} err=${e.message}")
                    if (target.requiresMatch) reportTargetResult(target, false, "采集失败：${e.message ?: e.code.name}")
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
                updateNotification("采集结束 $endStatus")
                log("任务结束 status=$endStatus total=$total success=$success fail=$fail")
                try {
                    // 终止/完成：由 Collector 收尾平台页面，再回联机工具主界面。
                    sessionForCleanup?.finish()
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
        collector: Collector,
        actions: CollectorSession,
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
                val ok = collectOne(collector, actions, dbTaskId, keyword, pickTag, openIndex, target, config)
                runtime.consecutiveSoldOut = 0
                if (ok) consecutiveActionAnomalies = 0
                afterItem(config, runtime)
                return ok
            } catch (e: CollectorException) {
                when (CollectorErrorPolicy.action(e)) {
                    CollectorErrorAction.FAIL_FAST -> throw e

                    CollectorErrorAction.STOP_TASK -> {
                        runtime.consecutiveSoldOut = 0
                        recordActionAnomaly(config, dbTaskId, "collector_stop", e.message.orEmpty(), e.evidence)
                        stopFlag.set(true)
                        log("采集器要求停止任务 code=${e.code}: ${e.message}")
                        afterItem(config, runtime)
                        return false
                    }

                    CollectorErrorAction.FAIL_ITEM -> {
                        if (e.code == SystemCollectorError.ITEM_UNAVAILABLE) {
                            runtime.consecutiveSoldOut++
                            log("检测到售罄/下架：${e.message}，连续 ${runtime.consecutiveSoldOut} 个")
                            val threshold = config.soldOutStopThreshold
                            if (threshold > 0 && runtime.consecutiveSoldOut >= threshold) {
                                log("连续售罄达到阈值 $threshold，停止本次任务")
                                stopFlag.set(true)
                            }
                        } else {
                            runtime.consecutiveSoldOut = 0
                            log("当前商品失败 code=${e.code}: ${e.message}")
                            if (e.code == SystemCollectorError.PARSE_ERROR ||
                                e.code == SystemCollectorError.DATA_QUALITY_FAILURE
                            ) {
                                recordActionAnomaly(config, dbTaskId, "collector_item", e.message.orEmpty(), e.evidence)
                            }
                        }
                        runCatching { restoreSearchList(collector, actions, keyword) }
                        afterItem(config, runtime)
                        return false
                    }

                    CollectorErrorAction.RETRY -> {
                        runtime.consecutiveSoldOut = 0
                        recordActionAnomaly(config, dbTaskId, "access_guard", e.message.orEmpty(), e.evidence)
                        if (stopFlag.get()) return false
                        val response = config.busyResponse.lowercase()
                        log("采集器暂时失败 code=${e.code}: ${e.message}，回复策略=$response")
                        when (CollectorErrorPolicy.retryDisposition(e, response, retries, config.busyRetryCount)) {
                            CollectorRetryDisposition.STOP -> {
                                stopFlag.set(true)
                                return false
                            }
                            CollectorRetryDisposition.SKIP,
                            CollectorRetryDisposition.EXHAUSTED -> {
                                log(if (response == "skip") "已按策略跳过当前商品" else "自动重试次数已用完（${config.busyRetryCount} 次）")
                                runCatching { restoreSearchList(collector, actions, keyword) }
                                afterItem(config, runtime)
                                return false
                            }
                            CollectorRetryDisposition.RETRY -> Unit
                        }
                        retries++
                        val baseCooldown = CollectorErrorPolicy.cooldownMs(e, config.busyCooldownMs, config.riskCooldownMs)
                        val cooldown = (baseCooldown * retries).coerceAtMost(30 * 60 * 1000L)
                        log("第 $retries 次恢复：冷却 ${cooldown / 1000} 秒后重试当前商品")
                        runCatching { actions.reset() }
                        delay(cooldown)
                        searchKeywordCounted(collector, actions, keyword, prefetchPages = 2)
                    }
                }
            }
        }
        return false
    }

    private suspend fun collectOne(
        collector: Collector,
        actions: CollectorSession,
        dbTaskId: Long,
        keyword: String,
        pickTag: String,
        openIndex: Int,
        target: CollectTarget? = null,
        config: CollectConfig,
    ): Boolean {
        return try {
            val collected = collector.collectDetail(
                actions,
                DetailCollectionRequest(keyword, pickTag, openIndex, log),
            )
            if (collected.failureAction != null) {
                recordActionAnomaly(
                    config,
                    dbTaskId,
                    collected.failureAction,
                    collected.failureMessage.orEmpty(),
                    collected.raw.evidence,
                )
                return false
            }
            var product = requireNotNull(collected.product).copy(taskId = dbTaskId)
            val quality = requireNotNull(collected.quality)

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
                        "匹配跳过【$pickTag】准字=${match.actualApproval.ifBlank { "-" }}/${match.expectedApproval} " +
                            "规格=${match.actualSpec.ifBlank { "-" }}/${match.expectedSpec} " +
                            "准字命中=${match.approvalMatched} 规格命中=${match.specMatched}"
                    )
                    restoreSearchList(collector, actions, keyword)
                    return false
                }
                log("匹配命中【$pickTag】准字=${product.approvalNo} 规格=${product.spec} item=${target.remoteItemId ?: "-"}")
            }

            if (!quality.accepted) {
                recordActionAnomaly(
                    config,
                    dbTaskId,
                    "quality_gate",
                    "page=${quality.pageStatus} parse=${quality.parseStatus} quality=${quality.qualityStatus} missing=${quality.missingFields}",
                    collected.raw.evidence,
                )
                log("质量门禁拒绝【$pickTag】：page=${quality.pageStatus} missing=${quality.missingFields}")
                restoreSearchList(collector, actions, keyword)
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
                    log("商品已进入待上报队列 outbox=$outboxId err=${e.message}")
                }
            }
            log(
                "采集并持久化【$pickTag】id=${product.itemId.ifBlank { "-" }} " +
                    "展示价=${product.displayPrice ?: "-"} 单买=${product.dealPrice ?: "-"} " +
                    "准字=${product.approvalNo.ifBlank { "-" }} 厂家=${product.manufacturer.ifBlank { "-" }} " +
                    "图=${if (product.mainImages.isBlank()) 0 else product.mainImages.split("|").size} " +
                    "链=${if (product.itemUrl.isBlank()) "-" else "有"} " +
                    "参数=${if (collected.paramsCaptured) "已开" else "未开"}"
            )
            restoreSearchList(collector, actions, keyword)
            true
        } catch (e: CollectorException) {
            throw e
        } catch (e: Exception) {
            log("本条失败 $pickTag err=${e.message}")
            try { restoreSearchList(collector, actions, keyword) } catch (_: Exception) {}
            false
        }
    }

}
