"""多平台预留：当前启用拼多多，后续天猫/京东/抖音。"""

from __future__ import annotations

# 代码常量，与 SJZQ_PLATFORM 种子一致
PLATFORM_PINDUODUO = "pinduoduo"
PLATFORM_TMALL = "tmall"
PLATFORM_JD = "jd"
PLATFORM_DOUYIN = "douyin"

KNOWN_PLATFORMS = {
    PLATFORM_PINDUODUO: "拼多多",
    PLATFORM_TMALL: "天猫",
    PLATFORM_JD: "京东",
    PLATFORM_DOUYIN: "抖音",
}

# 任务类型
TASK_COLLECT = "collect"
TASK_NURTURE = "nurture"

TASK_TYPES = {
    TASK_COLLECT: "采集",
    TASK_NURTURE: "养号",
}
