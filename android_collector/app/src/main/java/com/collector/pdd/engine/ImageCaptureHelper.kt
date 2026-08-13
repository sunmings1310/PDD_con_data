package com.collector.pdd.engine

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import android.view.Display
import com.collector.pdd.CollectorApp
import com.collector.pdd.service.CollectA11yService
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * 拼多多 H5 未登录拿不到主图 URL 时，从 App 界面截主图区域落地到导出目录。
 */
object ImageCaptureHelper {

    private val executor: Executor = Executors.newSingleThreadExecutor()

    suspend fun screenshotMainImage(
        service: CollectA11yService,
        goodsId: String,
        log: (String) -> Unit,
    ): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            log("系统过旧，无法无障碍截图")
            return ""
        }
        val full = takeScreenshotBitmap(service) ?: run {
            log("截图失败")
            return ""
        }
        return try {
            // 详情主图大致在屏幕上部 12%～48%
            val w = full.width
            val h = full.height
            val top = (h * 0.10f).toInt().coerceIn(0, h - 2)
            val bottom = (h * 0.48f).toInt().coerceIn(top + 2, h)
            val crop = Bitmap.createBitmap(full, 0, top, w, bottom - top)
            if (!full.isRecycled) full.recycle()
            val name = "g_${goodsId.ifBlank { System.currentTimeMillis().toString() }}.jpg"
            val dir = File(CollectorApp.instance.getExternalFilesDir(null), "exports/images")
                .apply { mkdirs() }
            val out = File(dir, name)
            FileOutputStream(out).use { fos ->
                crop.compress(Bitmap.CompressFormat.JPEG, 88, fos)
            }
            if (!crop.isRecycled) crop.recycle()
            log("主图已截取 ${out.name}")
            out.absolutePath
        } catch (e: Exception) {
            log("保存截图失败: ${e.message}")
            ""
        }
    }

    /** 保存异常发生时的完整页面，供任务详情和日志回放。 */
    suspend fun screenshotAnomaly(
        service: CollectA11yService,
        taskId: Long,
        actionName: String,
        log: (String) -> Unit,
    ): File? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        val full = takeScreenshotBitmap(service) ?: return null
        return try {
            val safeAction = actionName.replace(Regex("[^A-Za-z0-9_-]"), "_").take(40)
            val dir = File(CollectorApp.instance.getExternalFilesDir(null), "anomalies/task_$taskId")
                .apply { mkdirs() }
            val out = File(dir, "${System.currentTimeMillis()}_${safeAction}.jpg")
            FileOutputStream(out).use { fos ->
                full.compress(Bitmap.CompressFormat.JPEG, 88, fos)
            }
            log("异常页面已截图 ${out.name}")
            out
        } catch (e: Exception) {
            log("异常页面截图保存失败: ${e.message}")
            null
        } finally {
            if (!full.isRecycled) full.recycle()
        }
    }

    private suspend fun takeScreenshotBitmap(service: AccessibilityService): Bitmap? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        return suspendCoroutine { cont ->
            try {
                service.takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    executor,
                    object : AccessibilityService.TakeScreenshotCallback {
                        override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                            try {
                                val hw = screenshot.hardwareBuffer
                                val colorSpace = screenshot.colorSpace
                                val bmp = Bitmap.wrapHardwareBuffer(hw, colorSpace)
                                hw.close()
                                // 转软件位图便于裁剪压缩
                                val soft = bmp?.copy(Bitmap.Config.ARGB_8888, false)
                                bmp?.recycle()
                                cont.resume(soft)
                            } catch (e: Exception) {
                                cont.resume(null)
                            }
                        }

                        override fun onFailure(errorCode: Int) {
                            cont.resume(null)
                        }
                    },
                )
            } catch (_: Exception) {
                cont.resume(null)
            }
        }
    }

    /** 从剪贴板 HTML/URI 里抽图片地址 */
    fun imagesFromClipboard(service: CollectA11yService): List<String> {
        return try {
            val cm = service.getSystemService(android.content.Context.CLIPBOARD_SERVICE)
                as android.content.ClipboardManager
            val clip = cm.primaryClip ?: return emptyList()
            val out = mutableListOf<String>()
            for (i in 0 until clip.itemCount) {
                val item = clip.getItemAt(i) ?: continue
                item.htmlText?.let { html ->
                    Regex(
                        """https?://[^"'\\\s<>]+?\.(?:jpg|jpeg|png|webp)[^"'\\\s<>]*""",
                        RegexOption.IGNORE_CASE,
                    ).findAll(html).forEach { out.add(it.value) }
                }
                item.uri?.toString()?.let { u ->
                    if (GoodsLinkResolver.isProductImageUrl(u) || u.contains("pddpic", true)) {
                        out.add(u)
                    }
                }
            }
            out.distinct().filter { GoodsLinkResolver.isProductImageUrl(it) }
        } catch (_: Exception) {
            emptyList()
        }
    }
}
