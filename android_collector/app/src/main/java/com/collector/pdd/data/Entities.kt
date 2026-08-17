package com.collector.pdd.data

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "task_log")
data class TaskEntity(
    @PrimaryKey(autoGenerate = true) val taskId: Long = 0,
    val taskName: String = "",
    val startTime: String = "",
    val endTime: String = "",
    val keywordList: String = "",
    val totalCount: Int = 0,
    val successCount: Int = 0,
    val failCount: Int = 0,
    val status: String = "running",
    val remoteTaskId: Long? = null,
)

@Entity(tableName = "product_table")
data class ProductEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val taskId: Long = 0,
    val keyword: String = "",
    val itemId: String = "",
    val sellName: String = "",
    val productName: String = "",
    val brand: String = "",
    val shopName: String = "",
    val shopId: String = "",
    val price: Double? = null,
    val displayPrice: Double? = null,
    val groupPrice: Double? = null,
    val dealPrice: Double? = null,
    val originalPrice: Double? = null,
    val salesNum: Int? = null,
    val shopSalesNum: Int? = null,
    val commentNum: Int = 0,
    val spec: String = "",
    val skuPricesText: String = "",
    val skuPrices: String = "",
    val dosageForm: String = "",
    val approvalNo: String = "",
    val manufacturer: String = "",
    val expiry: String = "",
    val category: String = "",
    val couponInfo: String = "",
    val mainImages: String = "",
    val itemUrl: String = "",
    val pickTag: String = "",
    val specList: String = "",
    val updateTime: String = "",
    val parseStatus: String = "success",
    val pageStatus: String = "product",
    val qualityStatus: String = "passed",
    val fieldSources: String = "{}",
    val parserVersion: String = "pdd-android-1",
    val qualityRulesVersion: String = "phase3-1",
)

@Entity(tableName = "upload_outbox", indices = [Index(value = ["state", "nextAttemptAt"]), Index(value = ["jobId", "attemptId"])])
data class OutboxEntity(
    @PrimaryKey val outboxId: String,
    val eventType: String,
    val remoteTaskId: Long,
    val taskItemId: Long? = null,
    val payloadJson: String,
    val requiredImageCount: Int = 0,
    val state: String = "pending",
    val attemptCount: Int = 0,
    val nextAttemptAt: Long = 0,
    val lastError: String = "",
    val serverProductId: Long? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val ackedAt: Long? = null,
    /** Phase 2 authoritative Job/Attempt/Lease identity. Null is retained for legacy Phase 1 rows. */
    val jobId: Long? = null,
    val attemptId: Long? = null,
    val leaseToken: String? = null,
    val workerId: String? = null,
    val traceId: String? = null,
    val checkpointVersion: Int = 0,
)

@Entity(
    tableName = "job_assignment",
    indices = [Index(value = ["taskId"]), Index(value = ["state"]), Index(value = ["leaseExpiresAt"])],
)
data class JobAssignmentEntity(
    @PrimaryKey val jobId: Long,
    val taskId: Long,
    val jobKey: String,
    val jobType: String,
    val payloadJson: String,
    val attemptId: Long,
    val attemptNo: Int,
    val leaseToken: String,
    val workerId: String,
    val traceId: String,
    val checkpointVersion: Int = 0,
    val leaseExpiresAt: Long,
    val state: String = "leased",
    val updatedAt: Long = System.currentTimeMillis(),
)
