package com.collector.pdd.ui

import android.app.Activity
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.view.WindowManager
import android.widget.EditText
import com.collector.pdd.R

/**
 * 前台粘贴承接页：不依赖 ClipboardManager.getPrimaryClip（很多机型会读空）。
 * 由无障碍对输入框执行 ACTION_PASTE，或本页自行粘贴，再把文本交回采集引擎。
 */
class ClipPeekActivity : Activity() {
    private var done = false
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var edit: EditText

    private val watcher = object : TextWatcher {
        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
        override fun afterTextChanged(s: Editable?) {
            val t = s?.toString()?.trim().orEmpty()
            if (t.isNotBlank() && looksUseful(t)) {
                finishWith(t)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL)
        setContentView(R.layout.activity_clip_peek)
        edit = findViewById(R.id.clip_paste_target)
        edit.addTextChangedListener(watcher)
        edit.requestFocus()
        // 给无障碍留时间找节点并粘贴
        handler.postDelayed({ trySelfPaste() }, 300L)
        handler.postDelayed({ trySelfPaste() }, 900L)
        handler.postDelayed({ trySelfPaste() }, 1600L)
        handler.postDelayed({ finishWith(edit.text?.toString().orEmpty()) }, 4500L)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            edit.requestFocus()
            handler.postDelayed({ trySelfPaste() }, 150L)
        }
    }

    /** 供外部（无障碍粘贴后）主动收口 */
    fun currentText(): String = edit.text?.toString()?.trim().orEmpty()

    private fun trySelfPaste() {
        if (done) return
        // 1) ClipboardManager（部分机型前台可读）
        val fromCm = readClip()
        if (looksUseful(fromCm)) {
            edit.setText(fromCm)
            return
        }
        // 2) 系统粘贴菜单项（比 getPrimaryClip 更宽松的机型）
        try {
            edit.setText("")
            edit.requestFocus()
            edit.onTextContextMenuItem(android.R.id.paste)
        } catch (_: Exception) {
        }
    }

    private fun readClip(): String {
        return try {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip ?: return ""
            val parts = mutableListOf<String>()
            for (i in 0 until clip.itemCount) {
                val item = clip.getItemAt(i) ?: continue
                item.text?.toString()?.let { if (it.isNotBlank()) parts.add(it) }
                item.htmlText?.let { if (it.isNotBlank()) parts.add(it) }
                item.uri?.toString()?.let { if (it.isNotBlank()) parts.add(it) }
                try {
                    val coerced = item.coerceToText(this)?.toString().orEmpty()
                    if (coerced.isNotBlank()) parts.add(coerced)
                } catch (_: Exception) {
                }
            }
            parts.distinct().joinToString("\n").trim()
        } catch (_: Exception) {
            ""
        }
    }

    private fun looksUseful(t: String): Boolean {
        if (t.isBlank()) return false
        val s = t.lowercase()
        return s.contains("http") || s.contains("yangkeduo") || s.contains("pinduoduo") ||
            s.contains("ps=") || s.contains("goods") || t.contains("￥") || t.contains("€")
    }

    private fun finishWith(text: String) {
        if (done) return
        done = true
        ClipPeekStore.complete(text)
        finish()
        overridePendingTransition(0, 0)
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        try {
            edit.removeTextChangedListener(watcher)
        } catch (_: Exception) {
        }
        if (!done) ClipPeekStore.complete(edit.text?.toString().orEmpty())
        super.onDestroy()
    }

    companion object {
        const val VIEW_ID = "com.collector.pdd:id/clip_paste_target"
        const val DESC = "collector_clip_paste_target"
    }
}
