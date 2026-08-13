package com.collector.pdd.engine

enum class AccessIssueType {
    BUSY,
    RISK,
    SOLD_OUT,
}

data class AccessIssue(
    val type: AccessIssueType,
    val evidence: String,
)

/**
 * 只依据当前无障碍页面文本分类，不执行点击，便于在纯 JVM 测试中验证。
 */
object AccessGuard {
    private val riskWords = listOf(
        "安全验证", "请完成验证", "滑块验证", "验证身份", "操作频繁",
        "访问过于频繁", "请求频繁", "异常访问", "账号异常",
    )
    private val busyWords = listOf(
        "系统繁忙", "网络繁忙", "服务繁忙", "当前访问人数过多",
        "访问人数过多", "请稍后再试", "加载失败", "页面走丢了",
    )
    private val soldOutWords = listOf(
        "已售罄", "暂时缺货", "已抢光", "商品已下架", "商品不存在", "该商品不存在",
    )

    fun detect(pageText: String): AccessIssue? {
        val text = pageText.replace(Regex("\\s+"), "")
        if (text.isBlank()) return null
        riskWords.firstOrNull(text::contains)?.let {
            return AccessIssue(AccessIssueType.RISK, it)
        }
        busyWords.firstOrNull(text::contains)?.let {
            return AccessIssue(AccessIssueType.BUSY, it)
        }
        soldOutWords.firstOrNull(text::contains)?.let {
            return AccessIssue(AccessIssueType.SOLD_OUT, it)
        }
        return null
    }
}
