package com.collector.pdd.engine

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import com.collector.pdd.CollectorApp
import java.io.File
import java.io.FileOutputStream

/**
 * 从系统相册捞「刚刚保存」的图片，复制到导出目录供 CSV 引用。
 */
object GalleryImagePicker {

    data class Shot(
        val path: String,
        val addedMs: Long,
    )

    /**
     * @param sinceEpochMs 只取该时间之后入库的图片（拼多多一点保存后写入相册）
     * @param limit 最多张数
     */
    fun collectRecent(
        context: Context = CollectorApp.instance,
        sinceEpochMs: Long,
        limit: Int = 8,
        goodsId: String = "",
        log: (String) -> Unit = {},
    ): List<String> {
        val sinceSec = (sinceEpochMs / 1000L) - 2
        val shots = queryRecent(context, sinceSec, limit * 2)
        if (shots.isEmpty()) {
            log("相册未发现新图 since=$sinceSec")
            return emptyList()
        }
        val dir = File(context.getExternalFilesDir(null), "exports/images").apply { mkdirs() }
        val prefix = goodsId.ifBlank { sinceEpochMs.toString() }
        val out = mutableListOf<String>()
        for ((i, s) in shots.withIndex()) {
            if (out.size >= limit) break
            val name = "g_${prefix}_${i + 1}.jpg"
            val dest = File(dir, name)
            val ok = copyUriToFile(context, s.uri, dest) ||
                (s.path.isNotBlank() && copyFile(s.path, dest))
            if (ok && dest.exists() && dest.length() > 1024) {
                out.add(dest.absolutePath)
            }
        }
        log("从相册抓取 ${out.size}/${shots.size} 张")
        return out
    }

    private data class Row(val uri: Uri, val path: String, val added: Long)

    private fun queryRecent(context: Context, sinceSec: Long, limit: Int): List<Row> {
        val collection: Uri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        } else {
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        }
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.DATE_ADDED,
            MediaStore.Images.Media.DATE_MODIFIED,
            MediaStore.Images.Media.SIZE,
            MediaStore.Images.Media.DATA,
        )
        val selection =
            "(${MediaStore.Images.Media.DATE_ADDED}>=? OR ${MediaStore.Images.Media.DATE_MODIFIED}>=?)"
        val args = arrayOf(sinceSec.toString(), sinceSec.toString())
        val sort = "${MediaStore.Images.Media.DATE_ADDED} DESC"
        val rows = mutableListOf<Row>()
        try {
            context.contentResolver.query(collection, projection, selection, args, sort)?.use { c ->
                val idCol = c.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                val addCol = c.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)
                val dataCol = c.getColumnIndex(MediaStore.Images.Media.DATA)
                val sizeCol = c.getColumnIndex(MediaStore.Images.Media.SIZE)
                while (c.moveToNext() && rows.size < limit) {
                    val size = if (sizeCol >= 0) c.getLong(sizeCol) else 0L
                    if (size in 1 until 2048) continue // 跳过过小的图标
                    val id = c.getLong(idCol)
                    val uri = ContentUris.withAppendedId(collection, id)
                    val path = if (dataCol >= 0) c.getString(dataCol).orEmpty() else ""
                    val added = c.getLong(addCol) * 1000L
                    rows.add(Row(uri, path, added))
                }
            }
        } catch (_: SecurityException) {
            // 无读图权限
        } catch (_: Exception) {
        }
        return rows
    }

    private fun copyUriToFile(context: Context, uri: Uri, dest: File): Boolean {
        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(dest).use { output -> input.copyTo(output) }
            }
            dest.exists() && dest.length() > 0
        } catch (_: Exception) {
            false
        }
    }

    private fun copyFile(srcPath: String, dest: File): Boolean {
        return try {
            val src = File(srcPath)
            if (!src.exists()) return false
            src.copyTo(dest, overwrite = true)
            dest.exists()
        } catch (_: Exception) {
            false
        }
    }
}
