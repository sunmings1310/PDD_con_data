package com.collector.pdd.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.collector.pdd.CollectorApp
import com.collector.pdd.R
import com.collector.pdd.net.AgentCoordinator
import com.collector.pdd.net.ApiClient
import com.collector.pdd.net.ApkUpdater
import com.collector.pdd.net.ServerPrefs
import com.collector.pdd.service.CollectA11yService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalTime
import java.time.format.DateTimeFormatter

class MainActivity : AppCompatActivity() {

    private lateinit var tvA11y: TextView
    private lateinit var tvLog: TextView
    private lateinit var tvDeviceKey: TextView
    private lateinit var tvConnStatus: TextView
    private lateinit var tvTaskHint: TextView
    private lateinit var tvVersionInfo: TextView
    private lateinit var tvUpdateHint: TextView
    private lateinit var layoutUpdateBanner: LinearLayout
    private lateinit var btnUpdateNow: Button
    private lateinit var btnSyncVersion: Button
    private lateinit var prefs: ServerPrefs
    private var agent: AgentCoordinator? = null

    private val logs = mutableListOf<String>()
    private val tsFmt = DateTimeFormatter.ofPattern("HH:mm:ss")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = ServerPrefs(this)

        tvA11y = findViewById(R.id.tvA11y)
        tvLog = findViewById(R.id.tvLog)
        tvDeviceKey = findViewById(R.id.tvDeviceKey)
        tvConnStatus = findViewById(R.id.tvConnStatus)
        tvTaskHint = findViewById(R.id.tvTaskHint)
        tvVersionInfo = findViewById(R.id.tvVersionInfo)
        tvUpdateHint = findViewById(R.id.tvUpdateHint)
        layoutUpdateBanner = findViewById(R.id.layoutUpdateBanner)
        btnUpdateNow = findViewById(R.id.btnUpdateNow)
        btnSyncVersion = findViewById(R.id.btnSyncVersion)
        tvLog.movementMethod = ScrollingMovementMethod()
        tvDeviceKey.text = "设备Key：${prefs.deviceKey}"
        VersionStatus.applyLocal(ApiClient.APP_VERSION)
        applyVersionUi(VersionStatus.state.value)

