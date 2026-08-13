package com.collector.pdd.data

import androidx.room.Entity
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
    val salesNum: Int = 0,
    val shopSalesNum: Int = 0,
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
)
