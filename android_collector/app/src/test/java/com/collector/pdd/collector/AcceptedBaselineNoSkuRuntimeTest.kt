package com.collector.pdd.collector

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class AcceptedBaselineNoSkuRuntimeTest {
    @Test
    fun defaultDetailCollectionDoesNotEnterSkuPurchaseFlow() {
        val source = File(
            "src/main/java/com/collector/pdd/collector/PddCollector.kt",
        ).readText()
        val detailFlow = source.substring(
            source.indexOf("private object PddDetailCollector"),
            source.indexOf("private class PddCollectorSession"),
        )

        assertFalse(detailFlow.contains("openAndReadSkuPrices("))
        assertFalse(detailFlow.contains("purchase-or-selector-panel"))
        assertFalse(detailFlow.contains("listOf(\"sku\""))
        assertTrue(detailFlow.contains("listOf(\"params\", \"shop_sales\", \"human\")"))
    }

    @Test
    fun genericSkuInvestigationRuntimeIsAbsent() {
        val actions = File(
            "src/main/java/com/collector/pdd/engine/PddActions.kt",
        ).readText()

        assertFalse(actions.contains("GenericSkuContract"))
        assertFalse(actions.contains("readSkuPricesByClickingCombinations"))
        assertFalse(actions.contains("findSkuPurchaseEntryButtons"))
    }
}
