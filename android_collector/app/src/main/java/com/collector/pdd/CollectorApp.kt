package com.collector.pdd

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.collector.pdd.data.AppDatabase

class CollectorApp : Application() {
    lateinit var database: AppDatabase
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        database = AppDatabase.get(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_COLLECT,
                    getString(R.string.channel_collect),
                    NotificationManager.IMPORTANCE_LOW,
                ),
            )
            // 任务结束强提醒：用于鸿蒙/华为拦截后台拉起时兜底
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ALERT,
                    "任务结束提醒",
                    NotificationManager.IMPORTANCE_HIGH,
                ).apply {
                    description = "采集结束后返回联机工具"
                    setBypassDnd(true)
                },
            )
        }
    }

    companion object {
        const val CHANNEL_COLLECT = "collect_channel"
        const val CHANNEL_ALERT = "task_end_alert"
        lateinit var instance: CollectorApp
            private set
    }
}
