package com.collector.pdd.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [TaskEntity::class, ProductEntity::class, OutboxEntity::class, JobAssignmentEntity::class],
    version = 3,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun taskDao(): TaskDao
    abstract fun productDao(): ProductDao
    abstract fun outboxDao(): OutboxDao
    abstract fun jobAssignmentDao(): JobAssignmentDao

    companion object {
        @Volatile private var INSTANCE: AppDatabase? = null

        fun get(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "pdd_collector.db",
                ).addMigrations(MIGRATION_1_2, MIGRATION_2_3).build().also { INSTANCE = it }
            }
        }

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE task_log ADD COLUMN remoteTaskId INTEGER")
                // Rebuild once so legacy NOT NULL sales columns become nullable without losing rows.
                db.execSQL(
                    """
                    CREATE TABLE product_table_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        taskId INTEGER NOT NULL, keyword TEXT NOT NULL, itemId TEXT NOT NULL,
                        sellName TEXT NOT NULL, productName TEXT NOT NULL, brand TEXT NOT NULL,
                        shopName TEXT NOT NULL, shopId TEXT NOT NULL,
                        price REAL, displayPrice REAL, groupPrice REAL, dealPrice REAL, originalPrice REAL,
                        salesNum INTEGER, shopSalesNum INTEGER, commentNum INTEGER NOT NULL,
                        spec TEXT NOT NULL, skuPricesText TEXT NOT NULL, skuPrices TEXT NOT NULL,
                        dosageForm TEXT NOT NULL, approvalNo TEXT NOT NULL, manufacturer TEXT NOT NULL,
                        expiry TEXT NOT NULL, category TEXT NOT NULL, couponInfo TEXT NOT NULL,
                        mainImages TEXT NOT NULL, itemUrl TEXT NOT NULL, pickTag TEXT NOT NULL,
                        specList TEXT NOT NULL, updateTime TEXT NOT NULL,
                        parseStatus TEXT NOT NULL, pageStatus TEXT NOT NULL, qualityStatus TEXT NOT NULL,
                        fieldSources TEXT NOT NULL, parserVersion TEXT NOT NULL, qualityRulesVersion TEXT NOT NULL
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    INSERT INTO product_table_v2 (
                        id, taskId, keyword, itemId, sellName, productName, brand, shopName, shopId,
                        price, displayPrice, groupPrice, dealPrice, originalPrice, salesNum, shopSalesNum,
                        commentNum, spec, skuPricesText, skuPrices, dosageForm, approvalNo, manufacturer,
                        expiry, category, couponInfo, mainImages, itemUrl, pickTag, specList, updateTime,
                        parseStatus, pageStatus, qualityStatus, fieldSources, parserVersion, qualityRulesVersion
                    ) SELECT
                        id, taskId, keyword, itemId, sellName, productName, brand, shopName, shopId,
                        price, displayPrice, groupPrice, dealPrice, originalPrice, salesNum, shopSalesNum,
                        commentNum, spec, skuPricesText, skuPrices, dosageForm, approvalNo, manufacturer,
                        expiry, category, couponInfo, mainImages, itemUrl, pickTag, specList, updateTime,
                        'success', 'product', 'passed', '{}', 'legacy-room-v1', 'phase1-1'
                    FROM product_table
                    """.trimIndent(),
                )
                db.execSQL("DROP TABLE product_table")
                db.execSQL("ALTER TABLE product_table_v2 RENAME TO product_table")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS upload_outbox (
                        outboxId TEXT NOT NULL PRIMARY KEY,
                        eventType TEXT NOT NULL,
                        remoteTaskId INTEGER NOT NULL,
                        taskItemId INTEGER,
                        payloadJson TEXT NOT NULL,
                        requiredImageCount INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        attemptCount INTEGER NOT NULL,
                        nextAttemptAt INTEGER NOT NULL,
                        lastError TEXT NOT NULL,
                        serverProductId INTEGER,
                        createdAt INTEGER NOT NULL,
                        ackedAt INTEGER
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    "CREATE INDEX IF NOT EXISTS index_upload_outbox_state_nextAttemptAt " +
                        "ON upload_outbox(state, nextAttemptAt)",
                )
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN jobId INTEGER")
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN attemptId INTEGER")
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN leaseToken TEXT")
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN workerId TEXT")
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN traceId TEXT")
                db.execSQL("ALTER TABLE upload_outbox ADD COLUMN checkpointVersion INTEGER NOT NULL DEFAULT 0")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_upload_outbox_jobId_attemptId ON upload_outbox(jobId, attemptId)")
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS job_assignment (
                        jobId INTEGER NOT NULL PRIMARY KEY,
                        taskId INTEGER NOT NULL,
                        jobKey TEXT NOT NULL,
                        jobType TEXT NOT NULL,
                        payloadJson TEXT NOT NULL,
                        attemptId INTEGER NOT NULL,
                        attemptNo INTEGER NOT NULL,
                        leaseToken TEXT NOT NULL,
                        workerId TEXT NOT NULL,
                        traceId TEXT NOT NULL,
                        checkpointVersion INTEGER NOT NULL DEFAULT 0,
                        leaseExpiresAt INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        updatedAt INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_job_assignment_taskId ON job_assignment(taskId)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_job_assignment_state ON job_assignment(state)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_job_assignment_leaseExpiresAt ON job_assignment(leaseExpiresAt)")
            }
        }
    }
}
