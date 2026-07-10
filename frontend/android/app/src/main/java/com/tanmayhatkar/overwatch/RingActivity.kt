package com.tanmayhatkar.overwatch

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Tier-2 full-screen ring (ADR-0019).
 *
 * Launched either automatically by the notification's full-screen intent
 * (device locked / app backgrounded, and USE_FULL_SCREEN_INTENT granted), or
 * by the user tapping the fallback heads-up notification. Loops an
 * alarm-stream ringtone + vibration until Snooze or Done is tapped, then
 * relays that tap through [RingActionReceiver] — the same funnel the
 * fallback notification's inline actions use — so notifications.js only
 * needs one JS-side handler for both entry points.
 */
class RingActivity : AppCompatActivity() {

    private var mediaPlayer: MediaPlayer? = null
    private var vibrator: Vibrator? = null
    private var ringId: Int = -1

    private val stopReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.getIntExtra(RingConstants.EXTRA_ID, -1) == ringId) {
                stopRinging()
                finish()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        applyLockScreenWakeFlags()
        setContentView(R.layout.activity_ring)

        ringId = intent.getIntExtra(RingConstants.EXTRA_ID, -1)
        val commitmentId = intent.getStringExtra(RingConstants.EXTRA_COMMITMENT_ID)
        val title = intent.getStringExtra(RingConstants.EXTRA_TITLE) ?: "Overwatch"
        val body = intent.getStringExtra(RingConstants.EXTRA_BODY) ?: ""

        findViewById<TextView>(R.id.ringTitle).text = title
        findViewById<TextView>(R.id.ringBody).text = body
        findViewById<Button>(R.id.ringDone).setOnClickListener { sendAction(commitmentId, "DONE") }
        findViewById<Button>(R.id.ringSnooze).setOnClickListener { sendAction(commitmentId, "SNOOZE") }

        val filter = IntentFilter(RingConstants.ACTION_STOP_RING)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(stopReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(stopReceiver, filter)
        }

        startRinging()
    }

    /**
     * android:showWhenLocked / android:turnScreenOn (manifest) cover API 27+.
     * The Window-flag equivalents below are the documented pre-27 fallback,
     * and FLAG_DISMISS_KEYGUARD is still worth setting defensively even on
     * newer OEM skins that don't fully honor the manifest attributes alone.
     */
    private fun applyLockScreenWakeFlags() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                    WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD,
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun startRinging() {
        try {
            val uri = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            mediaPlayer = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build(),
                )
                setDataSource(this@RingActivity, uri)
                isLooping = true
                prepare()
                start()
            }
        } catch (e: Exception) {
            // No ringtone available on this device/emulator — vibration below still runs.
        }

        try {
            val pattern = longArrayOf(0, 800, 500)
            vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 0))
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, 0)
            }
        } catch (e: Exception) {
            // Vibration is best-effort.
        }
    }

    private fun stopRinging() {
        try {
            mediaPlayer?.stop()
            mediaPlayer?.release()
        } catch (e: Exception) {
            // already stopped/released
        }
        mediaPlayer = null
        try {
            vibrator?.cancel()
        } catch (e: Exception) {
            // best-effort
        }
    }

    private fun sendAction(commitmentId: String?, action: String) {
        val intent = Intent(RingConstants.ACTION_RING_BUTTON).setPackage(packageName)
        intent.setClass(this, RingActionReceiver::class.java)
        intent.putExtra(RingConstants.EXTRA_ID, ringId)
        intent.putExtra(RingConstants.EXTRA_COMMITMENT_ID, commitmentId)
        intent.putExtra(RingConstants.EXTRA_ACTION, action)
        sendBroadcast(intent)
        stopRinging()
        finish()
    }

    override fun onDestroy() {
        stopRinging()
        try {
            unregisterReceiver(stopReceiver)
        } catch (e: Exception) {
            // not registered / already gone
        }
        super.onDestroy()
    }
}
