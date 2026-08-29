package com.collector.pdd.net

import android.content.Context
import android.os.Build
import java.util.UUID

class ServerPrefs(ctx: Context) {
    private val sp = ctx.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var enabled: Boolean
        get() = sp.getBoolean(KEY_ENABLED, false)
        set(v) = sp.edit().putBoolean(KEY_ENABLED, v).apply()

    var host: String
        get() = sp.getString(KEY_HOST, "")?.trim().orEmpty()
        set(v) = sp.edit().putString(KEY_HOST, v.trim()).apply()

    /** 0 表示不拼接端口（适合花生壳已映射 80/443 的域名） */
    var port: Int
        get() = sp.getInt(KEY_PORT, 0)
        set(v) = sp.edit().putInt(KEY_PORT, v).apply()

    var deviceName: String
        get() = sp.getString(KEY_NAME, Build.MODEL)?.trim().orEmpty().ifBlank { Build.MODEL }
        set(v) = sp.edit().putString(KEY_NAME, v.trim()).apply()

    var platformCode: String
        get() = sp.getString(KEY_PLATFORM, "pinduoduo")?.trim().orEmpty().ifBlank { "pinduoduo" }
        set(v) = sp.edit().putString(KEY_PLATFORM, v.trim()).apply()

    var enrollmentToken: String
        get() = sp.getString(KEY_ENROLLMENT_TOKEN, "")?.trim().orEmpty()
        set(v) = sp.edit().putString(KEY_ENROLLMENT_TOKEN, v.trim()).apply()

    var otaGeneration: Int
        get() = sp.getInt(KEY_OTA_GENERATION, 0)
        set(v) = sp.edit().putInt(KEY_OTA_GENERATION, v).apply()

    val deviceKey: String
        get() {
            val existed = sp.getString(KEY_DEVICE, null)
            if (!existed.isNullOrBlank()) return existed
            val gen = "android-" + UUID.randomUUID().toString().replace("-", "").take(16)
            sp.edit().putString(KEY_DEVICE, gen).apply()
            return gen
        }

    /** Durable hand-off between a successful pull and TaskEngine's first Room transaction. */
    fun pendingTaskJson(): String? = sp.getString(KEY_PENDING_TASK, null)?.takeIf { it.isNotBlank() }

    fun savePendingTask(json: String) {
        check(sp.edit().putString(KEY_PENDING_TASK, json).commit()) {
            "failed to persist pulled task assignment"
        }
    }

    /** Stable logical worker identity; changes only when app data is cleared. */
    val workerId: String
        get() {
            val existed = sp.getString(KEY_WORKER, null)
            if (!existed.isNullOrBlank()) return existed
            val generated = "android-worker-" + UUID.randomUUID().toString().replace("-", "")
            check(sp.edit().putString(KEY_WORKER, generated).commit()) { "failed to persist worker identity" }
            return generated
        }

    fun clearPendingTask() {
        check(sp.edit().remove(KEY_PENDING_TASK).commit()) {
            "failed to clear persisted task assignment"
        }
    }

    /**
     * 解析最终 API 根地址。
     * - 主机已带 :端口 → 不再拼 port
     * - port<=0 → 不拼端口（走 80/443）
     * - 花生壳常见：只填域名，端口留空
     */
    fun baseUrl(): String {
        var h = host.trim().trimEnd('/')
        require(h.isNotBlank()) { "服务器地址为空" }
        // 用户误把完整 URL 填进主机时剥离尾部 path
        h = h.removeSuffix("/api").removeSuffix("/api/health")
        if (!h.startsWith("http://") && !h.startsWith("https://")) {
            h = "http://$h"
        }
        // 已含端口（http://x.com:8080）不再追加
        val hasPort = Regex("""^https?://[^/]+:\d+$""").containsMatchIn(h) ||
            Regex("""^https?://[^/]+:\d+/""").containsMatchIn(h)
        if (hasPort || port <= 0) return h.trimEnd('/')
        // https 默认 443 时通常也不该硬拼非标准端口以外的值；仍按用户填写拼接
        return "$h:$port"
    }

    fun wsBase(): String {
        val http = baseUrl()
        return when {
            http.startsWith("https://") -> "wss://" + http.removePrefix("https://")
            http.startsWith("http://") -> "ws://" + http.removePrefix("http://")
            else -> "ws://$http"
        }
    }

    companion object {
        private const val PREFS = "sjzq_server"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val KEY_NAME = "device_name"
        private const val KEY_PLATFORM = "platform"
        private const val KEY_ENROLLMENT_TOKEN = "enrollment_token"
        private const val KEY_DEVICE = "device_key"
        private const val KEY_WORKER = "worker_id"
        private const val KEY_PENDING_TASK = "pending_remote_task_json"
        private const val KEY_OTA_GENERATION = "ota_generation"
    }
}
