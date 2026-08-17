package com.collector.pdd.parser

import com.collector.pdd.data.ProductEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProductQualityGateTest {
    private val product = ProductEntity(
        itemId = "123456789",
        productName = "测试商品",
        itemUrl = "https://mobile.yangkeduo.com/goods.html?goods_id=123456789",
        price = 12.3,
        spec = "1盒",
        skuPricesText = "1盒=12.3",
        salesNum = 10,
    )

    @Test fun normalProductPasses() {
        val (normalized, decision) = ProductQualityGate.apply("商品详情 测试商品 单独购买 ¥12.3", product)
        assertTrue(decision.accepted)
        assertEquals("product", normalized.pageStatus)
        assertEquals("passed", normalized.qualityStatus)
    }

    @Test fun loginPageNeverProducesProduct() {
        val (normalized, decision) = ProductQualityGate.apply("手机号登录 验证码 登录", product)
        assertFalse(decision.accepted)
        assertEquals("login_required", normalized.pageStatus)
        assertEquals("quarantined", normalized.qualityStatus)
    }

    @Test fun missingPriceIsQuarantined() {
        val (normalized, decision) = ProductQualityGate.apply("商品详情 测试商品 立即购买", product.copy(price = null))
        assertFalse(decision.accepted)
        assertEquals("quarantined", normalized.qualityStatus)
    }
}
