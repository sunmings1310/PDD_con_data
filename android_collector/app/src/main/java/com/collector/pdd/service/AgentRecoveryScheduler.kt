package com.collector.pdd.service

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

/** Single recovery entry point for app start, boot and network restoration. */
object AgentRecoveryScheduler {
    const val UNIQUE_NAME = "pdd-agent-recovery"

    fun enqueue(context: Context): Boolean {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val work = OneTimeWorkRequestBuilder<AgentRecoveryWorker>()
            .setConstraints(constraints)
            .build()
        return try {
            WorkManager.getInstance(context.applicationContext)
                .enqueueUniqueWork(UNIQUE_NAME, ExistingWorkPolicy.KEEP, work)
            true
        } catch (error: IllegalStateException) {
            // Some secondary/test processes intentionally disable the AndroidX
            // initializer. The server lease timeout remains the recovery fence.
            Log.w("AgentRecovery", "WorkManager is not initialized", error)
            false
        }
    }
}
