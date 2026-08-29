package com.collector.pdd.net

import android.os.Build
import com.collector.pdd.data.ProductEntity
import com.collector.pdd.data.OutboxEntity
import com.collector.pdd.data.OutboxPayload
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
import java.util.UUID

class PermanentUploadException(message: String) : IllegalStateException(message)

class ApiClient(private val prefs: ServerPrefs) {

    fun acquireJob(workerId: String, leaseSeconds: Int = 120): JobLeaseIdentity? {
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("worker_id", workerId)
            .put("platform_code", prefs.platformCode)
            .put("lease_seconds", leaseSeconds)
        val response = try {
            postJsonChecked("/api/jobs/acquire", body)
        } catch (e: IllegalStateException) {
            // Compatibility is intentionally limited to a missing endpoint. A
            // timeout/5xx must not silently switch protocols and pull another task.
            if (e.message?.contains("http 404") == true || e.message?.contains("http 405") == true) {
                throw JobProtocolUnavailableException(e.message.orEmpty())
            }
            throw e
        }
        requireJobOk(response, "acquire")
        return response.optJSONObject("data")?.toJobLease(workerId)
    }

    fun recoverJobs(workerId: String): List<JSONObject> {
        val body = JSONObject().put("device_key", prefs.deviceKey).put("worker_id", workerId)
        val response = postJsonChecked("/api/jobs/recover", body)
        requireJobOk(response, "recover")
        val data = response.optJSONArray("data") ?: return emptyList()
        return buildList { for (i in 0 until data.length()) data.optJSONObject(i)?.let(::add) }
    }

    fun startJob(identity: JobLeaseIdentity): JSONObject = jobCall("start", identityBody(identity))

    fun heartbeatJob(identity: JobLeaseIdentity, leaseSeconds: Int = 120): JSONObject {
        val body = identityBody(identity).put("lease_seconds", leaseSeconds)
        return jobCall("heartbeat", body)
    }

    fun yieldJob(identity: JobLeaseIdentity): JSONObject = jobCall("yield", identityBody(identity))

    fun checkpointJob(identity: JobLeaseIdentity, version: Int, idempotencyKey: String, payload: JSONObject): JSONObject {
        val body = identityBody(identity)
            .put("version", version)
            .put("idempotency_key", idempotencyKey)
            .put("payload", payload)
        return jobCall("checkpoint", body)
    }

    fun completeJob(identity: JobLeaseIdentity, resultReceiptKeys: List<String>, resultProductId: Long? = null): JSONObject {
        require(resultReceiptKeys.isNotEmpty()) { "confirmed product receipt manifest is required" }
        val keys = resultReceiptKeys.distinct()
        val body = identityBody(identity)
            .put("result_receipt_key", keys.first())
            .put("result_receipt_keys", JSONArray(keys))
        resultProductId?.let { body.put("result_product_id", it) }
        return jobCall("complete", body)
    }

    fun completeJob(identity: JobLeaseIdentity, resultReceiptKey: String, resultProductId: Long? = null): JSONObject =
        completeJob(identity, listOf(resultReceiptKey), resultProductId)

    fun failJob(identity: JobLeaseIdentity, errorClass: String, errorCode: String, errorMessage: String = ""): JSONObject {
        val body = identityBody(identity)
            .put("error_class", errorClass)
            .put("error_code", errorCode)
            .put("error_message", errorMessage.take(2000))
        return jobCall("fail", body)
    }

    private fun identityBody(identity: JobLeaseIdentity): JSONObject = JSONObject()
        .put("device_key", prefs.deviceKey)
        .put("worker_id", identity.workerId)
        .put("job_id", identity.jobId)
        .put("attempt_id", identity.attemptId)
        .put("lease_token", identity.leaseToken)

    private fun jobCall(operation: String, body: JSONObject): JSONObject {
        val response = postJsonChecked("/api/jobs/$operation", body)
        requireJobOk(response, operation)
        return response.optJSONObject("data") ?: JSONObject()
    }

