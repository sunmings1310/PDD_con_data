package com.collector.pdd.engine

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.collector.pdd.data.AppDatabase
import com.collector.pdd.data.CollectConfig
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class TaskEngineCollectorLifecycleTest {
    @Test
    fun naturalTargetMissHasDedicatedTerminalStatus() {
        assertEquals("not_matched", taskEndStatus(stopRequested = false, success = 0, failed = 0, notMatched = 1))
        assertEquals("failed", taskEndStatus(stopRequested = false, success = 0, failed = 1, notMatched = 1))
    }

    @Test
    fun unknownPlatformFailsFastAndStillClosesLocalLifecycle() = runBlocking {
        val db = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            AppDatabase::class.java,
        ).allowMainThreadQueries().build()
        val notifications = mutableListOf<String>()
        val finished = mutableListOf<Pair<Long, String>>()
        val logs = mutableListOf<String>()
        try {
            val engine = TaskEngine(
                log = logs::add,
                onTaskFinished = { taskId, status -> finished += taskId to status },
                databaseProvider = { db },
                accessibilityEnabled = { true },
                updateNotification = notifications::add,
            )

            engine.start(this, CollectConfig(keywords = listOf("fixture"), platformCode = "unknown"))
            engine.awaitCompletionForTest()

            val tasks = db.taskDao().list()
            assertEquals(1, tasks.size)
            assertEquals("failed", tasks.single().status)
            assertTrue(tasks.single().endTime.isNotBlank())
            assertEquals(listOf(tasks.single().taskId to "failed"), finished)
            assertEquals("采集结束 failed", notifications.last())
            assertNull(engine.currentTaskId)
            assertTrue(logs.any { it.contains("unsupported platform: unknown") })
        } finally {
            db.close()
        }
    }
}
