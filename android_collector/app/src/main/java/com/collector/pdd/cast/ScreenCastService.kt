package com.collector.pdd.cast

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.collector.pdd.CollectorApp
import com.collector.pdd.R
import com.collector.pdd.net.ServerPrefs
import com.collector.pdd.ui.MainActivity
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class ScreenCastService : Service() {

    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var ws: WebSocket? = null
    private var handlerThread: HandlerThread? = null
    private var handler: Handler? = null
    private val sending = AtomicBoolean(false)
    private var lastSendAt = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopCast()
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_START -> {
                val code = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
                val data = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(EXTRA_RESULT_DATA)
                }
                if (data == null) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                startForeground(NOTIF_ID, buildNotification("投屏推流中…"))
                isRunning = true
                startCast(code, data)
            }
        }
        return START_STICKY
    }

    private fun startCast(resultCode: Int, data: Intent) {
        val prefs = ServerPrefs(this)
        if (!prefs.enabled || prefs.host.isBlank()) {
            stopSelf()
            return
        }
        handlerThread = HandlerThread("cast-capture").also { it.start() }
        handler = Handler(handlerThread!!.looper)

        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projection = mpm.getMediaProjection(resultCode, data)
        projection?.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                stopCast()
                stopSelf()
            }
        }, handler)

        val dm = getSystemService(WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        dm.defaultDisplay.getRealMetrics(metrics)
        // 降采样节省带宽
        val scale = 0.4f
        val width = (metrics.widthPixels * scale).toInt().coerceAtLeast(360)
        val height = (metrics.heightPixels * scale).toInt().coerceAtLeast(640)
        val density = metrics.densityDpi

        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        virtualDisplay = projection?.createVirtualDisplay(
            "sjzq-cast",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface,
            null,
            handler,
        )

        connectWs(prefs)
        imageReader?.setOnImageAvailableListener({ reader ->
            if (!sending.compareAndSet(false, true)) {
                reader.acquireLatestImage()?.close()
                return@setOnImageAvailableListener
            }
            try {
                val now = System.currentTimeMillis()
                if (now - lastSendAt < 200) { // ~5fps
                    reader.acquireLatestImage()?.close()
                    return@setOnImageAvailableListener
                }
                val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
                val jpeg = imageToJpeg(image, width, height) ?: return@setOnImageAvailableListener
                lastSendAt = now
                ws?.send(jpeg.toByteString())
            } catch (e: Exception) {
                Log.w(TAG, "frame", e)
            } finally {
                sending.set(false)
            }
        }, handler)
    }

    private fun connectWs(prefs: ServerPrefs) {
        val url = "${prefs.wsBase()}/ws/cast/pub/${prefs.deviceKey}"
        val client = OkHttpClient.Builder()
            .pingInterval(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
        val req = Request.Builder().url(url).build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "cast ws open")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.contains("\"stop\"")) {
                    stopCast()
                    stopSelf()
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "cast ws fail: ${t.message}")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "cast ws closed")
            }
        })
    }

    private fun imageToJpeg(image: android.media.Image, width: Int, height: Int): ByteArray? {
        return try {
            val plane = image.planes[0]
            val buffer = plane.buffer
            val pixelStride = plane.pixelStride
            val rowStride = plane.rowStride
            val rowPadding = rowStride - pixelStride * width
            val bitmap = Bitmap.createBitmap(
                width + rowPadding / pixelStride,
                height,
                Bitmap.Config.ARGB_8888,
            )
            bitmap.copyPixelsFromBuffer(buffer)
            image.close()
            val cropped = if (bitmap.width != width) {
                Bitmap.createBitmap(bitmap, 0, 0, width, height).also { bitmap.recycle() }
            } else bitmap
            val bos = ByteArrayOutputStream()
            cropped.compress(Bitmap.CompressFormat.JPEG, 55, bos)
            cropped.recycle()
            bos.toByteArray()
        } catch (e: Exception) {
            try {
                image.close()
            } catch (_: Exception) {
            }
            null
        }
    }

    private fun stopCast() {
        isRunning = false
        try {
            ws?.close(1000, "stop")
        } catch (_: Exception) {
        }
        ws = null
        try {
            virtualDisplay?.release()
        } catch (_: Exception) {
        }
        virtualDisplay = null
        try {
            imageReader?.close()
        } catch (_: Exception) {
        }
        imageReader = null
        try {
            projection?.stop()
        } catch (_: Exception) {
        }
        projection = null
        handlerThread?.quitSafely()
        handlerThread = null
        handler = null
    }

    override fun onDestroy() {
        stopCast()
        super.onDestroy()
    }

    private fun buildNotification(content: String): Notification {
        val pi = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CollectorApp.CHANNEL_COLLECT)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(content)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val TAG = "ScreenCast"
        private const val NOTIF_ID = 1002
        const val ACTION_START = "com.collector.pdd.cast.START"
        const val ACTION_STOP = "com.collector.pdd.cast.STOP"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"

        @Volatile
        var isRunning: Boolean = false
            private set
    }
}
