package com.collector.pdd.parser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DetailReaderTest {
    @Test
    fun inferPackPrices_linearRange() {
        val m = DetailReader.inferPackPrices(listOf("1盒装", "3盒装", "5盒装"), 860.0, 4300.0)
        assertEquals(860.0, m["1盒装"])
        assertEquals(2580.0, m["3盒装"])
        assertEquals(4300.0, m["5盒装"])
    }

    @Test
    fun extractBottomBarPrices_subsidy() {
        val text = """
            官方补贴32.2元
            百亿补贴 · 正品保障
            补贴价 快要抢光 ¥63.5
            品牌正品 免拼购买
        """.trimIndent()
        val p = DetailReader.extractBottomBarPrices(text)
        assertEquals(63.5, p.display)
        assertEquals(63.5, p.group)
    }

    @Test
    fun extractBottomBarPrices_fuzhenAsDeal() {
        val text = """
            ¥9.5
            最后2件
            【金石可致】头孢克洛颗粒 0.125g*12袋/盒 RX
            雪芙蓉大药房旗舰店
            本品为处方药，需凭处方在药师指导下购买和使用
            去复诊开药
        """.trimIndent()
        val p = DetailReader.extractBottomBarPrices(text)
        assertEquals(9.5, p.display)
        assertEquals(9.5, p.deal)
        assertEquals(null, p.group)
    }

    @Test
    fun extractShopName_rejectTitlePharmacyZhifa() {
        val page = """
            ¥9.5
            最后2件
            【金石可致】头孢克洛颗粒 0.125g*12袋/盒 RX 正品保证 药房直发 假一赔十
            雪芙蓉大药房
            100%正品，资质可官网验真
            本品为处方药，需凭处方在药师指导下购买和使用
            雪芙蓉大药房旗舰店
            旗舰店
            3年老店
            本店已拼12.3万+件
            进店
            去复诊开药
        """.trimIndent()
        assertEquals("雪芙蓉大药房旗舰店", DetailReader.extractShopName(page))
        val p = DetailReader.parse(page, "头孢克洛颗粒", "default_top_1")
        assertEquals("雪芙蓉大药房旗舰店", p.shopName)
    }

    @Test
    fun parse_productDetailGrid_andRejectJunkBrand() {
        val page = """
            综合
            销量
            价格
            筛选
            金牛纲目大药房旗舰店
            商品详情
            品牌 999
            药品通用名 感冒灵颗粒
            药品规格 10g*9袋/盒
            查看全部
            补贴价 快要抢光 ¥63.5
            品牌正品 免拼购买
            ---商品参数---
            商品参数
            品牌
            999
            药品通用名
            感冒灵颗粒
            药品规格
            10g*9袋/盒
            产品剂型
            颗粒剂
            批准文号
            国药准字Z44021019
            生产企业
            华润三九医药股份有限公司
            goods_id=98765432101
            https://img.pddpic.com/goods/a.jpg
        """.trimIndent()
        val p = DetailReader.parse(page, "感冒灵颗粒", "default_top_1", listPrice = 6.0)
        assertNotEquals("筛选", p.brand)
        assertEquals("999", p.brand)
        assertEquals("感冒灵颗粒", p.productName)
        assertEquals("10g*9袋/盒", p.spec)
        assertEquals(63.5, p.displayPrice)
        assertEquals(63.5, p.groupPrice)
        assertTrue(p.sellName.contains("感冒灵"))
        assertTrue(p.itemUrl.contains("98765432101"))
        assertTrue(p.mainImages.contains("pddpic"))
        assertEquals("颗粒剂", p.dosageForm)
    }
}
