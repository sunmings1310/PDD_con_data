package com.collector.pdd.net

import android.os.Build
import com.collector.pdd.data.ProductEntity
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.Charset

class ApiClient(private val prefs: ServerPrefs) {

    /** 探测服务是否可达，返回可读结果。 */
    fun pingHealth(): String {
        val url = URL(prefs.baseUrl().trimEnd('/') + "/api/health")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Accept", "application/json")
        }
        return try {
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.use { readAll(it) }.orEmpty()
            conn.disconnect()
            when {
                text.contains("\"ok\"") && text.contains("true") ->
                    "连接成功 ${prefs.baseUrl()}"
                text.contains("<html", ignoreCase = true) || text.contains("oray", ignoreCase = true) ->
                    "连接失败：当前地址打到了花生壳页面，不是采集服务。请把端口留空或改成 80，地址只填域名"
                else -> "连接异常 HTTP $code ${text.take(80)}"
            }
        } catch (e: Exception) {
            "连接失败：${e.message}（地址 ${prefs.baseUrl()}）"
        }
    }

    fun register(): JSONObject {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("device_name", prefs.deviceName)
            .put("platform_code", prefs.platformCode)
            .put("app_version", APP_VERSION)
            .put("os_version", "Android ${Build.VERSION.RELEASE}")
            .put("model", Build.MODEL)
        return postJson("/api/devices/register", body)
    }

    fun heartbeat(status: String, currentTaskId: Long?): JSONObject {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("status", status)
            .put("app_version", APP_VERSION)
        if (currentTaskId != null) body.put("current_task_id", currentTaskId)
        return postJson("/api/devices/heartbeat", body)
    }

    fun pullTask(): JSONObject? {
        val url = "/api/tasks/pull?device_key=${enc(prefs.deviceKey)}&platform_code=${enc(prefs.platformCode)}"
        val res = postJson(url, null)
        if (!res.optBoolean("ok", false)) return null
        val data = res.optJSONObject("data") ?: return null
        return data
    }

    fun progress(
        taskId: Long,
        message: String,
        successDelta: Int = 0,
        failDelta: Int = 0,
        keywordDelta: Int = 0,
        itemId: Long? = null,
        itemStatus: String? = null,
        productId: Long? = null,
    ) {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("task_id", taskId)
            .put("message", message.take(500))
            .put("level", "info")
            .put("success_delta", successDelta)
            .put("fail_delta", failDelta)
            .put("keyword_delta", keywordDelta)
        if (itemId != null) body.put("item_id", itemId)
        if (!itemStatus.isNullOrBlank()) body.put("item_status", itemStatus)
        if (productId != null) body.put("product_id", productId)
        postJson("/api/tasks/progress", body)
    }

    fun finish(taskId: Long, status: String, errorMsg: String? = null) {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("task_id", taskId)
            .put("status", status)
        if (!errorMsg.isNullOrBlank()) body.put("error_msg", errorMsg.take(500))
        postJson("/api/tasks/finish", body)
    }

    fun ackOta(versionName: String) {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("version_name", versionName)
        postJson("/api/ota/ack", body)
    }

    /** 查询服务端最新 APK（无需登录） */
    fun fetchLatestOta(): JSONObject {
        return getJson("/api/ota/latest")
    }

    private fun getJson(path: String): JSONObject {
        val url = URL(prefs.baseUrl().trimEnd('/') + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 12000
            readTimeout = 12000
            setRequestProperty("Accept", "application/json")
        }
        return try {
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.use { readAll(it) }.orEmpty()
            try {
                JSONObject(text.ifBlank { """{"ok":false,"message":"empty"}""" })
            } catch (_: Exception) {
                JSONObject().put("ok", false).put("message", "http $code $text")
            }
        } catch (e: Exception) {
            JSONObject().put("ok", false).put("message", e.message ?: "network error")
        } finally {
            conn.disconnect()
        }
    }

    fun uploadProduct(remoteTaskId: Long?, product: ProductEntity, taskItemId: Long? = null): Long? {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("platform_code", prefs.platformCode)
            .put("keyword", product.keyword)
            .put("item_id", product.itemId)
            .put("sell_name", product.sellName)
            .put("product_name", product.productName)
            .put("brand", product.brand)
            .put("shop_name", product.shopName)
            .put("shop_id", product.shopId)
            .put("spec", product.spec)
            .put("sku_prices_text", product.skuPricesText)
            .put("sku_prices", product.skuPrices)
            .put("dosage_form", product.dosageForm)
            .put("approval_no", product.approvalNo)
            .put("manufacturer", product.manufacturer)
            .put("expiry", product.expiry)
            .put("category", product.category)
            .put("coupon_info", product.couponInfo)
            .put("item_url", product.itemUrl)
            .put("pick_tag", product.pickTag)
            .put("spec_list", product.specList)
            .put("sales_num", product.salesNum)
            .put("shop_sales_num", product.shopSalesNum)
            .put("comment_num", product.commentNum)
        if (remoteTaskId != null) body.put("task_id", remoteTaskId)
        if (taskItemId != null) body.put("task_item_id", taskItemId)
        product.price?.let { body.put("price", it) }
        product.displayPrice?.let { body.put("display_price", it) }
        product.groupPrice?.let { body.put("group_price", it) }
        product.dealPrice?.let { body.put("deal_price", it) }
        product.originalPrice?.let { body.put("original_price", it) }

        val urls = JSONArray()
        val files = mutableListOf<File>()
        product.mainImages.split("|").map { it.trim() }.filter { it.isNotEmpty() }.forEach { p ->
            when {
                p.startsWith("http://") || p.startsWith("https://") -> urls.put(p)
                p.startsWith("file://") -> files.add(File(p.removePrefix("file://")))
                else -> {
                    val f = File(p)
                    if (f.exists()) files.add(f) else if (p.startsWith("/")) files.add(File(p))
                }
            }
        }
        body.put("image_urls", urls)
        val res = postJson("/api/products/upload", body)
        if (!res.optBoolean("ok", false)) return null
        val productId = res.optJSONObject("data")?.optLong("product_id") ?: return null
        if (files.isNotEmpty()) {
            uploadImages(productId, files)
        }
        return productId
    }

    fun uploadTaskAnomaly(
        taskId: Long,
        actionName: String,
        message: String,
        pageText: String,
        consecutiveCount: Int,
        screenshot: File?,
    ) {
        val boundary = "----sjzq-anomaly-${System.currentTimeMillis()}"
        val url = URL("${prefs.baseUrl().trimEnd('/')}/api/tasks/$taskId/anomalies")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 30000
            readTimeout = 120000
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        DataOutputStream(BufferedOutputStream(conn.outputStream)).use { out ->
            fun field(name: String, value: String) {
                out.writeBytes("--$boundary\r\n")
                out.writeBytes("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
                out.write(value.toByteArray(Charsets.UTF_8))
                out.writeBytes("\r\n")
            }
            field("device_key", prefs.deviceKey)
            field("action_name", actionName)
            field("message", message)
            field("page_text", pageText)
            field("consecutive_count", consecutiveCount.toString())
            if (screenshot != null && screenshot.exists() && screenshot.length() > 0) {
                out.writeBytes("--$boundary\r\n")
                out.writeBytes("Content-Disposition: form-data; name=\"screenshot\"; filename=\"${screenshot.name}\"\r\n")
                out.writeBytes("Content-Type: image/jpeg\r\n\r\n")
                FileInputStream(screenshot).use { it.copyTo(out) }
                out.writeBytes("\r\n")
            }
            out.writeBytes("--$boundary--\r\n")
            out.flush()
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val response = stream?.use { readAll(it) }.orEmpty()
        conn.disconnect()
        if (code !in 200..299) error("anomaly upload http $code: $response")
    }

    fun uploadImages(productId: Long, files: List<File>) {
        val boundary = "----sjzq${System.currentTimeMillis()}"
        val url = URL("${prefs.baseUrl()}/api/products/$productId/images")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 30000
            readTimeout = 120000
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        DataOutputStream(BufferedOutputStream(conn.outputStream)).use { out ->
            fun writeField(name: String, value: String) {
                out.writeBytes("--$boundary\r\n")
                out.writeBytes("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
                out.write(value.toByteArray(Charsets.UTF_8))
                out.writeBytes("\r\n")
            }
            writeField("device_key", prefs.deviceKey)
            files.filter { it.exists() && it.length() > 0 }.take(12).forEach { f ->
                out.writeBytes("--$boundary\r\n")
                out.writeBytes(
                    "Content-Disposition: form-data; name=\"files\"; filename=\"${f.name}\"\r\n"
                )
                out.writeBytes("Content-Type: image/jpeg\r\n\r\n")
                FileInputStream(f).use { it.copyTo(out) }
                out.writeBytes("\r\n")
            }
            out.writeBytes("--$boundary--\r\n")
            out.flush()
        }
        conn.inputStream.use { it.readBytes() }
        conn.disconnect()
    }

    private fun postJson(path: String, body: JSONObject?): JSONObject {
        val url = URL(prefs.baseUrl().trimEnd('/') + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doInput = true
            connectTimeout = 15000
            readTimeout = 30000
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        if (body != null) {
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.use { readAll(it) }.orEmpty()
        conn.disconnect()
        return try {
            JSONObject(text.ifBlank { """{"ok":false,"message":"empty"}""" })
        } catch (_: Exception) {
            JSONObject().put("ok", false).put("message", "http $code $text")
        }
    }

    private fun readAll(input: java.io.InputStream): String {
        val bos = ByteArrayOutputStream()
        input.copyTo(bos)
        return bos.toString(Charset.forName("UTF-8").name())
    }

    private fun enc(s: String): String = java.net.URLEncoder.encode(s, "UTF-8")

    companion object {
        /** 必须跟 build.gradle versionName 一致，勿再手写死版本号 */
        val APP_VERSION: String = com.collector.pdd.BuildConfig.VERSION_NAME
    }
}
