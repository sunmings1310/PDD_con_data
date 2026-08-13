package com.collector.pdd.data

data class CollectTarget(
    val keyword: String,
    val targetApproval: String = "",
    val targetName: String = "",
    val targetSpec: String = "",
    val targetManufacturer: String = "",
    val remoteItemId: Long? = null,
) {
    val requiresMatch: Boolean
        get() = targetApproval.isNotBlank() && targetSpec.isNotBlank()
}

data class CollectConfig(
    val keywords: List<String> = emptyList(),
    /** Excel 下发的逐行匹配目标；为空时保持普通关键词采集。 */
    val targets: List<CollectTarget> = emptyList(),
    val maxDetailPerKeyword: Int = 5,
    val enablePriceSort: Boolean = false,
    val enableSalesSort: Boolean = false,
    /** gentle | normal | strict */
    val humanLevel: String = "strict",
    val delayMinMs: Long = 1200,
    val delayMaxMs: Long = 3500,
    val thinkMinMs: Long = 600,
    val thinkMaxMs: Long = 2200,
    val readMinMs: Long = 1500,
    val readMaxMs: Long = 4500,
    val keywordGapMinMs: Long = 5000,
    val keywordGapMaxMs: Long = 15000,
    val itemGapMinMs: Long = 3000,
    val itemGapMaxMs: Long = 9000,
    /** 每批访问的商品数；达到后执行批次冷却。 */
    val batchSize: Int = 4,
    val batchCooldownMs: Long = 25_000,
    /** retry | skip | stop */
    val busyResponse: String = "retry",
    val busyRetryCount: Int = 0,
    val busyCooldownMs: Long = 15_000,
    val riskCooldownMs: Long = 60_000,
    /** 连续售罄达到阈值后停止；0 表示不停。 */
    val soldOutStopThreshold: Int = 2,
    /** 连续动作异常达到阈值后截图、上报并终止；0 表示不自动终止。 */
    val anomalyStopThreshold: Int = 3,
    /** 图片规则兼容位：当前固定 false，后续版本可直接接入规则引擎。 */
    val imageRuleEnabled: Boolean = false,
    val imageRuleVersion: Int = 1,
    /** 服务端任务 ID（联机模式） */
    val remoteTaskId: Long? = null,
    val platformCode: String = "pinduoduo",
    /** collect | nurture；养护任务只浏览，不写入商品资料库。 */
    val taskType: String = "collect",
    val platformAccountId: Long? = null,
    /** 额外拟人动作：回滑、浏览、走神 */
    val enableHumanGestures: Boolean = true,
)
