package com.collector.pdd.ui

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.WindowManager

/**
 * 作为系统分享目标接收拼多多分享的文本/链接。
 * 比读剪贴板更可靠（部分机型禁止后台/自动化读剪贴板）。
 */
class ShareReceiveActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL)
        val text = extractShareText(intent)
        if (text.isNotBlank()) {
            ClipPeekStore.offer(text)
        } else {
            ClipPeekStore.offer("")
        }
        finish()
        overridePendingTransition(0, 0)
    }

    private fun extractShareText(intent: Intent?): String {
        if (intent == null) return ""
        val parts = mutableListOf<String>()
        intent.getStringExtra(Intent.EXTRA_TEXT)?.let { parts.add(it) }
        intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()?.let { parts.add(it) }
        intent.getStringExtra(Intent.EXTRA_SUBJECT)?.let { parts.add(it) }
        intent.clipData?.let { clip ->
            for (i in 0 until clip.itemCount) {
                clip.getItemAt(i)?.coerceToText(this)?.toString()?.let {
                    if (it.isNotBlank()) parts.add(it)
                }
            }
        }
        intent.dataString?.let { parts.add(it) }
        return parts.distinct().joinToString("\n").trim()
    }
}
