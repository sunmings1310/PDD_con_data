package com.collector.pdd.service

import android.content.ClipboardManager
import android.content.Context
import android.graphics.PixelFormat
import android.view.accessibility.AccessibilityWindowInfo
import android.view.Gravity
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import com.collector.pdd.engine.GoodsLinkResolver
import com.collector.pdd.ui.ClipPeekActivity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * 用无障碍悬浮窗（TYPE_ACCESSIBILITY_OVERLAY）承接粘贴。
 * 不跳转 Activity、不点「更多分享」，避免离开拼多多细节页。
 */
object PasteOverlay {
    private const val DESC = ClipPeekActivity.DESC

    suspend fun captureLink(service: CollectA11yService, log: (String) -> Unit): String {
        return withContext(Dispatchers.Main) {
            var edit: EditText? = null
            var wm: WindowManager? = null
            try {
                wm = service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
                val et = EditText(service).apply {
                    contentDescription = DESC
                    hint = "paste"
                    minLines = 2
                    isSingleLine = false
                    setText("")
                    isFocusable = true
                    isFocusableInTouchMode = true
                    // 悬浮输入框只承接剪贴板粘贴，不需要弹出软键盘。
                    showSoftInputOnFocus = false
                    importantForAccessibility = android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES
                    setBackgroundColor(0x66FFFFFF)
                    setTextColor(0xFF000000.toInt())
                    textSize = 12f
                }
                edit = et
                val lp = WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.WRAP_CONTENT,
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                    // 必须可获焦，否则粘贴/读剪贴板无效
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT,
                ).apply {
                    gravity = Gravity.TOP
                    y = 80
                    title = "linkdesk_overlay"
                    softInputMode = WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN or
                        WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING
                }
                wm.addView(et, lp)
                et.requestFocus()
                delay(400)

                // 1) 悬浮窗获焦后直接读剪贴板（部分机型对 a11y 放宽）
                var text = readClipboard(service)
                if (isLink(text)) {
                    log("悬浮窗读剪贴板成功")
                    return@withContext text
                }

                // 2) 本视图粘贴菜单
                try {
                    et.onTextContextMenuItem(android.R.id.paste)
                    delay(200)
                    text = et.text?.toString().orEmpty()
                    if (isLink(text)) {
                        log("悬浮窗本地粘贴成功")
                        return@withContext text
                    }
                } catch (_: Exception) {
                }

                // 3) 无障碍 ACTION_PASTE
                text = a11yPaste(service, log)
                if (isLink(text)) return@withContext text

                // 4) 长按 → 点「粘贴」
                text = longPressPaste(service, log)
                if (isLink(text)) return@withContext text

                text = et.text?.toString().orEmpty()
                if (isLink(text)) return@withContext text

                log("悬浮窗粘贴未得到链接")
                ""
            } catch (e: Exception) {
                log("悬浮窗异常: ${e.message}")
                ""
            } finally {
                try {
                    val e = edit
                    val w = wm
                    if (e != null) {
                        val token = e.windowToken
                        e.clearFocus()
                        val imm = service.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
                        if (token != null) {
                            imm.hideSoftInputFromWindow(token, InputMethodManager.HIDE_NOT_ALWAYS)
                        }
                        if (w != null) w.removeViewImmediate(e)

                        // 部分定制系统在输入视图移除后仍保留 IME 窗口；确认存在时才按一次返回，
                        // 避免键盘已关闭时误退拼多多详情页。
                        delay(180)
                        if (isInputMethodVisible(service)) {
                            log("检测到输入法仍显示，执行返回收起输入法")
                            service.performGlobalAction(
                                android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK,
                            )
                            delay(250)
                        }
                        log("悬浮输入框已关闭，输入法显示=${isInputMethodVisible(service)}")
                    }
                } catch (e: Exception) {
                    log("关闭悬浮输入框/输入法异常: ${e.message}")
                }
            }
        }
    }

    private fun isInputMethodVisible(service: CollectA11yService): Boolean {
        return try {
            service.windows.any { window ->
                window.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD && window.root != null
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun isLink(t: String): Boolean {
        if (t.isBlank()) return false
        return GoodsLinkResolver.extractGoodsUrls(t).isNotEmpty() ||
            GoodsLinkResolver.extractGoodsId(t).isNotBlank() ||
            t.contains("yangkeduo.com", true) ||
            t.contains("pinduoduo.com", true) ||
            t.contains("ps=", true)
    }

    private fun readClipboard(ctx: Context): String {
        return try {
            val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip ?: return ""
            buildString {
                for (i in 0 until clip.itemCount) {
                    val item = clip.getItemAt(i) ?: continue
                    item.text?.let { append(it).append('\n') }
                    item.coerceToText(ctx)?.let { append(it).append('\n') }
                }
            }.trim()
        } catch (_: Exception) {
            ""
        }
    }

    private suspend fun a11yPaste(service: CollectA11yService, log: (String) -> Unit): String {
        repeat(8) {
            val node = A11yHelper.findByContentDescAllWindows(service, DESC)
            if (node != null) {
                node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                val ok = node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
                delay(220)
                node.refresh()
                val t = node.text?.toString().orEmpty()
                log("悬浮窗ACTION_PASTE ok=$ok len=${t.length}")
                if (isLink(t)) return t
            }
            delay(200)
        }
        return ""
    }

    private suspend fun longPressPaste(service: CollectA11yService, log: (String) -> Unit): String {
        val node = A11yHelper.findByContentDescAllWindows(service, DESC) ?: return ""
        val r = A11yHelper.bounds(node)
        if (r.width() <= 0) return ""
        log("长按悬浮输入框唤起粘贴菜单")
        // 长按中心
        A11yHelper.longPress(service, r.exactCenterX(), r.exactCenterY())
        delay(500)
        val paste = A11yHelper.findByTextAllWindows(service, "粘贴", exact = true, clickableOnly = true)
            ?: A11yHelper.findByTextAllWindows(service, "粘贴", exact = false, clickableOnly = false)
            ?: A11yHelper.findByTextAllWindows(service, "Paste", exact = false, clickableOnly = false)
        if (paste != null) {
            A11yHelper.clickNode(service, paste)
            delay(350)
        } else {
            log("未找到粘贴菜单项")
        }
        val again = A11yHelper.findByContentDescAllWindows(service, DESC)
        again?.refresh()
        return again?.text?.toString().orEmpty()
    }
}
