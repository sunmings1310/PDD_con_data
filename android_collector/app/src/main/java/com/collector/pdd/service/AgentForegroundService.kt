package com.collector.pdd.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.collector.pdd.CollectorApp
import com.collector.pdd.R
import com.collector.pdd.net.AgentCoordinator

/** Visible service keeps the Coordinator alive while accessibility UI is active. */
class AgentForegroundService : Service() {
    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, notification())
        val app = application as CollectorApp
        AgentCoordinator.ensure(app) { /* Coordinator owns structured logging. */ }.start()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        AgentCoordinator.ensure(application as CollectorApp) {}.start()
        return START_STICKY
    }

    override fun onDestroy() {
        AgentCoordinator.ensure(application as CollectorApp) {}.stop()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(): Notification {
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val pending = launch?.let {
            PendingIntent.getActivity(
                this,
                0,
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or
                    (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0),
            )
        }
        return NotificationCompat.Builder(this, CollectorApp.CHANNEL_COLLECT)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("采集恢复服务运行中")
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setContentIntent(pending)
            .build()
    }

    companion object {
        private const val NOTIFICATION_ID = 701
    }
}
