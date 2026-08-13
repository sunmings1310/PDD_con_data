package com.collector.pdd.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AccessGuardTest {
    @Test
    fun detectsBusyResponse() {
        assertEquals(
            AccessIssueType.BUSY,
            AccessGuard.detect("系统繁忙，请稍后再试")?.type,
        )
    }

    @Test
    fun riskTakesPriorityOverGenericBusyText() {
        assertEquals(
            AccessIssueType.RISK,
            AccessGuard.detect("操作频繁，请完成验证后稍后再试")?.type,
        )
    }

    @Test
    fun detectsSoldOutAndIgnoresNormalDetail() {
        assertEquals(
            AccessIssueType.SOLD_OUT,
            AccessGuard.detect("商品已售罄，看看其他商品")?.type,
        )
        assertNull(AccessGuard.detect("商品详情 立即购买 已拼10万件"))
    }
}
