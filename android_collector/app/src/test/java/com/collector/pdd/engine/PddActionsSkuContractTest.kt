package com.collector.pdd.engine

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PddActionsSkuContractTest {
    @Test fun arbitraryPlatformLabelsAreCandidatesWithoutDimensionVocabulary() {
        assertTrue(GenericSkuContract.isCandidateHeader("自定义字段-A"))
        assertTrue(GenericSkuContract.isCandidateOption("雾凇蓝"))
        assertTrue(GenericSkuContract.isCandidateOption("ZX-8"))
        assertTrue(GenericSkuContract.isCandidateOption("基础包"))
    }

    @Test fun checkoutControlsNeverBecomeSkuOptions() {
        assertFalse(GenericSkuContract.isCandidateOption("提交订单"))
        assertFalse(GenericSkuContract.isCandidateOption("立即支付"))
        assertFalse(GenericSkuContract.isCandidateOption("¥88"))
    }
    @Test fun dimensionWordsStayOpaqueRawLabelsRatherThanControlVocabulary() {
        listOf("颜色", "尺码", "容量", "型号", "套餐", "规格", "款式", "包装数量", "一次选多款")
            .forEach { label ->
                assertTrue("header: $label", GenericSkuContract.isCandidateHeader(label))
                assertTrue("option: $label", GenericSkuContract.isCandidateOption(label))
            }
    }

}
