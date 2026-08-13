package com.collector.pdd.engine

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProductTargetMatcherTest {
    @Test
    fun matchesApprovalAndNormalizedSpec() {
        val result = ProductTargetMatcher.match(
            expectedApproval = "国药准字 Z20063606",
            expectedName = "感冒灵颗粒",
            expectedSpec = "10g×10袋/盒",
            expectedManufacturer = "示例制药有限公司",
            actualApproval = "国药准字Z20063606",
            actualName = "感冒灵颗粒",
            actualSpec = "10G*10袋/盒",
            actualManufacturer = "示例制药",
        )
        assertTrue(result.matched)
    }

    @Test
    fun matchesTenCountAliases() {
        for (actual in listOf("10粒/盒", "10片/盒", "10s/盒")) {
            val result = ProductTargetMatcher.match(
                expectedApproval = "国药准字H12345678",
                expectedName = "测试药品",
                expectedSpec = "10S",
                expectedManufacturer = "测试药厂",
                actualApproval = "国药准字H12345678",
                actualName = "测试药品片",
                actualSpec = actual,
                actualManufacturer = "测试药厂有限公司",
            )
            assertTrue(actual, result.matched)
        }
    }

    @Test
    fun rejectsDifferentManufacturerInFourFieldMode() {
        val result = ProductTargetMatcher.match(
            expectedApproval = "国药准字H12345678", expectedName = "测试药品",
            expectedSpec = "10片", expectedManufacturer = "甲药厂",
            actualApproval = "国药准字H12345678", actualName = "测试药品",
            actualSpec = "10s", actualManufacturer = "乙药厂",
        )
        assertFalse(result.matched)
        assertFalse(result.manufacturerMatched)
    }

    @Test
    fun rejectsDifferentApproval() {
        val result = ProductTargetMatcher.match(
            expectedApproval = "国药准字Z20063606",
            expectedSpec = "10g*10袋/盒",
            actualApproval = "国药准字Z20063607",
            actualSpec = "10g*10袋/盒",
        )
        assertFalse(result.matched)
        assertFalse(result.approvalMatched)
        assertTrue(result.specMatched)
    }

    @Test
    fun rejectsDifferentSpec() {
        val result = ProductTargetMatcher.match(
            expectedApproval = "国药准字Z20063606",
            expectedSpec = "10g*10袋/盒",
            actualApproval = "国药准字Z20063606",
            actualSpec = "10g*20袋/盒",
        )
        assertFalse(result.matched)
        assertTrue(result.approvalMatched)
        assertFalse(result.specMatched)
    }

    @Test
    fun matchesInventorySWithDosageUnitAndOuterPackage() {
        val result = ProductTargetMatcher.match(
            expectedApproval = "国药准字H23023721",
            expectedSpec = "12S",
            actualApproval = "国药准字H23023721",
            actualSpec = "12粒/瓶/盒",
        )
        assertTrue(result.matched)
    }

    @Test
    fun ignoresOuterBoxButKeepsPackCountDifference() {
        val same = ProductTargetMatcher.match(
            expectedApproval = "国药准字Z51022126",
            expectedSpec = "10ml*10支",
            actualApproval = "国药准字Z51022126",
            actualSpec = "10ml*10支/盒",
        )
        val different = ProductTargetMatcher.match(
            expectedApproval = "国药准字Z51022126",
            expectedSpec = "10ml*10支",
            actualApproval = "国药准字Z51022126",
            actualSpec = "10ml*20支/盒",
        )
        assertTrue(same.matched)
        assertFalse(different.matched)
    }
}