    private fun requireJobOk(response: JSONObject, operation: String) {
        if (response.optBoolean("ok", false)) return
        val data = response.optJSONObject("data")
        throw JobProtocolException(
            errorCode = data?.optString("error_code").orEmpty().ifBlank { "JOB_${operation}_FAILED" },
            message = "$operation rejected: ${response.optString("message", "unknown")}",
            currentStatus = data?.optString("current_status")?.ifBlank { null },
        )
    }

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
        if (prefs.enrollmentToken.isNotBlank()) body.put("enrollment_token", prefs.enrollmentToken)
        return postJson("/api/devices/register", body).also {
            if (it.optBoolean("ok", false)) prefs.enrollmentToken = ""
        }
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
        if (successDelta != 0 || failDelta != 0 || keywordDelta != 0) {
            body.put("progress_id", UUID.randomUUID().toString())
        }
        if (itemId != null) body.put("item_id", itemId)
        if (!itemStatus.isNullOrBlank()) body.put("item_status", itemStatus)
        if (productId != null) body.put("product_id", productId)
        postJson("/api/tasks/progress", body)
    }

    fun finish(taskId: Long, status: String, errorMsg: String? = null): JSONObject {
        require(status in setOf("complete", "failed", "cancelled", "timed_out")) {
            "unknown server task completion status: $status"
        }
        val body = JSONObject()
            .put("device_key", prefs.deviceKey)
            .put("task_id", taskId)
            .put("status", status)
        if (!errorMsg.isNullOrBlank()) body.put("error_msg", errorMsg.take(500))
        return postJsonChecked("/api/tasks/finish", body)
    }

    /** Deliver one durable product event. The outbox id is the protocol idempotency key. */
    fun uploadProductEvent(event: OutboxEntity): Long {
        require(event.eventType == "product")
        val payload = JSONObject(event.payloadJson)
        val localPaths = payload.optJSONArray("local_image_paths") ?: JSONArray()
        payload.remove("local_image_paths")
        payload.remove("local_image_count")
        payload.put("device_key", prefs.deviceKey)
            .put("task_id", event.remoteTaskId)
            .put("idempotency_key", event.outboxId)
        event.taskItemId?.let { payload.put("task_item_id", it) }
        event.jobId?.let { payload.put("job_id", it) }
        event.attemptId?.let { payload.put("attempt_id", it) }
        event.leaseToken?.let { payload.put("lease_token", it) }
        event.workerId?.let { payload.put("worker_id", it) }
        event.traceId?.let { payload.put("trace_id", it) }

        val response = postJsonChecked("/api/products/upload", payload)
        val data = requireAck(response, "product")
        check(data.optBoolean("persisted", false)) { "product acknowledgement is not persisted" }
        val productId = data.optLong("product_id", 0L)
        check(productId > 0L) { "product acknowledgement has no product_id" }

        val files = buildList {
            for (i in 0 until localPaths.length()) {
                val file = File(localPaths.optString(i))
                if (file.exists() && file.length() > 0) add(file)
            }
        }
        check(files.size == event.requiredImageCount) {
            "required local images missing expected=${event.requiredImageCount} actual=${files.size}"
        }
        if (files.isNotEmpty()) {
            uploadImages(
                productId,
                files,
                "${event.outboxId}:images",
                event.jobId,
                event.attemptId,
                event.workerId,
                event.leaseToken,
            )
        }
        return productId
    }

    /** Finish is accepted only after the server confirms its receipt and final state. */
    fun finishEvent(event: OutboxEntity, forcedStatus: String? = null): String {
        require(event.eventType == "finish")
        val payload = JSONObject(event.payloadJson)
            .put("device_key", prefs.deviceKey)
            .put("task_id", event.remoteTaskId)
            .put("finish_id", event.outboxId)
        if (!forcedStatus.isNullOrBlank()) payload.put("status", forcedStatus)
        val data = requireAck(postJsonChecked("/api/tasks/finish", payload), "finish")
        return data.optString("status").also { check(it.isNotBlank()) { "finish acknowledgement has no status" } }
    }

    /** 查询服务端最新 APK（无需登录） */
    fun fetchLatestOta(): JSONObject {
        return getJson("/api/ota/latest?device_key=${enc(prefs.deviceKey)}")
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

    @Deprecated("Phase 1 remote tasks must use persistent outbox uploadProductEvent")
    fun uploadProduct(remoteTaskId: Long?, product: ProductEntity, taskItemId: Long? = null): Long? {
        // Legacy synchronous delivery delegates to the same authoritative field
        // mapper as durable outbox delivery.  Only transport metadata is added here.
        val body = OutboxPayload.product(product, prefs.platformCode)
            .put("device_key", prefs.deviceKey)
        if (remoteTaskId != null) body.put("task_id", remoteTaskId)
        if (taskItemId != null) body.put("task_item_id", taskItemId)

        val files = mutableListOf<File>()
        product.mainImages.split("|").map { it.trim() }.filter { it.isNotEmpty() }.forEach { p ->
            when {
                p.startsWith("http://") || p.startsWith("https://") -> Unit
                p.startsWith("file://") -> files.add(File(p.removePrefix("file://")))
                else -> {
                    val f = File(p)
                    if (f.exists()) files.add(f) else if (p.startsWith("/")) files.add(File(p))
                }
            }
        }
        body.remove("local_image_paths")
        body.remove("local_image_count")
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

    fun uploadImages(
        productId: Long,
        files: List<File>,
        idempotencyKey: String? = null,
        jobId: Long? = null,
        attemptId: Long? = null,
        workerId: String? = null,
        leaseToken: String? = null,
    ) {
        val uploadFiles = files.filter { it.exists() && it.length() > 0 }
        require(uploadFiles.size == files.size) { "image upload contains missing or empty files" }
        require(uploadFiles.size <= 12) { "image upload supports at most 12 files per receipt" }
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
            if (!idempotencyKey.isNullOrBlank()) writeField("idempotency_key", idempotencyKey)
            jobId?.let { writeField("job_id", it.toString()) }
            attemptId?.let { writeField("attempt_id", it.toString()) }
            workerId?.let { writeField("worker_id", it) }
            leaseToken?.let { writeField("lease_token", it) }
            uploadFiles.forEach { f ->
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
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = stream?.use { readAll(it) }.orEmpty()
        conn.disconnect()
        check(code in 200..299) { "image upload http $code: $responseText" }
        val response = runCatching { JSONObject(responseText) }
            .getOrElse { error("image upload invalid response: $responseText") }
        val data = requireAck(response, "images")
        val processed = (data.optJSONArray("images")?.length() ?: 0) +
            (data.optJSONArray("skipped_license")?.length() ?: 0)
        check(processed == uploadFiles.size) {
            "image acknowledgement mismatch expected=${uploadFiles.size} processed=$processed"
        }
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

    private fun postJsonChecked(path: String, body: JSONObject): JSONObject {
        val url = URL(prefs.baseUrl().trimEnd('/') + path)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doInput = true
            doOutput = true
            connectTimeout = 15000
            readTimeout = 120000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        return try {
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val responseText = stream?.use { readAll(it) }.orEmpty()
            check(code in 200..299) { "http $code: $responseText" }
            runCatching { JSONObject(responseText) }
                .getOrElse { error("invalid JSON response: $responseText") }
        } finally {
            conn.disconnect()
        }
    }

    private fun requireAck(response: JSONObject, operation: String): JSONObject {
        if (!response.optBoolean("ok", false)) {
            val code = response.optJSONObject("data")?.optString("error_code").orEmpty()
            val message = "$operation rejected${if (code.isBlank()) "" else " [$code]"}: ${response.optString("message", "unknown")}"
            if (code in setOf(
                    "STALE_LEASE", "LEASE_EXPIRED", "LEASE_REQUIRED", "LEASE_IDENTITY_REQUIRED",
                    "JOB_NOT_FOUND", "ATTEMPT_NOT_FOUND", "LEASE_TOKEN_MISMATCH",
                )
            ) throw JobProtocolException(code, message)
            if (code in setOf(
                    "QUALITY_REJECTED", "QUALITY_VERSION_REQUIRED", "FIELD_SOURCES_REQUIRED",
                    "IDEMPOTENCY_CONFLICT", "DEVICE_MISMATCH",
                    "TASK_NOT_FOUND", "TASK_NOT_RUNNING", "TASK_DEVICE_MISMATCH",
                    "TASK_ITEM_NOT_FOUND", "TASK_ITEM_TERMINAL", "ILLEGAL_TASK_ITEM_TRANSITION",
                )
            ) throw PermanentUploadException(message)
            error(message)
        }
        val data = response.optJSONObject("data") ?: error("$operation response has no data")
        check(data.optBoolean("acknowledged", false)) { "$operation response is not acknowledged" }
        return data
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