        findViewById<Button>(R.id.btnSettings).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        findViewById<Button>(R.id.btnA11y).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        findViewById<Button>(R.id.btnBattery).setOnClickListener {
            try {
                startActivity(
                    Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                        data = Uri.parse("package:$packageName")
                    }
                )
            } catch (_: Exception) {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            }
        }
        findViewById<Button>(R.id.btnStop).setOnClickListener {
            agent?.stopLocalTask()
            appendLog("已请求停止当前任务")
        }
        btnSyncVersion.setOnClickListener { syncVersionManual() }
        btnUpdateNow.setOnClickListener { startManualUpdate() }

        lifecycleScope.launch {
            CollectA11yService.connected.collectLatest { refreshA11y() }
        }
        lifecycleScope.launch {
            ConnectionStatus.state.collectLatest { applyConnUi(it) }
        }
        lifecycleScope.launch {
            VersionStatus.state.collectLatest { applyVersionUi(it) }
        }
        refreshA11y()
        ensureGalleryPermission()
        if (Build.VERSION.SDK_INT >= 33) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                1003,
            )
        }

        agent = AgentCoordinator.ensure(CollectorApp.instance) { msg ->
            appendLog(msg)
            if (msg.contains("心跳正常") || msg.contains("设备已注册") || msg.contains("领取远程任务")) {
                ConnectionStatus.mark(true, "已连接服务 ${prefs.baseUrl()}")
            }
            if (msg.contains("联机心跳异常") || msg.contains("连接失败")) {
                ConnectionStatus.mark(false, msg)
            }
            updateTaskHint()
        }
        if (prefs.enabled && prefs.host.isNotBlank()) {
            agent?.forceRestart()
            appendLog("正在联机 ${prefs.baseUrl()}")
            syncVersionManual(silent = true)
        } else {
            ConnectionStatus.mark(false, "服务未连接（请到设置里配置服务器）")
            appendLog("请先点右上角「设置」配置服务器并连接")
        }
    }

    override fun onResume() {
        super.onResume()
        refreshA11y()
        tvDeviceKey.text = "设备Key：${prefs.deviceKey}"
        updateTaskHint()
        if (prefs.enabled && prefs.host.isNotBlank() && agent?.let { true } == true) {
            agent?.start()
            syncVersionManual(silent = true)
        }
    }

    private fun applyConnUi(st: ConnectionStatus.State) {
        tvConnStatus.text = st.message
        if (st.connected) {
            tvConnStatus.setBackgroundColor(Color.parseColor("#E8F5E9"))
            tvConnStatus.setTextColor(Color.parseColor("#1B5E20"))
        } else {
            tvConnStatus.setBackgroundColor(Color.parseColor("#FFF3E0"))
            tvConnStatus.setTextColor(Color.parseColor("#E65100"))
        }
    }

    private fun applyVersionUi(st: VersionStatus.State) {
        tvVersionInfo.text = st.message.ifBlank { "本机 v${ApiClient.APP_VERSION}" }
        if (st.outdated) {
            layoutUpdateBanner.visibility = View.VISIBLE
            tvUpdateHint.text = "版本不一致：本机 v${st.localVersion} → 服务端 v${st.serverVersion}"
            btnUpdateNow.isEnabled = !ApkUpdater.isBusy()
        } else {
            layoutUpdateBanner.visibility = View.GONE
        }
    }

    private fun syncVersionManual(silent: Boolean = false) {
        if (prefs.host.isBlank()) {
            if (!silent) {
                Toast.makeText(this, "请先配置服务器地址", Toast.LENGTH_SHORT).show()
            }
            return
        }
        btnSyncVersion.isEnabled = false
        lifecycleScope.launch {
            try {
                val res = withContext(Dispatchers.IO) {
                    ApiClient(prefs).fetchLatestOta()
                }
                if (!res.optBoolean("ok", false)) {
                    appendLog("同步版本失败：${res.optString("message")}")
                    if (!silent) Toast.makeText(this@MainActivity, "同步失败", Toast.LENGTH_SHORT).show()
                    return@launch
                }
                val data = res.optJSONObject("data")
                VersionStatus.applyServer(data, ApiClient.APP_VERSION)
                val st = VersionStatus.state.value
                appendLog(
                    if (st.outdated) "版本校验：不一致，本机 ${st.localVersion} / 服务端 ${st.serverVersion}"
                    else "版本校验：已同步，本机 ${st.localVersion}" +
                        if (st.serverVersion.isNotBlank()) " / 服务端 ${st.serverVersion}" else "",
                )
                if (!silent) {
                    Toast.makeText(
                        this@MainActivity,
                        if (st.outdated) "发现新版本 ${st.serverVersion}" else "版本已一致",
                        Toast.LENGTH_SHORT,
                    ).show()
                }
            } catch (e: Exception) {
                appendLog("同步版本异常: ${e.message}")
            } finally {
                btnSyncVersion.isEnabled = true
            }
        }
    }

    private fun startManualUpdate() {
        val payload = VersionStatus.latestPayloadJson()
        if (payload == null) {
            Toast.makeText(this, "暂无服务端安装包，请先点「同步版本」", Toast.LENGTH_SHORT).show()
            syncVersionManual()
            return
        }
        if (ApkUpdater.isBusy()) {
            Toast.makeText(this, "更新进行中…", Toast.LENGTH_SHORT).show()
            return
        }
        appendLog("手工更新：开始下载服务端包…")
        ApkUpdater.startManualUpdate(
            this,
            prefs,
            ApiClient(prefs),
            payload,
        ) { msg -> appendLog(msg) }
    }

    private fun updateTaskHint() {
        val running = agent?.isRunningTask() == true
        val rid = agent?.remoteTaskId
        tvTaskHint.text = when {
            running && rid != null -> "正在执行 Web 任务 #$rid"
            running -> "正在执行任务…"
            else -> "当前无执行任务，等待 Web 下发…"
        }
    }

    private fun ensureGalleryPermission() {
        val need = if (Build.VERSION.SDK_INT >= 33) {
            arrayOf(Manifest.permission.READ_MEDIA_IMAGES)
        } else {
            arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        }
        val miss = need.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (miss.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, miss.toTypedArray(), 1002)
        }
    }

    private fun refreshA11y() {
        tvA11y.text = if (CollectA11yService.isEnabled()) "无障碍：已开启" else "无障碍：未开启"
    }

    private fun appendLog(msg: String) {
        runOnUiThread {
            val line = "${LocalTime.now().format(tsFmt)} $msg"
            logs.add(line)
            while (logs.size > 400) logs.removeAt(0)
            tvLog.text = logs.joinToString("\n")
            val scroll = tvLog.layout?.getLineTop(tvLog.lineCount) ?: 0
            tvLog.scrollTo(0, (scroll - tvLog.height).coerceAtLeast(0))
            updateTaskHint()
        }
    }
}
