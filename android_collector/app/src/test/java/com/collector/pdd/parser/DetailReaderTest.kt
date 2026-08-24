package com.collector.pdd.parser

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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

    @Test
    fun parse_genericParams_keepsFullTitleAndRejectsPartialLabelMatches() {
        val page = """
            返回
            【TOCI】水杨酸洗发水控油蓬松清爽去屑止痒柔顺修护持久留香洗头膏
            商品详情
            ¥24.99
            总售1.5万+件
            ---商品参数---
            商品参数
            品牌
            TOCI
            规格类型
            常规单品
            产品名称
            TOCI山茶花特护控油洗发水
            生产企业名称
            广州示例日化有限公司
            化妆品批准文号
            粤G妆网备字2025088015
            商品详情
            颜色
            款式
        """.trimIndent()

        val p = DetailReader.parse(page, "洗发水", "default_top_1", itemIdHint = "969857899556")
        assertEquals("【TOCI】水杨酸洗发水控油蓬松清爽去屑止痒柔顺修护持久留香洗头膏", p.sellName)
        assertEquals("TOCI山茶花特护控油洗发水", p.productName)
        assertEquals("广州示例日化有限公司", p.manufacturer)
        assertEquals("", p.spec)
        assertEquals("", p.skuPricesText)
        assertEquals("[]", p.skuPrices)
        val sources = org.json.JSONObject(p.fieldSources)
        assertEquals("none", sources.getString("sku"))
        assertEquals("none", sources.getString("comment_num"))
    }

    @Test
    fun parse_zeroComment_isObservedValue() {
        val page = "商品详情\n真实商品完整标题\n¥10\n评价 0\n立即购买"
        val p = DetailReader.parse(page, "测试", "default_top_1", itemIdHint = "123456789")
        assertEquals(0, p.commentNum)
        assertEquals("detail_text", org.json.JSONObject(p.fieldSources).getString("comment_num"))
    }

    @Test
    fun parse_peopleBeforeComment_isObserved() {
        val page = "商品详情\n真实商品完整标题\n¥10\n# 522人评价控油效果好\n立即购买"
        val p = DetailReader.parse(page, "测试", "default_top_1", itemIdHint = "123456789")
        assertEquals(522, p.commentNum)
        assertEquals("detail_text", org.json.JSONObject(p.fieldSources).getString("comment_num"))
    }

    @Test
    fun statusBar4gAfterSpecLabelIsNotAProductSpecOrSku() {
        val page = """
            商品详情
            多规格数据线完整标题
            商品参数
            规格
            4G
            ¥19.9
            立即购买
        """.trimIndent()

        val product = DetailReader.parse(page, "数据线", "default_top_1")

        assertEquals("", product.spec)
        assertFalse(product.specList.contains("4G"))
        assertEquals("[]", product.skuPrices)
        assertEquals("none", org.json.JSONObject(product.fieldSources).getString("sku"))
    }

    @Test
    fun skuPanelCombinationKeepsNullSkuIdAndPanelEvidence() {
        val panel = """
            请选择：颜色分类 尺码
            颜色分类
            酒红色 有口袋
            藏蓝色 有口袋
            尺码
            M 建议90-100斤
            L 建议100-110斤
            酒红色 有口袋 / M 建议90-100斤 ¥168
            藏蓝色 有口袋 / L 建议100-110斤 ¥178
        """.trimIndent()

        val product = DetailReader.parse(
            "商品详情\n多规格连衣裙完整标题\n¥168\n立即购买",
            "连衣裙", "default_top_1", skuPanelText = panel,
        )
        val skus = org.json.JSONArray(product.skuPrices)

        assertEquals(2, skus.length())
        assertTrue(skus.getJSONObject(0).isNull("sku_id"))
        assertEquals("SKU_PANEL", skus.getJSONObject(0).getString("evidence_source"))
        assertEquals("sku_panel", org.json.JSONObject(product.fieldSources).getString("sku"))
    }
    @Test
    fun skuPanelOpaqueDimensionValuesRemainPanelEvidenceWithoutMainPriceCopy() {
        val panel = """
            自定义属性A
            雾凇蓝 / ZX-8 ¥88
            暖灰 / ZX-9 ¥108
        """.trimIndent()
        val product = DetailReader.parse(
            "商品详情\n任意型号商品完整标题\n¥66\n立即购买",
            "任意商品", "default_top_1", skuPanelText = panel,
        )
        val skus = org.json.JSONArray(product.skuPrices)
        assertEquals(2, skus.length())
        assertEquals("雾凇蓝 / ZX-8", skus.getJSONObject(0).getString("spec"))
        assertEquals(88.0, skus.getJSONObject(0).getDouble("normal_price"), 0.0)
        assertTrue(skus.getJSONObject(0).isNull("sku_id"))
        assertEquals("SKU_PANEL", skus.getJSONObject(0).getString("evidence_source"))

        val withoutPanel = DetailReader.parse("商品详情\n任意型号商品完整标题\n¥66\n立即购买", "任意商品", "default_top_1")
        assertEquals("[]", withoutPanel.skuPrices)
    }

}
