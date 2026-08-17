package com.collector.pdd.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import androidx.room.Transaction

@Dao
interface TaskDao {
    @Insert
    suspend fun insert(task: TaskEntity): Long

    @Update
    suspend fun update(task: TaskEntity)

    @Query("SELECT * FROM task_log WHERE taskId = :id LIMIT 1")
    suspend fun get(id: Long): TaskEntity?

    @Query("SELECT * FROM task_log ORDER BY taskId DESC LIMIT :limit")
    suspend fun list(limit: Int = 50): List<TaskEntity>

    @Query("SELECT * FROM task_log WHERE remoteTaskId IS NOT NULL")
    suspend fun listRemotePending(): List<TaskEntity>

    @Query("UPDATE task_log SET remoteTaskId=NULL WHERE remoteTaskId=:remoteTaskId")
    suspend fun clearRemoteTask(remoteTaskId: Long)

    @Query("UPDATE task_log SET status='failed' WHERE remoteTaskId=:remoteTaskId")
    suspend fun markRemoteFailed(remoteTaskId: Long)
}

@Dao
interface ProductDao {
    @Insert
    suspend fun insert(product: ProductEntity): Long

    @Query("SELECT * FROM product_table WHERE taskId = :taskId ORDER BY id ASC")
    suspend fun listByTask(taskId: Long): List<ProductEntity>

    @Query("SELECT COUNT(*) FROM product_table WHERE taskId = :taskId")
    suspend fun countByTask(taskId: Long): Int
}

@Dao
interface OutboxDao {
    @Insert
    suspend fun insert(event: OutboxEntity)

    @Insert
    suspend fun insertProduct(product: ProductEntity): Long

    @Transaction
    suspend fun insertProductAndOutbox(product: ProductEntity, event: OutboxEntity): Long {
        val localId = insertProduct(product)
        insert(event)
        return localId
    }

    @Query(
        "SELECT * FROM upload_outbox WHERE state IN ('pending','retry') " +
            "AND nextAttemptAt <= :now ORDER BY createdAt ASC LIMIT :limit"
    )
    suspend fun ready(now: Long, limit: Int = 50): List<OutboxEntity>

    @Query("SELECT * FROM upload_outbox WHERE outboxId = :id LIMIT 1")
    suspend fun get(id: String): OutboxEntity?

    @Query("UPDATE upload_outbox SET state='in_flight' WHERE outboxId=:id AND state IN ('pending','retry')")
    suspend fun markInFlight(id: String): Int

    @Query(
        "UPDATE upload_outbox SET state='acked', serverProductId=:serverProductId, " +
            "ackedAt=:ackedAt, lastError='' WHERE outboxId=:id"
    )
    suspend fun markAcked(id: String, serverProductId: Long?, ackedAt: Long)

    @Query(
        "UPDATE upload_outbox SET state='retry', attemptCount=attemptCount+1, " +
            "nextAttemptAt=:nextAttemptAt, lastError=:error WHERE outboxId=:id"
    )
    suspend fun markRetry(id: String, nextAttemptAt: Long, error: String)

    @Query("UPDATE upload_outbox SET state='rejected', attemptCount=attemptCount+1, lastError=:error WHERE outboxId=:id")
    suspend fun markRejected(id: String, error: String)

    @Query("UPDATE upload_outbox SET state='retry' WHERE state='in_flight'")
    suspend fun resetInFlight(): Int

    @Query("SELECT COUNT(*) FROM upload_outbox WHERE remoteTaskId=:taskId AND state NOT IN ('acked','rejected')")
    suspend fun unackedCount(taskId: Long): Int

    @Query("SELECT COUNT(*) FROM upload_outbox WHERE remoteTaskId=:taskId AND eventType='product'")
    suspend fun productEventCount(taskId: Long): Int

    @Query(
        "SELECT COALESCE(SUM(CASE WHEN requiredImageCount > 0 THEN 1 ELSE 0 END), 0) " +
            "FROM upload_outbox WHERE remoteTaskId=:taskId AND eventType='product'"
    )
    suspend fun imageEventCount(taskId: Long): Int

    @Query(
        "SELECT * FROM upload_outbox WHERE remoteTaskId=:taskId AND eventType='product' " +
        "AND state NOT IN ('acked','rejected') ORDER BY createdAt ASC"
    )
    suspend fun unackedProducts(taskId: Long): List<OutboxEntity>

    @Query("SELECT COUNT(*) FROM upload_outbox WHERE remoteTaskId=:taskId AND eventType='product' AND state='rejected'")
    suspend fun rejectedProductCount(taskId: Long): Int

    @Query("SELECT * FROM upload_outbox WHERE state NOT IN ('acked','rejected') ORDER BY createdAt ASC LIMIT 1")
    suspend fun oldestUnacked(): OutboxEntity?

    @Query("SELECT * FROM upload_outbox WHERE jobId=:jobId AND attemptId=:attemptId ORDER BY createdAt ASC")
    suspend fun listForAttempt(jobId: Long, attemptId: Long): List<OutboxEntity>

    @Query("UPDATE upload_outbox SET jobId=:jobId, attemptId=:attemptId, leaseToken=:leaseToken, workerId=:workerId, traceId=:traceId, checkpointVersion=:checkpointVersion WHERE outboxId=:outboxId")
    suspend fun bindLease(
        outboxId: String,
        jobId: Long,
        attemptId: Long,
        leaseToken: String,
        workerId: String,
        traceId: String,
        checkpointVersion: Int,
    ): Int

    @Query("UPDATE upload_outbox SET payloadJson=:payloadJson WHERE outboxId=:outboxId AND eventType='job_checkpoint' AND state IN ('pending','retry')")
    suspend fun updatePendingCheckpoint(outboxId: String, payloadJson: String): Int

    @Query("UPDATE upload_outbox SET state='rejected', lastError=:error WHERE jobId=:jobId AND attemptId=:attemptId AND state NOT IN ('acked','rejected')")
    suspend fun rejectStaleLease(jobId: Long, attemptId: Long, error: String): Int
}

@Dao
interface JobAssignmentDao {
    @Insert(onConflict = androidx.room.OnConflictStrategy.REPLACE)
    suspend fun upsert(assignment: JobAssignmentEntity)

    @Query("SELECT * FROM job_assignment WHERE state IN ('leased','running') ORDER BY updatedAt ASC")
    suspend fun active(): List<JobAssignmentEntity>

    @Query("SELECT * FROM job_assignment WHERE jobId=:jobId LIMIT 1")
    suspend fun get(jobId: Long): JobAssignmentEntity?

    @Query("UPDATE job_assignment SET state=:state, updatedAt=:updatedAt WHERE jobId=:jobId AND attemptId=:attemptId")
    suspend fun setState(jobId: Long, attemptId: Long, state: String, updatedAt: Long): Int

    @Query("UPDATE job_assignment SET leaseExpiresAt=:expiresAt, checkpointVersion=:checkpointVersion, state=:state, updatedAt=:updatedAt WHERE jobId=:jobId AND attemptId=:attemptId")
    suspend fun updateLease(jobId: Long, attemptId: Long, expiresAt: Long, checkpointVersion: Int, state: String, updatedAt: Long): Int

    @Query("DELETE FROM job_assignment WHERE jobId=:jobId AND attemptId=:attemptId")
    suspend fun delete(jobId: Long, attemptId: Long): Int
}
