package com.collector.pdd.data

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
class AppDatabaseMigrationTest {
    private lateinit var context: Context
    private lateinit var name: String
    private var database: AppDatabase? = null

    @Before fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        name = "phase1-${UUID.randomUUID()}.db"
    }

    @After fun tearDown() {
        database?.close()
        context.deleteDatabase(name)
    }

    private fun createVersion1() {
        val db = context.openOrCreateDatabase(name, Context.MODE_PRIVATE, null)
        db.execSQL(
            """
            CREATE TABLE task_log (
                taskId INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, taskName TEXT NOT NULL,
                startTime TEXT NOT NULL, endTime TEXT NOT NULL, keywordList TEXT NOT NULL,
                totalCount INTEGER NOT NULL, successCount INTEGER NOT NULL, failCount INTEGER NOT NULL,
                status TEXT NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE product_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, taskId INTEGER NOT NULL,
                keyword TEXT NOT NULL, itemId TEXT NOT NULL, sellName TEXT NOT NULL,
                productName TEXT NOT NULL, brand TEXT NOT NULL, shopName TEXT NOT NULL,
                shopId TEXT NOT NULL, price REAL, displayPrice REAL, groupPrice REAL,
                dealPrice REAL, originalPrice REAL, salesNum INTEGER NOT NULL,
                shopSalesNum INTEGER NOT NULL, commentNum INTEGER NOT NULL, spec TEXT NOT NULL,
                skuPricesText TEXT NOT NULL, skuPrices TEXT NOT NULL, dosageForm TEXT NOT NULL,
                approvalNo TEXT NOT NULL, manufacturer TEXT NOT NULL, expiry TEXT NOT NULL,
                category TEXT NOT NULL, couponInfo TEXT NOT NULL, mainImages TEXT NOT NULL,
                itemUrl TEXT NOT NULL, pickTag TEXT NOT NULL, specList TEXT NOT NULL,
                updateTime TEXT NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL(
            """INSERT INTO task_log
                (taskId,taskName,startTime,endTime,keywordList,totalCount,successCount,failCount,status)
                VALUES (1,'legacy','','','kw',1,1,0,'finished')""",
        )
        db.execSQL(
            """INSERT INTO product_table
                (id,taskId,keyword,itemId,sellName,productName,brand,shopName,shopId,
                 price,displayPrice,groupPrice,dealPrice,originalPrice,salesNum,shopSalesNum,
                 commentNum,spec,skuPricesText,skuPrices,dosageForm,approvalNo,manufacturer,
                 expiry,category,couponInfo,mainImages,itemUrl,pickTag,specList,updateTime)
                VALUES (1,1,'kw','123','legacy','','','','',10,NULL,NULL,NULL,NULL,0,0,
                        0,'','','','','','','','','','','','','','')""",
        )
        db.version = 1
        db.close()
    }

    private fun openMigrated(): AppDatabase {
        createVersion1()
        return Room.databaseBuilder(context, AppDatabase::class.java, name)
            .addMigrations(AppDatabase.MIGRATION_1_2, AppDatabase.MIGRATION_2_3)
            .allowMainThreadQueries()
            .build()
            .also {
                it.openHelper.writableDatabase
                database = it
            }
    }

    @Test fun migrationPreservesRowsAndMakesSalesNullable() = runBlocking {
        val db = openMigrated()
        val legacy = db.productDao().listByTask(1).single()
        assertEquals("123", legacy.itemId)
        assertEquals(0, legacy.salesNum)
        assertEquals("legacy-room-v1", legacy.parserVersion)

        val cursor = db.openHelper.readableDatabase.query("PRAGMA table_info(product_table)")
        var salesNotNull = -1
        while (cursor.moveToNext()) {
            if (cursor.getString(cursor.getColumnIndexOrThrow("name")) == "salesNum") {
                salesNotNull = cursor.getInt(cursor.getColumnIndexOrThrow("notnull"))
            }
        }
        cursor.close()
        assertEquals(0, salesNotNull)
    }

    @Test fun productAndOutboxAreAtomicAndRecoverInFlight() = runBlocking {
        val db = openMigrated()
        val dao = db.outboxDao()
        val event = OutboxEntity("product-1-a", "product", 99, payloadJson = "{}")
        val initialCount = db.productDao().countByTask(2)
        dao.insertProductAndOutbox(ProductEntity(taskId = 2, itemId = "456"), event)
        assertEquals(initialCount + 1, db.productDao().countByTask(2))
        assertEquals(1, dao.markInFlight(event.outboxId))
        assertEquals(1, dao.resetInFlight())
        assertEquals(event.outboxId, dao.ready(System.currentTimeMillis()).single().outboxId)

        val beforeFailure = db.productDao().countByTask(2)
        runCatching {
            dao.insertProductAndOutbox(ProductEntity(taskId = 2, itemId = "duplicate"), event)
        }
        assertEquals(beforeFailure, db.productDao().countByTask(2))
        dao.markAcked(event.outboxId, 100, System.currentTimeMillis())
        assertTrue(dao.ready(System.currentTimeMillis()).isEmpty())
    }

    @Test fun outboxAndRemoteTaskSurviveAppDatabaseReopen() = runBlocking {
        var db = openMigrated()
        val remoteTask = db.taskDao().insert(
            TaskEntity(taskName = "remote", status = "running", remoteTaskId = 77),
        )
        val event = OutboxEntity("product-restart-a", "product", 77, payloadJson = "{}")
        db.outboxDao().insertProductAndOutbox(ProductEntity(taskId = remoteTask), event)
        assertEquals(1, db.outboxDao().markInFlight(event.outboxId))
        db.close()
        database = null

        db = Room.databaseBuilder(context, AppDatabase::class.java, name)
            .addMigrations(AppDatabase.MIGRATION_1_2)
            .allowMainThreadQueries()
            .build()
        database = db
        db.openHelper.writableDatabase
        assertEquals(77L, db.taskDao().listRemotePending().single().remoteTaskId)
        assertEquals(1, db.outboxDao().resetInFlight())
        assertEquals(event.outboxId, db.outboxDao().ready(System.currentTimeMillis()).single().outboxId)
    }
}
