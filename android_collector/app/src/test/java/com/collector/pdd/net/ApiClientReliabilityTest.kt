package com.collector.pdd.net

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.collector.pdd.data.OutboxEntity
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ApiClientReliabilityTest {
    private lateinit var server: MockWebServer
    private lateinit var client: ApiClient
    private lateinit var prefs: ServerPrefs

    @Before fun setUp() {
        server = MockWebServer()
        server.start()
        val context = ApplicationProvider.getApplicationContext<Context>()
        prefs = ServerPrefs(context).apply {
            host = server.url("/").toString().trimEnd('/')
            port = 0
            platformCode = "pinduoduo"
        }
        client = ApiClient(prefs)
    }

    @Test fun pulledAssignmentIsSynchronouslyDurableUntilExplicitlyCleared() {
        val payload = """{"task_id":77,"keywords":["fixture"]}"""
        prefs.savePendingTask(payload)
        val reopened = ServerPrefs(ApplicationProvider.getApplicationContext())
        assertEquals(payload, reopened.pendingTaskJson())
        reopened.clearPendingTask()
        assertEquals(null, prefs.pendingTaskJson())
    }

    @After fun tearDown() {
        server.shutdown()
    }

    private fun productEvent(localPaths: JSONArray = JSONArray()) = OutboxEntity(
        outboxId = "product-task-1-abcdef",
        eventType = "product",
        remoteTaskId = 1,
        payloadJson = JSONObject()
            .put("local_image_paths", localPaths)
            .put("local_image_count", localPaths.length())
            .put("item_id", "123")
            .toString(),
        requiredImageCount = localPaths.length(),
    )

    private fun json(code: Int = 200, body: String) = MockResponse()
        .setResponseCode(code)
        .setHeader("Content-Type", "application/json")
        .setBody(body)

    @Test fun productRequiresPersistedAcknowledgementAndUsesStableKey() {
        server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"persisted":true,"product_id":88}}"""))
        assertEquals(88L, client.uploadProductEvent(productEvent()))
        val request = server.takeRequest()
        assertEquals("/api/products/upload", request.path)
        val sent = JSONObject(request.body.readUtf8())
        assertEquals("product-task-1-abcdef", sent.getString("idempotency_key"))
        assertEquals(1L, sent.getLong("task_id"))
    }

    @Test fun http5xxInvalidJsonAndMissingAckAreNeverSuccess() {
        // A refused connection is deterministic. DISCONNECT_AT_START may be retried
        // transparently by HttpURLConnection and consume the next queued response.
        server.shutdown()
        assertThrows(Exception::class.java) { client.uploadProductEvent(productEvent()) }
        server = MockWebServer().also { it.start() }
        prefs.host = server.url("/").toString().trimEnd('/')

        server.enqueue(json(503, """{"ok":false,"message":"busy"}"""))
        assertThrows(IllegalStateException::class.java) { client.uploadProductEvent(productEvent()) }

        server.enqueue(json(body = "not-json"))
        assertThrows(IllegalStateException::class.java) { client.uploadProductEvent(productEvent()) }

        server.enqueue(json(body = """{"ok":true,"data":{"persisted":true,"product_id":88}}"""))
        assertThrows(IllegalStateException::class.java) { client.uploadProductEvent(productEvent()) }
    }

    @Test fun repeatedDeliveryReusesThePersistedIdempotencyKey() {
        repeat(2) {
            server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"persisted":true,"product_id":88}}"""))
        }
        val event = productEvent()
        assertEquals(88L, client.uploadProductEvent(event))
        assertEquals(88L, client.uploadProductEvent(event))
        val first = JSONObject(server.takeRequest().body.readUtf8())
        val second = JSONObject(server.takeRequest().body.readUtf8())
        assertEquals(event.outboxId, first.getString("idempotency_key"))
        assertEquals(first.getString("idempotency_key"), second.getString("idempotency_key"))
    }

    @Test fun candidateObservationRequiresRawAcknowledgementAndLeaseIdentity() {
        val event = OutboxEntity(
            outboxId = "candidate-12-13-1", eventType = "candidate_observation", remoteTaskId = 10,
            taskItemId = 11, jobId = 12, attemptId = 13, workerId = "worker",
            leaseToken = "x".repeat(32), payloadJson = """{"candidate_present":true,"matched":false,"reason_code":"candidate_rejected","candidate_ordinal":1,"expected_fields":{},"observed_fields":{},"field_differences":{},"source_summary":[],"collected_at_epoch_ms":1700000000000,"collector_version":"test","parser_version":"test"}""",
        )
        server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"persisted":true,"raw_id":77}}"""))
        assertEquals(77L, client.uploadCandidateObservationEvent(event))
        val request = server.takeRequest()
        assertEquals("/api/candidate-observations", request.path)
        val sent = JSONObject(request.body.readUtf8())
        assertEquals(event.outboxId, sent.getString("idempotency_key"))
        assertEquals(12L, sent.getLong("job_id")); assertEquals(13L, sent.getLong("attempt_id"))
        server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"persisted":true}}"""))
        assertThrows(IllegalStateException::class.java) { client.uploadCandidateObservationEvent(event) }
    }

    @Test fun qualityAndIdempotencyConflictsArePermanentFailures() {
        for (code in listOf("QUALITY_REJECTED", "IDEMPOTENCY_CONFLICT", "TASK_NOT_RUNNING", "OBSERVATION_LIMIT_REACHED")) {
            server.enqueue(json(body = """{"ok":false,"message":"rejected","data":{"error_code":"$code"}}"""))
            assertThrows(PermanentUploadException::class.java) { client.uploadProductEvent(productEvent()) }
        }
    }

    @Test fun imageFailurePreventsProductEventAcknowledgement() {
        val image = kotlin.io.path.createTempFile("phase1-image", ".jpg").toFile().apply {
            writeBytes(byteArrayOf(1, 2, 3, 4))
            deleteOnExit()
        }
        server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"persisted":true,"product_id":88}}"""))
        server.enqueue(json(500, """{"ok":false,"message":"image failed"}"""))
        assertThrows(IllegalStateException::class.java) {
            client.uploadProductEvent(productEvent(JSONArray().put(image.absolutePath)))
        }
        server.takeRequest() // product
        assertEquals("/api/products/88/images", server.takeRequest().path)
    }

    @Test fun imageUploadRejectsMoreThanReceiptLimitBeforeNetworkIo() {
        val image = kotlin.io.path.createTempFile("phase1-image-limit", ".jpg").toFile().apply {
            writeBytes(byteArrayOf(1))
            deleteOnExit()
        }
        assertThrows(IllegalArgumentException::class.java) {
            client.uploadImages(88, List(13) { image }, "image-limit")
        }
        assertEquals(0, server.requestCount)
    }

    @Test fun finishRequiresAcknowledgedFinalStatusAndPreservesFinishKey() {
        val event = OutboxEntity(
            outboxId = "finish-task-1",
            eventType = "finish",
            remoteTaskId = 1,
            payloadJson = """{"status":"complete","expected_product_count":1,"expected_image_count":0}""",
        )
        server.enqueue(json(body = """{"ok":true,"data":{"acknowledged":true,"status":"succeeded"}}"""))
        assertEquals("succeeded", client.finishEvent(event))
        val sent = JSONObject(server.takeRequest().body.readUtf8())
        assertEquals("finish-task-1", sent.getString("finish_id"))

        server.enqueue(json(body = """{"ok":true,"data":{"status":"succeeded"}}"""))
        assertThrows(IllegalStateException::class.java) { client.finishEvent(event) }
        assertTrue(server.requestCount >= 2)
    }
}
