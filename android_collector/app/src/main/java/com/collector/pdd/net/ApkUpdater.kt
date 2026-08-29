package com.collector.pdd.net

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * 联机一键更新：下载服务端 APK 并拉起系统安装界面。
 */
object ApkUpdater {
    @Volatile
    private var busy = false
    @Volatile private var pendingRemoteVersion: String? = null

    fun isBusy(): Boolean = busy
    fun isRemoteUpdatePending(): Boolean = pendingRemoteVersion != null

    fun handleCommand(
        context: Context,
        prefs: ServerPrefs,
        cmd: JSONObject?,
        log: (String) -> Unit,
    ) {
        val version = cmd?.optString("version_name", "")?.trim().orEmpty()
        if (version.isNotBlank() && pendingRemoteVersion == version) return
        pendingRemoteVersion = version.ifBlank { "unknown" }
        cmd?.optInt("generation", 0)?.takeIf { it > 0 }?.let { prefs.otaGeneration = it }
        startUpdate(context, prefs, cmd, log, source = "远程指令")
    }

    /** 主界面手工点「更新」 */
    fun startManualUpdate(
        context: Context,
        prefs: ServerPrefs,
        cmd: JSONObject?,
        log: (String) -> Unit,
    ) {
        startUpdate(context, prefs, cmd, log, source = "手工更新")
    }

    private fun startUpdate(
        context: Context,
        prefs: ServerPrefs,
        cmd: JSONObject?,
        log: (String) -> Unit,
        source: String,
    ) {
        if (cmd == null) {
            log("$source：无有效更新包信息")
            return
        }
        val urlPath = cmd.optString("apk_url", "").trim()
        if (urlPath.isBlank()) {
            log("$source：缺少 apk_url")
            return
        }
        val ver = cmd.optString("version_name", "").trim()
        if (ver.isNotBlank() && ver == ApiClient.APP_VERSION) {
            log("已是目标版本 $ver，跳过更新")
            return
        }
        if (busy) {
            log("更新进行中，跳过重复请求")
            return
        }
        busy = true
        Thread {
            try {
                log("$source：目标 v${ver.ifBlank { "?" }}，开始下载…")
                val fullUrl = if (urlPath.startsWith("http", true)) {
                    urlPath
                } else {
                    prefs.baseUrl().trimEnd('/') + urlPath
                }
                val dir = File(context.getExternalFilesDir(null), "apk").apply { mkdirs() }
                val apk = File(dir, "update.apk")
                // 去掉查询串再落盘；下载带 ?v= 防花生壳缓存旧包
                val expectSize = cmd.optLong("size", 0L)
                download(fullUrl, apk)
                if (expectSize > 0 && apk.length() != expectSize) {
                    log("警告：下载大小 ${apk.length()} 与服务端期望 $expectSize 不一致，仍继续安装")
                }
                log("APK 已下载 ${apk.length()} bytes，目标 v${ver.ifBlank { "?" }}，准备安装…")
                ensureInstallPermission(context, log)
                launchInstaller(context, apk)
                log("已拉起安装界面，请在系统弹窗中确认安装")
            } catch (e: Exception) {
                log("更新失败: ${e.message}")
            } finally {
                busy = false
            }
        }.start()
    }

    private fun download(url: String, dest: File) {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 30000
            readTimeout = 120000
            instanceFollowRedirects = true
        }
        try {
            if (conn.responseCode !in 200..299) {
                error("下载失败 HTTP ${conn.responseCode}")
            }
            conn.inputStream.use { input ->
                FileOutputStream(dest).use { output ->
                    input.copyTo(output)
                }
            }
        } finally {
            conn.disconnect()
        }
        if (!dest.isFile || dest.length() < 10_000L) error("APK 文件异常")
    }

    private fun ensureInstallPermission(context: Context, log: (String) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        if (context.packageManager.canRequestPackageInstalls()) return
        log("未授权安装未知应用，请允许本应用安装")
        try {
            val i = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                data = Uri.parse("package:${context.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(i)
            Thread.sleep(2500)
        } catch (_: Exception) {
        }
    }

    private fun launchInstaller(context: Context, apk: File) {
        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apk,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(intent)
    }
}
