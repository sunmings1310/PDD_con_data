package com.collector.pdd.service

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.PendingIntent
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.app.NotificationCompat
import com.collector.pdd.CollectorApp
import com.collector.pdd.R
import com.collector.pdd.ui.MainActivity
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class CollectA11yService : AccessibilityService() {

    @Volatile
    var lastToastText: String = ""
        private set

    private val mainHandler = Handler(Looper.getMainLooper())
    private var lastAutoClickAt = 0L

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        _connected.value = true
        try {
            startForeground(NOTIF_ID, buildNotification(getString(R.string.notify_idle)))
        } catch (_: Exception) {
            // 部分机型无通知权限时忽略，无障碍仍可用
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        when (event.eventType) {
            AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED,
            AccessibilityEvent.TYPE_ANNOUNCEMENT,
            -> {
                val t = buildString {
                    event.text?.forEach { append(it).append(' ') }
                    event.contentDescription?.let { append(it) }
                }.trim()
                if (t.isNotBlank()) lastToastText = t
            }
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
            -> {
                if (autoAcceptProjection) {
                    mainHandler.post { tryAutoAcceptProjection() }
                }
            }
        }
    }

    /**
     * 自动点击系统录屏/投屏确认框：立即开始 / Start now / 允许 等。
     */
    private fun tryAutoAcceptProjection() {
        val now = System.currentTimeMillis()
        if (now - lastAutoClickAt < 600) return
        val root = rootInActiveWindow ?: return
        // 优先点「整个屏幕」选项（Android 14+）
        clickTextInTree(root, listOf("整个屏幕", "Entire screen", "整块屏幕"))
        val ok = clickTextInTree(
            root,
            listOf(
                "立即开始",
                "开始录制",
                "开始",
                "允许",
                "确定",
                "Start now",
                "START NOW",
                "Allow",
                "OK",
            ),
        )
        if (ok) {
            lastAutoClickAt = now
            autoAcceptProjection = false
        }
    }

    private fun clickTextInTree(root: AccessibilityNodeInfo, texts: List<String>): Boolean {
        for (t in texts) {
            val nodes = root.findAccessibilityNodeInfosByText(t) ?: continue
            for (n in nodes) {
                if (clickNodeOrParent(n)) return true
            }
        }
        // 部分机型按钮无文字，扫可点击叶子
        return false
    }

    private fun clickNodeOrParent(node: AccessibilityNodeInfo?): Boolean {
        var cur = node
        var depth = 0
        while (cur != null && depth < 6) {
            if (cur.isClickable) {
                if (cur.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
            }
            cur = cur.parent
            depth++
        }
        return false
    }

    override fun onInterrupt() {
        // no-op
    }

    override fun onDestroy() {
        _connected.value = false
        if (instance === this) instance = null
        super.onDestroy()
    }

    fun updateNotification(text: String) {
        val nm = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        nm.notify(NOTIF_ID, buildNotification(text))
    }

    /** 任务结束：尽量从无障碍前台服务拉起主界面（含全屏 Intent / PendingIntent 兜底） */
    fun forceOpenMain(reason: String): Boolean {
        updateNotification(reason)
        val launch = mainLaunchIntent()
        var ok = false
        try {
            startActivity(launch)
            ok = true
        } catch (_: Exception) {
        }
        try {
            val pi = PendingIntent.getActivity(
                this,
                1002,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            pi.send()
            ok = true
        } catch (_: Exception) {
        }
        // 高优先级通知 + 全屏 Intent（华为常拦 startActivity，靠这个拉起）
        try {
            val pi = PendingIntent.getActivity(
                this,
                1003,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val n = NotificationCompat.Builder(this, CollectorApp.CHANNEL_ALERT)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(reason)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentIntent(pi)
                .setFullScreenIntent(pi, true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setAutoCancel(true)
                .setTimeoutAfter(15_000)
                .build()
            val nm = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
            nm.notify(NOTIF_ALERT_ID, n)
            ok = true
        } catch (_: Exception) {
        }
        return ok
    }

    fun mainLaunchIntent(): Intent {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
            ?: Intent(this, MainActivity::class.java)
        launch.addFlags(
            Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_CLEAR_TOP or
                Intent.FLAG_ACTIVITY_SINGLE_TOP or
                Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or
                Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED,
        )
        return launch
    }

    private fun buildNotification(content: String): Notification {
        val pi = PendingIntent.getActivity(
            this,
            0,
            mainLaunchIntent(),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CollectorApp.CHANNEL_COLLECT)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(content)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val NOTIF_ID = 1001
        private const val NOTIF_ALERT_ID = 1008
        @Volatile var instance: CollectA11yService? = null
            private set

        /** 投屏授权期间为 true，无障碍自动点确认 */
        @Volatile var autoAcceptProjection: Boolean = false

        private val _connected = MutableStateFlow(false)
        val connected: StateFlow<Boolean> = _connected

        fun isEnabled(): Boolean = instance != null
    }
}
