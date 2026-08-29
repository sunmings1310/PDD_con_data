package com.collector.pdd.net

import android.content.Context
import android.content.Intent
import android.util.Log
import com.collector.pdd.CollectorApp
import com.collector.pdd.cast.CastPermissionActivity
import com.collector.pdd.cast.ScreenCastService
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.CollectTarget
import com.collector.pdd.data.OutboxEntity
import com.collector.pdd.data.JobAssignmentEntity
import com.collector.pdd.engine.ImageCaptureHelper
import com.collector.pdd.engine.TaskEngine
import com.collector.pdd.service.CollectA11yService
import com.collector.pdd.ui.ConnectionStatus
import com.collector.pdd.ui.VersionStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * 联机模式：心跳 / 拉任务 / 上报 / 响应投屏与远程终止。
 */
class AgentCoordinator(
    private val appContext: Context,
    private val prefs: ServerPrefs,
    private val log: (String) -> Unit,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val api = ApiClient(prefs)
    private val workerId = prefs.workerId
    private var loopJob: Job? = null
    private var durableRecoveryDone = false
    @Volatile private var awaitingJobRecovery = false
    @Volatile private var activeJob: JobLeaseIdentity? = null
    @Volatile private var pauseRequested = false
    private var lastEngineRecoveryAttemptAt = 0L
    private val engine = TaskEngine(
        log = { msg ->
            log(msg)
            val rid = remoteTaskId
            if (rid != null) {
                scope.launch(Dispatchers.IO) {
                    runCatching { api.progress(rid, msg) }
                }
            }
        },
        onProductCollected = { _, outboxId, product, _ ->
            withContext(Dispatchers.IO) {
                // TaskEngine persisted the immutable Job/Attempt/Lease identity with the
                // product event. Never rebind a delayed callback to a newer active Job.
                flushOutbox(outboxId)
                log("商品已持久化待确认 item=${product.itemId} outbox=$outboxId")
            }
        },
        onKeywordSearched = { kw ->
            val rid = remoteTaskId
            if (rid != null) {
                scope.launch(Dispatchers.IO) {
                    runCatching {
                        api.progress(rid, "关键词搜索 $kw", keywordDelta = 1)
                    }
                }
            }
        },
        onTargetFinished = { target, matched, message ->
            val rid = remoteTaskId
            if (rid != null && target.remoteItemId != null) {
                withContext(Dispatchers.IO) {
                    runCatching {
                        api.progress(
                            taskId = rid,
                            message = message,
                            itemId = target.remoteItemId,
                            itemStatus = TaskStatusMapping.itemResult(matched),
                        )
                    }.onFailure {
                        log("明细结果上报失败 item=${target.remoteItemId}: ${it.message}")
                    }
                }
            }
        },
        onActionAnomaly = { localTaskId, actionName, message, pageText, consecutiveCount ->
            val rid = remoteTaskId
            if (rid != null) {
                val screenshot = CollectA11yService.instance?.let { service ->
                    ImageCaptureHelper.screenshotAnomaly(service, localTaskId, actionName, log)
                }
                withContext(Dispatchers.IO) {
                    runCatching {
                        api.uploadTaskAnomaly(rid, actionName, message, pageText, consecutiveCount, screenshot)
                    }.onFailure {
                        log("异常现场上报失败: ${it.message}")
                    }
                }
            }
        },
        onTaskFinished = { localTaskId, status ->
            val rid = remoteTaskId
            if (rid != null) {
                scope.launch(Dispatchers.IO) {
                    if (pauseRequested) {
                        log("Job 收到暂停请求，停止后不提交终态 #$rid")
                        return@launch
                    }
                    val job = activeJob
                    if (job != null) {
                        enqueueJobCheckpoint(job, TaskStatusMapping.completionFor(status))
                        enqueueJobTerminal(job, TaskStatusMapping.completionFor(status))
                        flushOutbox()
                    } else {
                        enqueueFinish(localTaskId, rid, TaskStatusMapping.completionFor(status))
                        flushOutbox()
                    }
                }
            }
        },
    )

    @Volatile var remoteTaskId: Long? = null
        private set

    fun start() {
        if (loopJob?.isActive == true) return
        if (!prefs.enabled) return
        loopJob = scope.launch {
            log("联机模式已开启 ${prefs.baseUrl()}")
            if (!durableRecoveryDone) {
                withContext(Dispatchers.IO) { recoverDurableState() }
                durableRecoveryDone = true
            }
            var lastOkLogAt = 0L
            while (isActive) {
                if (!prefs.enabled || prefs.host.isBlank()) {
                    delay(3000)
                    continue
                }
                try {
                    tick()
                    val now = System.currentTimeMillis()
                    if (now - lastOkLogAt > 30000) {
                        log("心跳正常 ${prefs.baseUrl()}")
                        lastOkLogAt = now
                    }
                } catch (e: Exception) {
                    ConnectionStatus.mark(false, "联机异常：${e.message}")
                    log("联机心跳异常: ${e.message}")
                    Log.w(TAG, "tick", e)
                }
                delay(if (engine.isRunning()) 5000 else 3000)
            }
        }
    }

    fun stop() {
        loopJob?.cancel()
        loopJob = null
        // 仅停联机循环，不强制打断本地手动采集
    }

    fun forceRestart() {
        stop()
        start()
    }

    fun isRunningTask(): Boolean = engine.isRunning()

    fun stopLocalTask() {
        engine.stop()
    }

    private suspend fun tick() = withContext(Dispatchers.IO) {
        flushOutbox()
        val reg = runCatching { api.register() }.getOrNull()
        if (reg != null && reg.has("ok") && !reg.optBoolean("ok")) {
            throw IllegalStateException(reg.optString("message", "register failed"))
        }
        // 仅在任务真正运行时上报 current_task_id，避免终止后心跳把 Web 状态写回「采集中」
        val running = engine.isRunning()
        if (remoteTaskId == null) remoteTaskId = CollectorApp.instance.database.outboxDao().oldestUnacked()?.remoteTaskId
        val status = when {
            ScreenCastService.isRunning && !running -> "busy"
            running || remoteTaskId != null -> "busy"
            else -> "online"
        }
        val tidForHb = remoteTaskId
        val hb = api.heartbeat(status, tidForHb)
        if (!hb.optBoolean("ok", false)) {
            ConnectionStatus.mark(false, "心跳失败：${hb.optString("message")}")
            throw IllegalStateException(hb.optString("message", "heartbeat failed"))
        }
        ConnectionStatus.mark(true, "已连接服务 ${prefs.baseUrl()}")
        if (awaitingJobRecovery && activeJob == null) {
            // Keep the old lease as the only candidate while the server truth is
            // temporarily unavailable; never acquire a replacement job.
            try {
                recoverDurableState()
            } catch (e: Exception) {
                log("Job recovery 重试失败: ${e.message}")
            }
            return@withContext
        }
        val job = activeJob
        if (job != null) {
            try {
                val state = api.heartbeatJob(job)
                val expiresAt = System.currentTimeMillis() + state.optLong("lease_seconds", 120L) * 1000L
                CollectorApp.instance.database.jobAssignmentDao().updateLease(
                    job.jobId, job.attemptId, expiresAt, job.checkpointVersion,
                    state.optString("status", "running"), System.currentTimeMillis(),
                )
                if (state.optBoolean("pause_requested", false)) {
                    pauseJob(job)
                    return@withContext
                }
            } catch (e: JobProtocolException) {
                if (e.errorCode in setOf("STALE_LEASE", "LEASE_EXPIRED", "JOB_NOT_FOUND")) {
                    handleStaleJob(job, e.errorCode)
                } else {
                    throw e
                }
            }
            val now = System.currentTimeMillis()
            val terminalExists = CollectorApp.instance.database.outboxDao()
                .get("job-terminal-${job.jobId}-${job.attemptId}") != null
            if (shouldRetryRecoveredEngine(
                    engineRunning = engine.isRunning(),
                    terminalExists = terminalExists,
                    now = now,
                    lastAttemptAt = lastEngineRecoveryAttemptAt,
                )
            ) {
                lastEngineRecoveryAttemptAt = now
                log("Job 引擎未运行，重试恢复 #${job.jobId}/${job.attemptId}")
                startEngineForJob(job)
            }
        }
        val data = hb.optJSONObject("data")
        // 心跳附带服务端最新包版本，驱动主界面更新条
        VersionStatus.applyServer(data?.optJSONObject("latest_apk"), ApiClient.APP_VERSION)
        val cmds = data?.optJSONObject("commands")
        val castReq = cmds?.optBoolean("cast_request", false) == true
        val abort = cmds?.optBoolean("abort_task", false) == true
        val updateApk = cmds?.optJSONObject("update_apk")

        if (abort) {
            val rid = remoteTaskId
            if (engine.isRunning()) {
                withContext(Dispatchers.Main) {
                    log("收到远程终止指令，停止采集并返回主界面…")
                    engine.stop()
                }
            } else if (rid != null) {
                enqueueFinish(0L, rid, "cancelled", "远程终止")
                flushOutbox()
                log("远程终止：结束确认已进入持久队列 #$rid")
            }
        }
        if (updateApk != null) {
            // 更新优先：先停任务再装包
            if (engine.isRunning()) {
                withContext(Dispatchers.Main) {
                    log("一键更新：先停止当前任务")
                    engine.stop()
                }
            }
            ApkUpdater.handleCommand(appContext, prefs, api, updateApk, log)
        }
        if (castReq && !ScreenCastService.isRunning) {
            withContext(Dispatchers.Main) {
                log("收到投屏请求，准备自动授权…")
                val i = Intent(appContext, CastPermissionActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                appContext.startActivity(i)
            }
        }
        if (!castReq && ScreenCastService.isRunning) {
            // 服务端已停止请求时也可继续推，直到 Web stop；此处不强制停
        }

        if (!engine.isRunning() && activeJob == null) {
            var jobsApiUnavailable = false
            val jobLease = try {
                api.acquireJob(workerId)
            } catch (e: JobProtocolUnavailableException) {
                // Only an older server without /api/jobs permits compatibility pull.
                log("Job API 不存在，使用 legacy task pull: ${e.message}")
                jobsApiUnavailable = true
                null
            } catch (e: Exception) {
                // An available jobs API with a transport/5xx failure must not
                // bypass the lease protocol or accidentally claim a second task.
                log("Job acquire 失败，等待下次恢复: ${e.message}")
                return@withContext
            }
            if (jobLease != null) {
                startJobLease(jobLease)
                return@withContext
            }
            // A successful acquire with no data means there is currently no Job.
            // Do not call legacy pull: the server is the sole scheduler.
            if (!jobsApiUnavailable) return@withContext
            val persistedAssignment = prefs.pendingTaskJson()?.let { raw ->
                runCatching { JSONObject(raw) }.getOrElse {
                    prefs.clearPendingTask()
                    null
                }
            }
            val task = persistedAssignment ?: api.pullTask()
            if (task != null) {
                val tid = task.optLong("task_id")
                val targets = parseTargets(task)
                val keywords = if (targets.isNotEmpty()) {
                    targets.map { it.keyword }
                } else {
                    parseKeywords(task)
                }
                if (tid > 0 && keywords.isNotEmpty()) {
                    if (persistedAssignment == null) {
                        // The durable assignment exists before the in-memory task becomes active.
                        prefs.savePendingTask(task.toString())
                    }
                    remoteTaskId = tid
                    val cfgJson = task.optJSONObject("config")
                    val delayMinSec = when {
                        cfgJson == null -> 2
                        cfgJson.has("delay_min_sec") -> cfgJson.optInt("delay_min_sec", 2)
                        else -> cfgJson.optInt("delay_sec", 2)
                    }.coerceIn(1, 60)
                    val delayMaxSec = when {
                        cfgJson == null -> 5
                        cfgJson.has("delay_max_sec") -> cfgJson.optInt("delay_max_sec", delayMinSec)
                        else -> (cfgJson.optInt("delay_sec", delayMinSec) * 2).coerceAtLeast(delayMinSec)
                    }.coerceIn(delayMinSec, 120)
                    val n = cfgJson?.optInt("max_detail", 5) ?: 5
                    val humanLevel = cfgJson?.optString("human_level", "strict")?.ifBlank { "strict" } ?: "strict"
                    val gestures = cfgJson?.optBoolean("enable_human_gestures", true) != false
                    val minMs = delayMinSec * 1000L
                    val maxMs = delayMaxSec * 1000L
                    val itemGapMinSec = cfgJson?.optInt("item_gap_min_sec", 6)?.coerceIn(1, 180) ?: 6
                    val itemGapMaxSec = cfgJson?.optInt("item_gap_max_sec", 10)
                        ?.coerceIn(itemGapMinSec, 300) ?: 10
                    val batchSize = cfgJson?.optInt("batch_size", 4)?.coerceIn(1, 50) ?: 4
                    val batchCooldownSec = cfgJson?.optInt("batch_cooldown_sec", 25)?.coerceIn(0, 900) ?: 25
                    val busyResponse = cfgJson?.optString("busy_response", "retry")
                        ?.lowercase()?.takeIf { it in setOf("retry", "skip", "stop") } ?: "retry"
                    val busyRetryCount = cfgJson?.optInt("busy_retry_count", 0)?.coerceIn(0, 5) ?: 0
                    val busyCooldownSec = cfgJson?.optInt("busy_cooldown_sec", 15)?.coerceIn(5, 900) ?: 15
                    val riskCooldownSec = cfgJson?.optInt("risk_cooldown_sec", 60)?.coerceIn(10, 1800) ?: 60
                    val soldOutThreshold = cfgJson?.optInt("sold_out_stop_threshold", 2)?.coerceIn(0, 20) ?: 2
                    val anomalyStopThreshold = cfgJson?.optInt("anomaly_stop_threshold", 3)?.coerceIn(0, 20) ?: 3
                    withContext(Dispatchers.Main) {
                        log(
                            "领取远程任务 #$tid 关键词=${keywords.size} " +
                                "匹配目标=${targets.count { it.requiresMatch }} " +
                                "等待=${delayMinSec}~${delayMaxSec}s 商品间隔=${itemGapMinSec}~${itemGapMaxSec}s " +
                                "批次=$batchSize/$batchCooldownSec s 繁忙=$busyResponse 拟人=$humanLevel"
                        )
                        val cfg = CollectConfig(
                            keywords = keywords,
                            targets = targets,
                            maxDetailPerKeyword = n.coerceIn(1, 30),
                            enablePriceSort = cfgJson?.optBoolean("enable_price_sort") == true,
                            enableSalesSort = cfgJson?.optBoolean("enable_sales_sort") == true,
                            remoteTaskId = tid,
                            platformCode = task.optString("platform_code", prefs.platformCode),
                            taskType = task.optString("task_type", "collect"),
                            platformAccountId = cfgJson?.optLong("account_id")?.takeIf { it > 0L },
                            humanLevel = humanLevel,
                            enableHumanGestures = gestures,
                            // 操作等待：完全按 Web 区间随机
                            delayMinMs = minMs,
                            delayMaxMs = maxMs,
                            // 思考/阅读/间隙随区间放大
                            thinkMinMs = (minMs * 0.5).toLong().coerceAtLeast(400),
                            thinkMaxMs = (maxMs * 0.8).toLong().coerceAtLeast(800),
                            readMinMs = (minMs * 0.8).toLong().coerceAtLeast(800),
                            readMaxMs = (maxMs * 1.2).toLong().coerceAtLeast(1500),
                            itemGapMinMs = itemGapMinSec * 1000L,
                            itemGapMaxMs = itemGapMaxSec * 1000L,
                            keywordGapMinMs = (minMs * 1.5).toLong(),
                            keywordGapMaxMs = (maxMs * 2.5).toLong().coerceAtLeast(minMs * 2),
                            batchSize = batchSize,
                            batchCooldownMs = batchCooldownSec * 1000L,
                            busyResponse = busyResponse,
                            busyRetryCount = busyRetryCount,
                            busyCooldownMs = busyCooldownSec * 1000L,
                            riskCooldownMs = riskCooldownSec * 1000L,
                            soldOutStopThreshold = soldOutThreshold,
                            anomalyStopThreshold = anomalyStopThreshold,
                            imageRuleEnabled = cfgJson?.optBoolean("image_rule_enabled", false) == true,
                            imageRuleVersion = cfgJson?.optInt("image_rule_version", 1) ?: 1,
                        )
                        engine.start(scope, cfg)
                    }
                } else if (tid > 0) {
                    if (persistedAssignment == null) prefs.savePendingTask(task.toString())
                    remoteTaskId = tid
                    enqueueFinish(0L, tid, "failed", "invalid task payload: no executable keywords")
                    flushOutbox()
                } else if (persistedAssignment != null) {
                    prefs.clearPendingTask()
                }
            }
        }
    }

    private suspend fun enqueueFinish(localTaskId: Long, remoteId: Long, status: String, error: String? = null) {
        val dao = CollectorApp.instance.database.outboxDao()
        val finishId = "finish-$remoteId-$localTaskId"
        val payload = JSONObject()
            .put("status", status)
            .put("expected_product_count", dao.productEventCount(remoteId))
            .put("expected_image_count", dao.imageEventCount(remoteId))
        if (!error.isNullOrBlank()) payload.put("error_msg", error.take(500))
        val existing = dao.get(finishId)
        if (existing != null) {
            if (shouldRequeueLegacyFinishForCancellation(existing, status)) {
                dao.requeueLegacyFinishForCancellation(
                    finishId,
                    payload.toString(),
                    System.currentTimeMillis(),
                )
            }
            return
        }
        dao.insert(
            OutboxEntity(
                outboxId = finishId,
                eventType = "finish",
                remoteTaskId = remoteId,
                payloadJson = payload.toString(),
            ),
        )
    }

    private suspend fun recoverDurableState() {
        val db = CollectorApp.instance.database
        db.outboxDao().resetInFlight()
        // A local running task is only an observation. Never convert it to failed
        // during process recovery; the server Job/Attempt/Lease is authoritative.
        val localAssignments = db.jobAssignmentDao().active()
        val serverAssignments = runCatching { api.recoverJobs(workerId) }.getOrElse {
            log("Job recover 暂不可用，保留本地 lease 证据: ${it.message}")
            emptyList()
        }
        var unresolvedLease = false
        for (assignment in localAssignments) {
            val remote = serverAssignments.firstOrNull {
                it.optLong("job_id") == assignment.jobId &&
                    it.optLong("active_attempt_id") == assignment.attemptId
            }
            if (remote == null) {
                // Recover can race lease materialization. Validate the persisted
                // token directly before deciding that the lease disappeared.
                val localIdentity = assignment.toJobLeaseIdentity()
                try {
                    val heartbeat = api.heartbeatJob(localIdentity)
                    val refreshed = localIdentity.copy(
                        checkpointVersion = heartbeat.optInt("checkpoint_version", localIdentity.checkpointVersion),
                        leaseExpiresAt = System.currentTimeMillis() + heartbeat.optLong("lease_seconds", 120L) * 1000L,
                    )
                    activeJob = refreshed
                    db.jobAssignmentDao().updateLease(
                        assignment.jobId,
                        assignment.attemptId,
                        refreshed.leaseExpiresAt,
                        refreshed.checkpointVersion,
                        "running",
                        System.currentTimeMillis(),
                    )
                    if (!engine.isRunning()) startEngineForJob(refreshed)
                } catch (e: JobProtocolException) {
                    if (e.errorCode in setOf("STALE_LEASE", "LEASE_EXPIRED", "JOB_NOT_FOUND")) {
                        handleStaleJob(localIdentity, e.errorCode)
                    } else {
                        unresolvedLease = true
                        log("未从服务端恢复 job=${assignment.jobId} attempt=${assignment.attemptId}，保留等待状态")
                    }
                } catch (e: Exception) {
                    unresolvedLease = true
                    log("未从服务端恢复 job=${assignment.jobId} attempt=${assignment.attemptId}，保留等待状态")
                }
                continue
            }
            val identity = assignment.toJobLeaseIdentity()
                .copy(checkpointVersion = remote.optInt("checkpoint_version", assignment.checkpointVersion))
            remote.optJSONObject("checkpoint")?.let { identity.payload.put("_checkpoint", it) }
            activeJob = identity
            remoteTaskId = assignment.taskId
            db.jobAssignmentDao().updateLease(
                assignment.jobId,
                assignment.attemptId,
                System.currentTimeMillis() + 120_000L,
                identity.checkpointVersion,
                assignment.state,
                System.currentTimeMillis(),
            )
            var canStart = assignment.state == "running"
            if (assignment.state == "leased") {
                runCatching { api.startJob(identity) }
                    .onSuccess {
                        canStart = true
                        db.jobAssignmentDao().setState(
                            assignment.jobId,
                            assignment.attemptId,
                            "running",
                            System.currentTimeMillis(),
                        )
                    }
                    .onFailure { log("恢复 leased Job start 待重试: ${it.message}") }
            }
            // The server lease remains the source of truth; resume the collector
            // only after the identity has been recovered and persisted locally.
            if (canStart && !engine.isRunning()) startEngineForJob(identity)
        }
        if (activeJob == null) {
            if (unresolvedLease) {
                // Never classify local outbox rows as stale merely because the
                // recovery request timed out or returned no rows.
                awaitingJobRecovery = true
                return
            }
            remoteTaskId = db.outboxDao().oldestUnacked()?.remoteTaskId
        }
        awaitingJobRecovery = false
        flushOutbox()
    }

    private suspend fun flushOutbox(onlyId: String? = null) {
        val db = CollectorApp.instance.database
        val dao = db.outboxDao()
        val events = if (onlyId != null) listOfNotNull(dao.get(onlyId)) else dao.ready(System.currentTimeMillis())
        for (event in events) {
            val eventJobId = event.jobId
            val eventAttemptId = event.attemptId
            if (eventJobId != null && eventAttemptId != null) {
                val current = activeJob
                if (current == null || current.jobId != eventJobId || current.attemptId != eventAttemptId || current.leaseToken != event.leaseToken) {
                    dao.rejectStaleLease(eventJobId, eventAttemptId, "no longer current lease")
                    continue
                }
            }
            if (event.state == "acked" || dao.markInFlight(event.outboxId) == 0) continue
            try {
                when (event.eventType) {
                    "product" -> {
                        val productId = api.uploadProductEvent(event)
                        dao.markAcked(event.outboxId, productId, System.currentTimeMillis())
                        runCatching { api.progress(event.remoteTaskId, "服务端已确认商品 product_id=$productId") }
                        activeJob?.takeIf { it.jobId == event.jobId && it.attemptId == event.attemptId }?.let { identity ->
                            flushOutbox(enqueueJobCheckpoint(identity, "running"))
                        }
                    }
                    "finish" -> {
                        if (dao.unackedProducts(event.remoteTaskId).isNotEmpty()) {
                            error("product acknowledgements pending")
                        }
                        val rejected = dao.rejectedProductCount(event.remoteTaskId)
                        val status = api.finishEvent(event, if (rejected > 0) "failed" else null)
                        dao.markAcked(event.outboxId, null, System.currentTimeMillis())
                        CollectorApp.instance.database.taskDao().clearRemoteTask(event.remoteTaskId)
                        prefs.clearPendingTask()
                        if (remoteTaskId == event.remoteTaskId) remoteTaskId = null
                        log("服务端已确认任务结束 #${event.remoteTaskId} status=$status")
                    }
                    "job_complete" -> {
                        val identity = activeJob ?: error("job assignment not recovered")
                        val attemptEvents = dao.listForAttempt(identity.jobId, identity.attemptId)
                        val products = confirmedJobProducts(
                            identity.payload.optJSONObject("_checkpoint"),
                            dao.listProductsForJob(identity.jobId),
                        )
                        if (products.any { it.state !in setOf("acked", "rejected") }) {
                            error("job product acknowledgements pending")
                        }
                        if (attemptEvents.any { it.eventType == "job_checkpoint" && it.state != "acked" }) {
                            error("job checkpoint acknowledgement pending")
                        }
                        val rejected = products.filter { it.state == "rejected" }
                        val receipts = products.filter { it.state == "acked" }
                        when (jobTerminalAction(receipts.size, rejected.size)) {
                            JobTerminalAction.FAIL_REJECTED ->
                                api.failJob(identity, "data_quality", "PRODUCT_REJECTED", "rejected_products=${rejected.size}")
                            JobTerminalAction.FAIL_NO_RESULT ->
                                api.failJob(identity, "business_rejection", "NO_CONFIRMED_RESULT", "collector produced no confirmed product")
                            JobTerminalAction.COMPLETE ->
                                api.completeJob(identity, receipts.map { it.outboxId })
                        }
                        dao.markAcked(event.outboxId, null, System.currentTimeMillis())
                        db.jobAssignmentDao().delete(identity.jobId, identity.attemptId)
                        if (activeJob?.attemptId == identity.attemptId) activeJob = null
                        if (remoteTaskId == identity.taskId) remoteTaskId = null
                        log("服务端已确认 Job 完成 #${identity.jobId}")
                    }
                    "job_checkpoint" -> {
                        val identity = activeJob ?: error("job assignment not recovered")
                        val payload = JSONObject(event.payloadJson)
                        val version = payload.optInt("version", identity.checkpointVersion + 1)
                        val key = payload.optString("idempotency_key").ifBlank { event.outboxId }
                        val checkpointPayload = payload.optJSONObject("payload") ?: JSONObject()
                        api.checkpointJob(identity, version, key, checkpointPayload)
                        dao.markAcked(event.outboxId, null, System.currentTimeMillis())
                        identity.payload.put("_checkpoint", checkpointPayload)
                        val updated = identity.copy(checkpointVersion = version)
                        activeJob = updated
                        db.jobAssignmentDao().updateLease(
                            identity.jobId,
                            identity.attemptId,
                            identity.leaseExpiresAt,
                            version,
                            "running",
                            System.currentTimeMillis(),
                        )
                    }
                    "job_fail" -> {
                        val identity = activeJob ?: error("job assignment not recovered")
                        val localStatus = JSONObject(event.payloadJson).optString("local_status", "failed")
                        val (errorClass, errorCode) = TaskStatusMapping.jobFailureFor(localStatus)
                        api.failJob(identity, errorClass, errorCode, "local_status=$localStatus")
                        dao.markAcked(event.outboxId, null, System.currentTimeMillis())
                        db.jobAssignmentDao().delete(identity.jobId, identity.attemptId)
                        if (activeJob?.attemptId == identity.attemptId) activeJob = null
                        if (remoteTaskId == identity.taskId) remoteTaskId = null
                        log("服务端已确认 Job 失败 #${identity.jobId}")
                    }
                    else -> error("unknown outbox event ${event.eventType}")
                }
            } catch (e: PermanentUploadException) {
                if (event.eventType == "product") {
                    dao.markRejected(event.outboxId, e.message.orEmpty().take(500))
                    CollectorApp.instance.database.taskDao().markRemoteFailed(event.remoteTaskId)
                    log("上报永久拒绝，任务将以失败结束 outbox=${event.outboxId}: ${e.message}")
                } else {
                    dao.markRetry(event.outboxId, Long.MAX_VALUE, e.message.orEmpty().take(500))
                    log("结束确认发生协议冲突 outbox=${event.outboxId}: ${e.message}")
                }
            } catch (e: JobProtocolException) {
                if (e.errorCode in setOf("STALE_LEASE", "LEASE_EXPIRED", "JOB_NOT_FOUND")) {
                    event.jobId?.let { jobId ->
                        event.attemptId?.let { attemptId -> dao.rejectStaleLease(jobId, attemptId, e.errorCode) }
                    }
                    activeJob?.let { handleStaleJob(it, e.errorCode) }
                } else {
                    val next = System.currentTimeMillis() + OutboxRetryPolicy.delayMillis(event.attemptCount)
                    dao.markRetry(event.outboxId, next, e.message.orEmpty().take(500))
                }
            } catch (e: Exception) {
                val next = System.currentTimeMillis() + OutboxRetryPolicy.delayMillis(event.attemptCount)
                dao.markRetry(event.outboxId, next, e.message.orEmpty().take(500))
                log("上报待重试 outbox=${event.outboxId}: ${e.message}")
            }
        }
    }

    /**
     * Persist the server assignment before starting UI work. A process death between
     * acquire and start therefore leaves a recoverable leased attempt, not a phantom
     * legacy task.
     */
    private suspend fun startJobLease(identity: JobLeaseIdentity) {
        val db = CollectorApp.instance.database
        db.jobAssignmentDao().upsert(
            JobAssignmentEntity(
                jobId = identity.jobId,
                taskId = identity.taskId,
                jobKey = identity.jobKey,
                jobType = identity.jobType,
                payloadJson = identity.payload.toString(),
                attemptId = identity.attemptId,
                attemptNo = identity.attemptNo,
                leaseToken = identity.leaseToken,
                workerId = identity.workerId,
                traceId = identity.traceId,
                checkpointVersion = identity.checkpointVersion,
                leaseExpiresAt = identity.leaseExpiresAt.takeIf { it > System.currentTimeMillis() }
                    ?: (System.currentTimeMillis() + 120_000L),
                state = "leased",
            ),
        )
        val started = try {
            api.startJob(identity)
        } catch (e: JobProtocolException) {
            if (e.errorCode == "STALE_LEASE" || e.errorCode == "LEASE_EXPIRED") {
                handleStaleJob(identity, e.errorCode)
                return
            }
            if (e.errorCode == "JOB_PAUSED") {
                api.yieldJob(identity)
                db.jobAssignmentDao().setState(identity.jobId, identity.attemptId, "paused", System.currentTimeMillis())
                log("Job 在启动前已暂停并释放 lease #${identity.jobId}")
                return
            }
            throw e
        }
        val running = identity.copy(checkpointVersion = started.optInt("checkpoint_version", identity.checkpointVersion))
        pauseRequested = false
        activeJob = running
        remoteTaskId = identity.taskId
        db.jobAssignmentDao().setState(identity.jobId, identity.attemptId, "running", System.currentTimeMillis())
        startEngineForJob(running)
    }

    private suspend fun startEngineForJob(identity: JobLeaseIdentity) {
        val task = normalizeJobPayload(identity.payload)
            .put("task_id", identity.taskId)
            .put("job_id", identity.jobId)
            .put("attempt_id", identity.attemptId)
        val configPayload = task.optJSONObject("config") ?: task.optJSONObject("collect_config")
        val source = configPayload ?: task
        val targets = parseTargets(task)
        val keywords = if (targets.isNotEmpty()) targets.map { it.keyword } else parseKeywords(task)
        if (keywords.isEmpty()) {
            api.failJob(identity, "permanent", "INVALID_JOB_PAYLOAD", "Job payload has no executable keywords")
            handleStaleJob(identity, "INVALID_JOB_PAYLOAD")
            return
        }
        val n = source.optInt("max_detail", 5).coerceIn(1, 30)
        val confirmedSlots = linkedSetOf<String>()
        identity.payload.optJSONObject("_checkpoint")?.optJSONArray("confirmed_slots")?.let { slots ->
            for (i in 0 until slots.length()) {
                slots.optString(i).takeIf { it.isNotBlank() }?.let(confirmedSlots::add)
            }
        }
        CollectorApp.instance.database.outboxDao().listForAttempt(identity.jobId, identity.attemptId)
            .filter { it.eventType == "product" && it.state == "acked" }
            .forEach { event ->
                val product = runCatching { JSONObject(event.payloadJson) }.getOrNull()
                val keyword = product?.optString("keyword").orEmpty()
                val pickTag = product?.optString("pick_tag").orEmpty()
                if (keyword.isNotBlank() && pickTag.isNotBlank()) confirmedSlots += "$keyword|$pickTag"
            }
        val cfg = CollectConfig(
            keywords = keywords,
            targets = targets,
            maxDetailPerKeyword = n,
            enablePriceSort = source.optBoolean("enable_price_sort", false),
            enableSalesSort = source.optBoolean("enable_sales_sort", false),
            remoteTaskId = identity.taskId,
            remoteJobId = identity.jobId,
            attemptId = identity.attemptId,
            leaseToken = identity.leaseToken,
            workerId = identity.workerId,
            traceId = identity.traceId,
            checkpointVersion = identity.checkpointVersion,
            confirmedSlots = confirmedSlots,
            platformCode = source.optString("platform_code", prefs.platformCode),
            taskType = source.optString("task_type", "collect"),
            humanLevel = source.optString("human_level", "strict").ifBlank { "strict" },
        )
        if (checkpointCoversCollectWork(cfg)) {
            log("Checkpoint 已覆盖全部采集槽位，直接提交 Job 完成 #${identity.jobId}")
            enqueueJobCheckpoint(identity, TaskStatusMapping.COMPLETE)
            enqueueJobTerminal(identity, TaskStatusMapping.COMPLETE)
            flushOutbox()
            return
        }
        withContext(Dispatchers.Main) { engine.start(scope, cfg) }
    }

    /** Accept both the structured job payload and the current flat materializer payload. */
    private fun normalizeJobPayload(payload: JSONObject): JSONObject {
        val task = JSONObject(payload.toString())
        if (task.optJSONArray("items") == null && task.optString("keyword").trim().isNotEmpty()) {
            val item = JSONObject(task.toString())
                .put("task_item_id", task.optLong("task_item_id", 0L))
                .put("item_id", task.optLong("task_item_id", task.optLong("item_id", 0L)))
            task.put("items", JSONArray().put(item))
        }
        if (task.optJSONArray("keywords") == null && task.optString("keyword").trim().isNotEmpty()) {
            task.put("keywords", JSONArray().put(task.optString("keyword").trim()))
        }
        return task
    }

    private suspend fun enqueueJobTerminal(identity: JobLeaseIdentity, localStatus: String) {
        val dao = CollectorApp.instance.database.outboxDao()
        val id = "job-terminal-${identity.jobId}-${identity.attemptId}"
        if (dao.get(id) != null) return
        val eventType = if (localStatus == "complete") "job_complete" else "job_fail"
        val payload = JSONObject().put("local_status", localStatus)
        dao.insert(
            OutboxEntity(
                outboxId = id,
                eventType = eventType,
                remoteTaskId = identity.taskId,
                payloadJson = payload.toString(),
                jobId = identity.jobId,
                attemptId = identity.attemptId,
                leaseToken = identity.leaseToken,
                workerId = identity.workerId,
                traceId = identity.traceId,
                checkpointVersion = identity.checkpointVersion,
            ),
        )
    }

    private suspend fun enqueueJobCheckpoint(identity: JobLeaseIdentity, localStatus: String): String {
        val version = identity.checkpointVersion + 1
        val id = "job-checkpoint-${identity.jobId}-${identity.attemptId}-$version"
        val dao = CollectorApp.instance.database.outboxDao()
        val confirmed = linkedSetOf<String>()
        identity.payload.optJSONObject("_checkpoint")?.optJSONArray("confirmed_slots")?.let { slots ->
            for (i in 0 until slots.length()) {
                slots.optString(i).takeIf { it.isNotBlank() }?.let(confirmed::add)
            }
        }
        dao.listForAttempt(identity.jobId, identity.attemptId)
            .filter { it.eventType == "product" && it.state == "acked" }
            .forEach { event ->
                val product = runCatching { JSONObject(event.payloadJson) }.getOrNull()
                val keyword = product?.optString("keyword").orEmpty()
                val pickTag = product?.optString("pick_tag").orEmpty()
                if (keyword.isNotBlank() && pickTag.isNotBlank()) confirmed += "$keyword|$pickTag"
            }
        val checkpoint = JSONObject()
            .put("local_status", localStatus)
            .put("confirmed_slots", JSONArray(confirmed.toList()))
        val payload = JSONObject()
            .put("version", version)
            .put("idempotency_key", id)
            .put("payload", checkpoint)
        if (dao.get(id) != null) {
            dao.updatePendingCheckpoint(id, payload.toString())
            return id
        }
        dao.insert(
            OutboxEntity(
                outboxId = id,
                eventType = "job_checkpoint",
                remoteTaskId = identity.taskId,
                payloadJson = payload.toString(),
                jobId = identity.jobId,
                attemptId = identity.attemptId,
                leaseToken = identity.leaseToken,
                workerId = identity.workerId,
                traceId = identity.traceId,
                checkpointVersion = identity.checkpointVersion,
            ),
        )
        return id
    }

    private suspend fun handleStaleJob(identity: JobLeaseIdentity, reason: String) {
        // Suppress the cancelled engine's asynchronous onTaskFinished callback.
        // startJobLease resets this guard only after a new authoritative start.
        pauseRequested = true
        withContext(Dispatchers.Main) {
            if (engine.isRunning()) engine.stop()
        }
        CollectorApp.instance.database.outboxDao().rejectStaleLease(identity.jobId, identity.attemptId, reason)
        CollectorApp.instance.database.jobAssignmentDao().setState(identity.jobId, identity.attemptId, "stale", System.currentTimeMillis())
        if (activeJob?.attemptId == identity.attemptId) activeJob = null
        if (remoteTaskId == identity.taskId) remoteTaskId = null
        log("Job lease 已失效 job=${identity.jobId} attempt=${identity.attemptId} reason=$reason；旧事件停止投递")
    }

    /** Pause is a server-owned state, not a failed attempt. Yield only after local safe stop. */
    private suspend fun pauseJob(identity: JobLeaseIdentity) {
        pauseRequested = true
        withContext(Dispatchers.Main) {
            if (engine.isRunning()) engine.stop()
        }
        // Persist the safe-stop boundary before releasing execution ownership.
        enqueueJobCheckpoint(identity, "paused")
        flushOutbox()
        val pendingReceipts = CollectorApp.instance.database.outboxDao()
            .listForAttempt(identity.jobId, identity.attemptId)
            .any {
                it.eventType in setOf("product", "job_checkpoint") &&
                    it.state !in setOf("acked", "rejected")
            }
        if (pendingReceipts) {
            log("Job 暂停等待商品回执确认，暂不释放 lease #${identity.jobId}")
            return
        }
        val yielded = api.yieldJob(identity)
        val checkpointVersion = yielded.optInt("checkpoint_version", identity.checkpointVersion)
        CollectorApp.instance.database.jobAssignmentDao().updateLease(
            identity.jobId,
            identity.attemptId,
            System.currentTimeMillis(),
            checkpointVersion,
            "paused",
            System.currentTimeMillis(),
        )
        if (activeJob?.attemptId == identity.attemptId) activeJob = null
        if (remoteTaskId == identity.taskId) remoteTaskId = null
        pauseRequested = false
        log("服务端已确认 Job 暂停并释放 lease #${identity.jobId}")
    }

    private fun parseKeywords(task: JSONObject): List<String> {
        val arr = task.optJSONArray("keywords")
        if (arr != null && arr.length() > 0) {
            return buildList {
                for (i in 0 until arr.length()) {
                    val s = arr.optString(i).trim()
                    if (s.isNotEmpty()) add(s)
                }
            }
        }
        val items = task.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val kw = items.optJSONObject(i)?.optString("keyword")?.trim().orEmpty()
                if (kw.isNotEmpty()) add(kw)
            }
        }
    }

    private fun parseTargets(task: JSONObject): List<CollectTarget> {
        val items = task.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until items.length()) {
                val item = items.optJSONObject(i) ?: continue
                val keyword = item.optString("keyword").trim()
                if (keyword.isEmpty()) continue
                val approval = optionalJsonText(item, "target_approval")
                val name = optionalJsonText(item, "target_name")
                val spec = optionalJsonText(item, "target_spec")
                val manufacturer = optionalJsonText(item, "target_manufacturer")
                val itemId = item.optLong("item_id", item.optLong("task_item_id")).takeIf { it > 0L }
                add(
                    CollectTarget(
                        keyword = keyword,
                        targetApproval = approval,
                        targetName = name,
                        targetSpec = spec,
                        targetManufacturer = manufacturer,
                        remoteItemId = itemId,
                    )
                )
            }
        }
    }

    companion object {
        private const val TAG = "AgentCoordinator"

        @Volatile
        var instance: AgentCoordinator? = null
            private set

        fun ensure(app: CollectorApp, log: (String) -> Unit): AgentCoordinator {
            val prefs = ServerPrefs(app)
            val cur = instance
            if (cur != null) {
                return cur
            }
            val c = AgentCoordinator(app, prefs, log)
            instance = c
            return c
        }
    }
}

