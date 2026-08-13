package com.collector.pdd.ui

import kotlinx.coroutines.CompletableDeferred

/**
 * 剪贴板偷看 / 分享接收 的结果中转。
 */
object ClipPeekStore {
    @Volatile
    var latest: String = ""
        private set

    private var pending: CompletableDeferred<String>? = null

    @Synchronized
    fun beginAwait(): CompletableDeferred<String> {
        pending?.cancel()
        val d = CompletableDeferred<String>()
        pending = d
        latest = ""
        return d
    }

    /** 有内容就写入；空串仅在仍有等待方时用于结束等待 */
    @Synchronized
    fun offer(text: String) {
        if (text.isNotBlank()) latest = text
        val d = pending ?: return
        pending = null
        if (!d.isCompleted) d.complete(text)
    }

    @Synchronized
    fun complete(text: String) = offer(text)

    @Synchronized
    fun cancel() {
        val d = pending
        pending = null
        if (d != null && !d.isCompleted) d.complete("")
    }
}
