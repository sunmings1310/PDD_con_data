package com.collector.pdd.parser

import com.collector.pdd.data.ProductEntity
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class CollectionFixtureReplayTest {
    private fun fixtureDir(): File {
        val candidates = listOf(
            File("../../tests/fixtures/pinduoduo"),
            File("../tests/fixtures/pinduoduo"),
            File("tests/fixtures/pinduoduo"),
        )
        return candidates.firstOrNull(File::isDirectory)
            ?: error("fixture directory not found from ${File(".").absolutePath}")
    }

    private fun fixtures(): List<JSONObject> = fixtureDir().listFiles { f -> f.extension == "json" }
        .orEmpty().sortedBy(File::getName).map { JSONObject(it.readText(Charsets.UTF_8)) }

    private val validProduct = ProductEntity(
        itemId = "123456789",
        productName = "fixture guard product",
        itemUrl = "https://mobile.yangkeduo.com/goods.html?goods_id=123456789",
        price = 10.0,
        skuPricesText = "default=10",
        salesNum = 1,
    )

    @Test fun everyFixtureUsesCanonicalVersionsAndPageClassifier() {
        val all = fixtures()
        assertTrue(all.size >= 10)
        all.forEach { fixture ->
            assertEquals("pdd-android-1", fixture.getString("parser_version"))
            assertEquals("phase1-1", fixture.getString("quality_rules_version"))
            assertEquals(
                "fixture=${fixture.getString("fixture_id")}",
                fixture.getString("page_status"),
                ProductQualityGate.classifyPage(fixture.getString("page_text")),
            )
        }
    }

    @Test fun everyAbnormalFixtureIsRejectedEvenWithOtherwiseValidProduct() {
        fixtures().filter { it.getString("page_status") != "product" }.forEach { fixture ->
            val (_, decision) = ProductQualityGate.apply(fixture.getString("page_text"), validProduct)
            assertFalse("fixture=${fixture.getString("fixture_id")}", decision.accepted)
            assertEquals("quarantined", decision.qualityStatus)
        }
    }

    @Test fun normalFixtureParsesAndPassesWithoutNetwork() {
        val fixture = fixtures().first { it.getString("fixture_id") == "pdd-normal-001" }
        val expected = fixture.getJSONObject("expected")
        val parsed = DetailReader.parse(
            pageText = fixture.getString("page_text"),
            keyword = "维生素C",
            pickTag = "fixture",
            listPrice = expected.getDouble("price"),
            itemIdHint = expected.getString("item_id"),
            urlHint = fixture.getString("page_url"),
            skuPanelText = "1盒 ¥12.99\n2盒 ¥23.99",
        )
        val (_, decision) = ProductQualityGate.apply(fixture.getString("page_text"), parsed)
        assertTrue(decision.accepted)
        assertEquals(expected.getString("item_id"), parsed.itemId)
        assertTrue((parsed.price ?: 0.0) > 0.0)
    }
}
