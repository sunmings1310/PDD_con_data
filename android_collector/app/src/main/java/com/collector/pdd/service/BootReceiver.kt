package com.collector.pdd.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Boot only schedules constrained recovery; it never starts an infinite service directly. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
            AgentRecoveryScheduler.enqueue(context)
        }
    }
}
