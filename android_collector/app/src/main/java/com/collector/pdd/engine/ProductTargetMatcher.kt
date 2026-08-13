package com.collector.pdd.engine

import java.util.Locale

data class ProductTargetMatch(
    val matched: Boolean,
    val approvalMatched: Boolean,
    val nameMatched: Boolean,
    val specMatched: Boolean,
    val manufacturerMatched: Boolean,
    val expectedApproval: String,
    val actualApproval: String,
    val expectedName: String,
    val actualName: String,
    val expectedSpec: String,
    val actualSpec: String,
    val expectedManufacturer: String,
    val actualManufacturer: String,
)

object ProductTargetMatcher {
    fun match(
        expectedApproval: String,
        expectedName: String = "",
        expectedSpec: String,
        expectedManufacturer: String = "",
        actualApproval: String,
        actualName: String = "",
        actualSpec: String,
        actualManufacturer: String = "",
    ): ProductTargetMatch {
        val approvalMatched = normalizeApproval(expectedApproval).let { expected ->
            expected.isNotBlank() && expected == normalizeApproval(actualApproval)
        }
        val specMatched = normalizeSpec(expectedSpec).let { expected ->
            expected.isNotBlank() && expected == normalizeSpec(actualSpec)
        }
        val nameMatched = compatibleText(expectedName, actualName)
        val manufacturerMatched = compatibleText(expectedManufacturer, actualManufacturer)
        return ProductTargetMatch(
            matched = approvalMatched && nameMatched && specMatched && manufacturerMatched,
            approvalMatched = approvalMatched,
            nameMatched = nameMatched,
            specMatched = specMatched,
            manufacturerMatched = manufacturerMatched,
            expectedApproval = expectedApproval.trim(),
            actualApproval = actualApproval.trim(),
            expectedName = expectedName.trim(),
            actualName = actualName.trim(),
            expectedSpec = expectedSpec.trim(),
            actualSpec = actualSpec.trim(),
            expectedManufacturer = expectedManufacturer.trim(),
            actualManufacturer = actualManufacturer.trim(),
        )
    }

    fun normalizeApproval(value: String): String = normalizeCommon(value)
        .replace(Regex("[^0-9A-Z\\u4E00-\\u9FFF]"), "")

    fun normalizeSpec(value: String): String = normalizeCommon(value)
        .lowercase(Locale.ROOT)
        .replace('×', '*')
        .replace('Ｘ', '*')
        .replace('x', '*')
        .replace('／', '/')
        .replace(Regex("\\s+"), "")
        // 10粒、10片、10s 在药品规格匹配中视为同一种计数表达。
        .replace(Regex("(?<=\\d)(?:片|粒|丸|支|袋|贴|枚|只|s)"), "s")
        .replace(Regex("(?:/(?:盒|瓶|袋|支|板|包|罐|桶))+$"), "")
        .trim('/', ';', '；', '。', '.')

    fun normalizeText(value: String): String = normalizeCommon(value)
        .lowercase(Locale.ROOT)
        .replace(Regex("[\\s·•()（）\\-_/,.，。有限责任公司股份]"), "")

    private fun compatibleText(expectedRaw: String, actualRaw: String): Boolean {
        if (expectedRaw.isBlank()) return true
        val expected = normalizeText(expectedRaw)
        val actual = normalizeText(actualRaw)
        return expected.isNotBlank() && actual.isNotBlank() &&
            (expected == actual || expected.contains(actual) || actual.contains(expected))
    }

    private fun normalizeCommon(value: String): String = value
        .trim()
        .uppercase(Locale.ROOT)
        .replace('（', '(')
        .replace('）', ')')
        .replace('：', ':')
}
