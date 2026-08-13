package com.collector.pdd.engine

import com.collector.pdd.data.CollectConfig
import kotlinx.coroutines.delay
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

/**
 * 拟人节奏：Beta 分布停顿、偶发走神/长停，对齐桌面 human_behavior.py。
 */
object HumanBehavior {

    data class Profile(
        val delayMin: Double,
        val delayMax: Double,
        val longPauseP: Double,
        val idleP: Double,
        val backscrollP: Double,
        val thinkMin: Double,
        val thinkMax: Double,
        val readMin: Double,
        val readMax: Double,
        val keywordGapMin: Double,
        val keywordGapMax: Double,
        val itemGapMin: Double,
        val itemGapMax: Double,
    )

    fun profile(config: CollectConfig): Profile {
        val level = config.humanLevel.lowercase()
        // 等待区间以 Web 下发为准，不再整体放大超出区间；强度只影响停顿/回滑概率
        val baseMin = config.delayMinMs.toDouble()
        val baseMax = max(baseMin, config.delayMaxMs.toDouble())
        val presets = mapOf(
            "gentle" to doubleArrayOf(0.08, 0.05, 0.10),
            "normal" to doubleArrayOf(0.15, 0.10, 0.18),
            "strict" to doubleArrayOf(0.25, 0.18, 0.28),
        )
        val p = presets[level] ?: presets.getValue("strict")
        return Profile(
            delayMin = baseMin,
            delayMax = baseMax,
            longPauseP = p[0],
            idleP = p[1],
            backscrollP = p[2],
            thinkMin = config.thinkMinMs.toDouble(),
            thinkMax = config.thinkMaxMs.toDouble(),
            readMin = config.readMinMs.toDouble(),
            readMax = config.readMaxMs.toDouble(),
            keywordGapMin = config.keywordGapMinMs.toDouble(),
            keywordGapMax = config.keywordGapMaxMs.toDouble(),
            itemGapMin = config.itemGapMinMs.toDouble(),
            itemGapMax = config.itemGapMaxMs.toDouble(),
        )
    }

    /** 非均匀随机停留（ms）。bias=short|long */
    suspend fun sleepMs(lowMs: Double, highMs: Double, bias: String = "short"): Long {
        val low = max(50.0, lowMs)
        val high = max(low, highMs)
        val span = high - low
        val r = if (bias == "long") beta(2.2, 1.6) else beta(1.4, 2.8)
        var ms = low + span * r
        if (Random.nextDouble() < 0.08) {
            ms *= Random.nextDouble(1.6, 2.8)
        }
        val wait = ms.toLong().coerceAtLeast(50L)
        delay(wait)
        return wait
    }

    /**
     * kind: think/action/read/idle/keyword/item
     */
    suspend fun pause(config: CollectConfig, kind: String = "action"): Long {
        val p = profile(config)
        var low: Double
        var high: Double
        var bias: String
        when (kind) {
            "think" -> {
                low = p.thinkMin; high = p.thinkMax; bias = "short"
            }
            "read" -> {
                low = p.readMin; high = p.readMax; bias = "long"
            }
            "idle" -> {
                // 走神也落在配置区间偏长一侧
                low = (p.delayMin + p.delayMax) / 2.0
                high = p.delayMax
                bias = "long"
            }
            "keyword" -> {
                low = p.keywordGapMin; high = p.keywordGapMax; bias = "long"
            }
            "item" -> {
                low = p.itemGapMin; high = p.itemGapMax; bias = "long"
            }
            else -> {
                low = p.delayMin; high = p.delayMax; bias = "short"
            }
        }
        // 偶发走神：仍夹在配置区间内，最多摸到上限
        if (kind in listOf("action", "item", "read") && Random.nextDouble() < p.idleP) {
            low = (p.delayMin + p.delayMax) / 2.0
            high = p.delayMax
            bias = "long"
        }
        // 强制落在 Web 配置的等待区间内（action/item）
        if (kind == "action" || kind == "item") {
            low = max(low, p.delayMin)
            high = min(high, p.delayMax)
            if (high < low) high = low
        }
        return sleepMs(low, high, bias)
    }

    fun shouldBackscroll(config: CollectConfig): Boolean =
        Random.nextDouble() < profile(config).backscrollP

    fun shouldLongPause(config: CollectConfig): Boolean =
        Random.nextDouble() < profile(config).longPauseP

    /** 触摸坐标抖动 */
    fun jitter(base: Float, span: Float): Float =
        base + Random.nextDouble(-span.toDouble(), span.toDouble()).toFloat()

    fun swipeDurationMs(purpose: String = "list"): Long {
        val (lo, hi) = if (purpose == "detail") 280L to 620L else 320L to 720L
        return Random.nextLong(lo, hi + 1)
    }

    fun detailScrollRounds(): Int = Random.nextInt(3, 7)

    fun listScrollRounds(base: Int = 2): Int =
        max(1, (base * Random.nextDouble(0.7, 1.3)).toInt())

    private fun beta(a: Double, b: Double): Double {
        // 简单近似：用两个 Gamma 构造 Beta；Gamma 用 Marsaglia 简化版
        val x = gammaSample(a)
        val y = gammaSample(b)
        val s = x + y
        return if (s <= 0) 0.5 else min(0.999, max(0.001, x / s))
    }

    private fun nextGaussian(): Double {
        // Box-Muller
        val u1 = Random.nextDouble().coerceAtLeast(1e-12)
        val u2 = Random.nextDouble()
        return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2)
    }

    private fun gammaSample(shape: Double): Double {
        if (shape < 1.0) {
            return gammaSample(shape + 1.0) * Math.pow(Random.nextDouble(), 1.0 / shape)
        }
        val d = shape - 1.0 / 3.0
        val c = 1.0 / Math.sqrt(9.0 * d)
        while (true) {
            var x: Double
            var v: Double
            do {
                x = nextGaussian()
                v = 1.0 + c * x
            } while (v <= 0)
            v = v * v * v
            val u = Random.nextDouble()
            if (u < 1.0 - 0.0331 * (x * x) * (x * x)) return d * v
            if (Math.log(u) < 0.5 * x * x + d * (1.0 - v + Math.log(v))) return d * v
        }
    }
}