internal fun shouldRequeueLegacyFinishForCancellation(event: OutboxEntity, status: String): Boolean =
    status == "cancelled" && event.eventType == "finish" && event.jobId == null && event.state != "acked"

internal fun optionalJsonText(source: JSONObject, key: String): String {
    if (!source.has(key) || source.isNull(key)) return ""
    return source.optString(key, "").trim().takeUnless { it.equals("null", ignoreCase = true) }.orEmpty()
}

/** Select the server-confirmed Job receipts across attempts using the durable checkpoint slots. */
internal fun confirmedJobProducts(
    checkpoint: JSONObject?,
    jobProducts: List<OutboxEntity>,
): List<OutboxEntity> {
    val slots = buildSet {
        checkpoint?.optJSONArray("confirmed_slots")?.let { values ->
            for (index in 0 until values.length()) {
                values.optString(index).takeIf { it.isNotBlank() }?.let(::add)
            }
        }
    }
    if (slots.isEmpty()) return emptyList()
    return jobProducts.filter { event ->
        val product = runCatching { JSONObject(event.payloadJson) }.getOrNull() ?: return@filter false
        val keyword = product.optString("keyword")
        val pickTag = product.optString("pick_tag")
        keyword.isNotBlank() && pickTag.isNotBlank() && "$keyword|$pickTag" in slots
    }
}

