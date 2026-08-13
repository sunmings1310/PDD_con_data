package com.collector.pdd.engine

/**
 * 打开详情前从列表卡片预取的字段，对齐桌面 list → detail 交接。
 */
data class ListCardMeta(
    val listPrice: Double? = null,
    val itemId: String = "",
    val imageHint: String = "",
    val titleHint: String = "",
)
