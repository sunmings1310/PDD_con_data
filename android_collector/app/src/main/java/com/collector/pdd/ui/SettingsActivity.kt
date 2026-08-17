package com.collector.pdd.ui

import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.collector.pdd.CollectorApp
import com.collector.pdd.R
import com.collector.pdd.net.AgentCoordinator
import com.collector.pdd.net.ApiClient
import com.collector.pdd.net.ServerPrefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SettingsActivity : AppCompatActivity() {

    private lateinit var prefs: ServerPrefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        title = "联机设置"
        prefs = ServerPrefs(this)

        val cbOnline = findViewById<CheckBox>(R.id.cbOnline)
        val etHost = findViewById<EditText>(R.id.etServerHost)
        val etPort = findViewById<EditText>(R.id.etServerPort)
        val etName = findViewById<EditText>(R.id.etDeviceName)
        val etEnrollmentToken = findViewById<EditText>(R.id.etEnrollmentToken)
        val tvKey = findViewById<TextView>(R.id.tvDeviceKey)
        val tvResult = findViewById<TextView>(R.id.tvTestResult)

        cbOnline.isChecked = prefs.enabled
        etHost.setText(prefs.host)
        etPort.setText(if (prefs.port > 0) prefs.port.toString() else "")
        etName.setText(prefs.deviceName)
        etEnrollmentToken.setText(prefs.enrollmentToken)
        tvKey.text = "设备Key：${prefs.deviceKey}"

        findViewById<Button>(R.id.btnSaveServer).setOnClickListener {
            prefs.host = etHost.text.toString().trim()
            prefs.port = etPort.text.toString().trim().toIntOrNull() ?: 0
            prefs.deviceName = etName.text.toString().trim().ifBlank { Build.MODEL }
            prefs.enrollmentToken = etEnrollmentToken.text.toString().trim()
            prefs.enabled = cbOnline.isChecked
            tvKey.text = "设备Key：${prefs.deviceKey}"

            if (!prefs.enabled || prefs.host.isBlank()) {
                AgentCoordinator.ensure(CollectorApp.instance) {}.stop()
                ConnectionStatus.mark(false, "服务未连接（联机已关闭）")
                tvResult.text = "已关闭联机"
                Toast.makeText(this, "已关闭联机", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            tvResult.text = "正在检测 ${prefs.baseUrl()} …"
            lifecycleScope.launch {
                val ping = withContext(Dispatchers.IO) {
                    runCatching { ApiClient(prefs).pingHealth() }.getOrElse { "连接失败：${it.message}" }
                }
                tvResult.text = ping
                if (!ping.startsWith("连接成功")) {
                    ConnectionStatus.mark(false, ping)
                    Toast.makeText(this@SettingsActivity, "连接失败", Toast.LENGTH_LONG).show()
                    return@launch
                }
                val reg = withContext(Dispatchers.IO) {
                    runCatching {
                        val r = ApiClient(prefs).register()
                        if (r.optBoolean("ok", false)) "设备注册成功" else "注册失败：${r.optString("message")}"
                    }.getOrElse { "注册失败：${it.message}" }
                }
                tvResult.text = "$ping\n$reg"
                val agent = AgentCoordinator.ensure(CollectorApp.instance) {}
                agent.forceRestart()
                ConnectionStatus.mark(true, "已连接服务 ${prefs.baseUrl()}")
                Toast.makeText(this@SettingsActivity, "连接成功", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