internal fun shouldRetryRecoveredEngine(
    engineRunning: Boolean,
    terminalExists: Boolean,
    now: Long,
    lastAttemptAt: Long,
): Boolean = !engineRunning && !terminalExists && now - lastAttemptAt >= 15_000L

/** Ordinary collection can finish without reopening PDD when every required slot is ACKed. */
internal fun checkpointCoversCollectWork(config: CollectConfig): Boolean {
    if (config.taskType != "collect" || config.confirmedSlots.isEmpty()) return false
    if (config.targets.any { it.requiresMatch }) return false
    val keywords = config.targets.takeIf { it.isNotEmpty() }?.map { it.keyword } ?: config.keywords
    return keywords.all { keyword ->
        val required = buildSet {
            for (index in 1..config.maxDetailPerKeyword.coerceAtLeast(1)) {
                add("$keyword|default_top_$index")
            }
            if (config.enablePriceSort) add("$keyword|price_asc_first")
            if (config.enableSalesSort) add("$keyword|sales_desc_first")
        }
        config.confirmedSlots.containsAll(required)
    }
}

private fun JobAssignmentEntity.toJobLeaseIdentity(): JobLeaseIdentity = JobLeaseIdentity(
    taskId = taskId,
    jobId = jobId,
    jobKey = jobKey,
    jobType = jobType,
    payload = JSONObject(payloadJson),
    attemptId = attemptId,
    attemptNo = attemptNo,
    leaseToken = leaseToken,
    workerId = workerId,
    traceId = traceId,
    checkpointVersion = checkpointVersion,
    leaseExpiresAt = leaseExpiresAt,
)
