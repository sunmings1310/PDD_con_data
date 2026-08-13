package com.collector.pdd.engine

import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

/**
 * 从系统 dumpsys 里捞拼多多当前页的 goods_id / ps= 分享参。
 * 不依赖剪贴板；部分机型无需 root 可读 activity 信息。
 */
object ActivityDumpResolver {

    data class Hit(
        val goodsId: String = "",
        val shareUrl: String = "",
        val rawSnippet: String = "",
    )

    fun probePdd(): Hit {
        val dumps = listOf(
            shell("dumpsys activity top"),
            shell("dumpsys activity activities"),
            shell("dumpsys activity recents"),
        ).filter { it.isNotBlank() }
        if (dumps.isEmpty()) return Hit()

        val blob = dumps.joinToString("\n")
        // 只关心拼多多相关片段，降低误伤
        val focused = blob.lineSequence()
            .filter {
                it.contains("pinduoduo", true) || it.contains("yangkeduo", true) ||
                    it.contains("goods_id", true) || it.contains("goodsId", true) ||
                    it.contains("ps=", true)
            }
            .joinToString("\n")
            .ifBlank { blob.take(120_000) }

        val goodsId = GoodsLinkResolver.extractGoodsId(focused)
            .ifBlank { GoodsLinkResolver.extractGoodsId(blob.take(200_000)) }

        val ps = Regex("""[?&]ps=([A-Za-z0-9_-]{4,})""").find(focused)?.groupValues?.getOrNull(1)
            ?: Regex("""[?&]ps=([A-Za-z0-9_-]{4,})""").find(blob)?.groupValues?.getOrNull(1)
            ?: ""

        val urlFromDump = GoodsLinkResolver.extractGoodsUrls(focused).firstOrNull().orEmpty()
            .ifBlank { GoodsLinkResolver.extractGoodsUrls(blob.take(200_000)).firstOrNull().orEmpty() }

        val shareUrl = when {
            goodsId.isNotBlank() -> GoodsLinkResolver.buildGoodsUrl(goodsId)
            urlFromDump.isNotBlank() -> urlFromDump
            ps.isNotBlank() -> "https://mobile.yangkeduo.com/goods1.html?ps=$ps"
            else -> ""
        }

        return Hit(
            goodsId = goodsId,
            shareUrl = shareUrl,
            rawSnippet = focused.take(300),
        )
    }

    private fun shell(cmd: String): String {
        return try {
            val p = Runtime.getRuntime().exec(arrayOf("sh", "-c", cmd))
            val ok = p.waitFor(4, TimeUnit.SECONDS)
            if (!ok) {
                try {
                    p.destroy()
                } catch (_: Exception) {
                }
                return ""
            }
            BufferedReader(InputStreamReader(p.inputStream)).use { it.readText() }.take(400_000)
        } catch (_: Exception) {
            ""
        }
    }
}
