package com.collector.pdd.export

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import com.collector.pdd.data.ProductEntity
import org.json.JSONObject
import java.io.File
import java.nio.charset.Charset
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

object CsvExporter {

    private val columns = listOf(
        "任务ID" to { p: ProductEntity -> p.taskId.toString() },
        "关键词" to { p -> p.keyword },
        "商品ID" to { p -> p.itemId },
        "售卖名称" to { p -> p.sellName },
        "商品名称" to { p -> p.productName },
        "品牌" to { p -> p.brand },
        "店铺名称" to { p -> p.shopName },
        "店铺ID" to { p -> p.shopId },
        "列表价" to { p -> p.price?.toString().orEmpty() },
        "详情展示价" to { p -> p.displayPrice?.toString().orEmpty() },
        "拼单价" to { p -> p.groupPrice?.toString().orEmpty() },
        "单独购买价" to { p -> p.dealPrice?.toString().orEmpty() },
        "原价" to { p -> p.originalPrice?.toString().orEmpty() },
        "销量" to { p -> p.salesNum?.toString().orEmpty() },
        "店铺销量" to { p -> p.shopSalesNum?.toString().orEmpty() },
        "评价数" to { p ->
            val source = runCatching { JSONObject(p.fieldSources).optString("comment_num") }.getOrDefault("")
            if (source == "none") "" else p.commentNum.toString()
        },
        "规格" to { p -> p.spec },
        "多规格价格" to { p -> p.skuPricesText },
        "多规格价格JSON" to { p -> p.skuPrices },
        "剂型" to { p -> p.dosageForm },
        "国药准字" to { p -> p.approvalNo },
        "生产厂家" to { p -> p.manufacturer },
        "有效期" to { p -> p.expiry },
        "类目" to { p -> p.category },
        "优惠信息" to { p -> p.couponInfo },
        "图片" to { p -> p.mainImages },
        "链接" to { p -> p.itemUrl },
        "采集规则" to { p -> p.pickTag },
        "属性明细" to { p -> p.specList },
        "采集时间" to { p -> p.updateTime },
    )

    fun export(context: Context, taskId: Long, rows: List<ProductEntity>): File {
        val stamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"))
        val dir = File(context.getExternalFilesDir(null), "exports").apply { mkdirs() }
        val file = File(dir, "task_${taskId}_$stamp.csv")
        val sb = StringBuilder()
        // UTF-8 BOM for Excel
        sb.append('\uFEFF')
        sb.append(columns.joinToString(",") { it.first }).append('\n')
        for (p in rows) {
            sb.append(columns.joinToString(",") { csvEscape(it.second(p)) }).append('\n')
        }
        file.writeText(sb.toString(), Charset.forName("UTF-8"))
        return file
    }

    fun share(context: Context, file: File) {
        val uri = FileProvider.getUriForFile(
            context,
            context.packageName + ".fileprovider",
            file,
        )
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/csv"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(intent, "导出采集结果"))
    }

    private fun csvEscape(raw: String): String {
        val v = raw.replace("\"", "\"\"")
        return if (v.contains(',') || v.contains('"') || v.contains('\n')) "\"$v\"" else v
    }
}
