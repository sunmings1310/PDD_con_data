package com.collector.pdd.net

import android.content.Context
import android.content.Intent
import android.util.Log
import com.collector.pdd.CollectorApp
import com.collector.pdd.cast.CastPermissionActivity
import com.collector.pdd.cast.ScreenCastService
import com.collector.pdd.data.CollectConfig
import com.collector.pdd.data.CollectTarget
import com.collector.pdd.data.ProductEntity
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
    private var loopJob: Job? = null
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
        onProductCollected = { _, product, taskItemId ->
            val rid = remoteTaskId
            withContext(Dispatchers.IO) {
                runCatching {
                    val productId = api.uploadProduct(rid, product, taskItemId)
                        ?: error("商品上报未返回 product_id")
                    if (rid != null) {
                        // 成功数由 /api/products/upload 的数据库事务累加，避免 APP 再加一次。
                        api.progress(rid, "上报商品 ${product.itemId} product_id=$productId")
                    }
                }.onFailure {
                    log("上报失败: ${it.message}")
                }
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
        onTaskFinished = { _, status ->
            val rid = remoteTaskId
            remoteTaskId = null
            if (rid != null) {
                scope.launch(Dispatchers.IO) {
                    runCatching {
                        val st = TaskStatusMapping.completionFor(status)
                        api.finish(rid, st)
                        log("已上报任务结束 #$rid status=$st")
                    }.onFailure {
                        log("上报任务结束失败: ${it.message}")
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
        val reg = runCatching { api.register() }.getOrNull()
        if (reg != null && reg.has("ok") && !reg.optBoolean("ok")) {
            throw IllegalStateException(reg.optString("message", "register failed"))
        }
        // 仅在任务真正运行时上报 current_task_id，避免终止后心跳把 Web 状态写回「采集中」
        val running = engine.isRunning()
        val status = when {
            ScreenCastService.isRunning && !running -> "busy"
            running -> "busy"
            else -> "online"
        }
        val tidForHb = if (running) remoteTaskId else null
        if (!running && remoteTaskId != null) {
            val orphan = remoteTaskId
            // 本地 idle 不能决定服务端业务终态；停止主动覆盖，等待后续恢复协议。
            log("检测到本地空闲但远程任务仍存在 #$orphan，未覆盖服务端状态")
            remoteTaskId = null
        }
        val hb = api.heartbeat(status, tidForHb)
        if (!hb.optBoolean("ok", false)) {
            ConnectionStatus.mark(false, "心跳失败：${hb.optString("message")}")
            throw IllegalStateException(hb.optString("message", "heartbeat failed"))
        }
        ConnectionStatus.mark(true, "已连接服务 ${prefs.baseUrl()}")
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
                remoteTaskId = null
                runCatching { api.finish(rid, "cancelled", "远程终止") }
                log("远程终止：本地无运行任务，已清理 #$rid")
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

        if (!engine.isRunning() && remoteTaskId == null) {
            val task = api.pullTask()
            if (task != null) {
                val tid = task.optLong("task_id")
                val targets = parseTargets(task)
                val keywords = if (targets.isNotEmpty()) {
                    targets.map { it.keyword }
                } else {
                    parseKeywords(task)
                }
                if (tid > 0 && keywords.isNotEmpty()) {
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
                }
            }
        }
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
                val approval = item.optString("target_approval").trim()
                val name = item.optString("target_name").trim()
                val spec = item.optString("target_spec").trim()
                val manufacturer = item.optString("target_manufacturer").trim()
                val itemId = item.optLong("item_id").takeIf { it > 0L }
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
