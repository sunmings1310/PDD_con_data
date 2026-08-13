package com.collector.pdd.ui

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * 本机版本 vs 服务端最新包，供主界面顶部更新条使用。
 */
object VersionStatus {
    data class State(
        val localVersion: String = "",
        val serverVersion: String = "",
        val serverCode: Int = 0,
        val apkUrl: String = "",
        val hasApk: Boolean = false,
        val outdated: Boolean = false,
        val message: String = "",
        val checkedAt: Long = 0L,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    fun applyLocal(localVersion: String) {
        val cur = _state.value
        _state.value = cur.copy(
            localVersion = localVersion,
            outdated = isOutdated(localVersion, cur.serverVersion, cur.serverCode),
            message = buildMsg(localVersion, cur.serverVersion, cur.hasApk, cur.outdated),
        )
    }

    fun applyServer(payload: JSONObject?, localVersion: String) {
        if (payload == null) {
            _state.value = State(
                localVersion = localVersion,
                message = "本机 v$localVersion（未获取到服务端版本）",
                checkedAt = System.currentTimeMillis(),
            )
            return
        }
        val ver = payload.optString("version_name", "").trim()
        val code = payload.optInt("version_code", 0)
        val url = payload.optString("apk_url", "").trim()
        val has = payload.optBoolean("has_apk", url.isNotBlank())
        val outdated = has && isOutdated(localVersion, ver, code)
        _state.value = State(
            localVersion = localVersion,
            serverVersion = ver,
            serverCode = code,
            apkUrl = url,
            hasApk = has,
            outdated = outdated,
            message = buildMsg(localVersion, ver, has, outdated),
            checkedAt = System.currentTimeMillis(),
        )
    }

    fun latestPayloadJson(): JSONObject? {
        val s = _state.value
        if (!s.hasApk || s.apkUrl.isBlank()) return null
        return JSONObject()
            .put("apk_url", s.apkUrl)
            .put("version_name", s.serverVersion)
            .put("version_code", s.serverCode)
    }

    private fun isOutdated(local: String, server: String, serverCode: Int): Boolean {
        if (server.isBlank() && serverCode <= 0) return false
        if (server.isNotBlank() && server != local) return true
        // 仅有 version_code 时：本地无法读 code，有名称不一致才提示；名称相同则不算过期
        return false
    }

    private fun buildMsg(local: String, server: String, hasApk: Boolean, outdated: Boolean): String {
        return when {
            !hasApk && server.isBlank() -> "本机 v$local · 服务端暂无安装包"
            outdated -> "本机 v$local · 服务端 v$server（不一致，请更新）"
            server.isNotBlank() -> "本机 v$local · 服务端 v$server（已同步）"
            else -> "本机 v$local"
        }
    }
}
