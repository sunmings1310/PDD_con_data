package com.collector.pdd.cast

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import com.collector.pdd.service.CollectA11yService

/**
 * 透明 Activity：拉起系统投屏授权框；无障碍会自动点「立即开始」。
 */
class CastPermissionActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        CollectA11yService.autoAcceptProjection = true
        val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        @Suppress("DEPRECATION")
        startActivityForResult(mpm.createScreenCaptureIntent(), REQ)
        // 超时保护：若用户未授权也关闭
        Handler(Looper.getMainLooper()).postDelayed({
            if (!isFinishing) finish()
        }, 15000)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        CollectA11yService.autoAcceptProjection = false
        if (requestCode == REQ && resultCode == RESULT_OK && data != null) {
            val i = Intent(this, ScreenCastService::class.java).apply {
                action = ScreenCastService.ACTION_START
                putExtra(ScreenCastService.EXTRA_RESULT_CODE, resultCode)
                putExtra(ScreenCastService.EXTRA_RESULT_DATA, data)
            }
            startForegroundService(i)
        }
        finish()
    }

    companion object {
        private const val REQ = 4101
    }
}
