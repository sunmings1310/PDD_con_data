package com.collector.pdd.service

import android.content.Intent
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.collector.pdd.CollectorApp
import com.collector.pdd.net.ServerPrefs

/** WorkManager is only the network-aware wakeup; long UI work belongs to the FGS. */
class AgentRecoveryWorker(
    appContext: android.content.Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val prefs = ServerPrefs(applicationContext)
        if (!prefs.enabled || prefs.host.isBlank()) return Result.success()
        val intent = Intent(applicationContext, AgentForegroundService::class.java)
        ContextCompat.startForegroundService(applicationContext, intent)
        return Result.success()
    }
}
