package com.collector.pdd.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

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
