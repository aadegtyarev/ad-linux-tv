package io.github.aadegtyarev.adlinuxtv.remote

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.widget.Toast
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.media.VolumeProviderCompat
import androidx.media.app.NotificationCompat.MediaStyle
import androidx.webkit.ProfileStore
import androidx.webkit.WebViewFeature

/** Explicit user opt-in; remote-device foreground connection, never local audio playback. */
class RemoteMediaService : Service() {
    companion object {
        const val CONNECT = "remote.connect"
        private const val STOP = "remote.stop"
        private const val CHANNEL = "remote-media"
        private const val NOTIFICATION = 101
    }
    private lateinit var session: MediaSessionCompat
    private var connection: MediaConnection? = null
    private var state = Playback(false)
    private var message = "Подключение…"
    private var owner: Target? = null
    private var generation = 0L
    private val pendingButtons = mutableListOf<PendingIntent>()

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Управление телевизором", NotificationManager.IMPORTANCE_LOW))
        session = MediaSessionCompat(this, "AD Linux TV remote")
        session.setPlaybackToRemote(object : VolumeProviderCompat(VOLUME_CONTROL_FIXED, 0, 0) {})
        session.isActive = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val target = ActiveCenter.selection.target()
        if (target == null || intent?.getLongExtra("epoch", -1) != target.epoch) {
            if (retireStaleService(owner, target)) {
                connection?.close()
                if (ActiveCenter.media === connection) ActiveCenter.media = null
                stopSelf(startId)
            }
            // A delayed old intent must not tear down a valid replacement connection.
            return START_NOT_STICKY
        }
        if (intent.action == CONNECT) {
            if (!WebViewFeature.isFeatureSupported(WebViewFeature.MULTI_PROFILE)) {
                stopSelf(startId); return START_NOT_STICKY
            }
            generation += 1
            val revision = generation
            connection?.close()
            owner = target; state = Playback(false); message = "Подключение…"
            session.setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() { if (revision == generation) perform("play") }
                override fun onPause() { if (revision == generation) perform("pause") }
                override fun onSkipToNext() { if (revision == generation) perform("next") }
                override fun onSkipToPrevious() { if (revision == generation) perform("previous") }
            })
            try {
                ServiceCompat.startForeground(this, NOTIFICATION, notification(),
                    if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0)
                val cookies = ProfileStore.getInstance().getOrCreateProfile(target.center.profile).cookieManager
                val client = MediaConnection(target, cookies) { observed, feedback ->
                    if (revision == generation && ActiveCenter.selection.accepts(target)) {
                        state = observed; message = feedback; publish()
                    }
                }
                connection = client; ActiveCenter.media = client; client.start()
            } catch (_: RuntimeException) {
                if (MediaOptIn.mayReportStartupFailure(owner == target,
                        ActiveCenter.selection.accepts(target), revision == generation)) {
                    Toast.makeText(this, "Не удалось подключить медиакнопки", Toast.LENGTH_LONG).show()
                }
                stopSelf(startId)
            }
        } else if (intent.getLongExtra("generation", -1) == generation && owner == target) {
            if (intent.action == STOP) { stopSelf(startId) }
            else if (intent.getStringExtra("media_id") == state.mediaId) perform(intent.action.orEmpty())
        }
        return START_NOT_STICKY
    }

    private fun perform(action: String) {
        val target = owner ?: return
        if (!ActiveCenter.selection.accepts(target) || !state.permits(action)) return
        if (connection?.busy == true) {
            message = "Сверяем состояние плеера…"; publish(); return
        }
        connection?.action(action)
    }

    private fun publish() {
        if (owner?.let { ActiveCenter.selection.accepts(it) } != true) return
        var actions = 0L
        if (state.available && connection?.busy != true) {
            if (state.canPlay) actions = actions or PlaybackStateCompat.ACTION_PLAY
            if (state.canPause) actions = actions or PlaybackStateCompat.ACTION_PAUSE
            if (state.canNext) actions = actions or PlaybackStateCompat.ACTION_SKIP_TO_NEXT
            if (state.canPrevious) actions = actions or PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS
        }
        val playback = when {
            !state.available -> PlaybackStateCompat.STATE_NONE
            connection?.busy == true -> PlaybackStateCompat.STATE_BUFFERING
            state.playing -> PlaybackStateCompat.STATE_PLAYING
            else -> PlaybackStateCompat.STATE_PAUSED
        }
        session.setPlaybackState(PlaybackStateCompat.Builder().setActions(actions)
            .setState(playback, PlaybackStateCompat.PLAYBACK_POSITION_UNKNOWN, if (state.playing) 1f else 0f).build())
        session.setMetadata(MediaMetadataCompat.Builder().putString(MediaMetadataCompat.METADATA_KEY_TITLE,
            state.title.ifBlank { owner?.center?.name.orEmpty() }).build())
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION, notification())
    }

    private fun actionIntent(action: String): PendingIntent {
        val target = requireNotNull(owner)
        val token = "${target.epoch}/$generation/$action/${state.mediaId.orEmpty()}"
        val intent = Intent(this, RemoteMediaService::class.java).setAction(action)
            .setData(Uri.parse("ad-linux-tv-action://button/$token"))
            .putExtra("epoch", target.epoch).putExtra("generation", generation).putExtra("media_id", state.mediaId)
        return PendingIntent.getService(this, token.hashCode(), intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT).also { pendingButtons.add(it) }
    }

    private fun notification(): android.app.Notification {
        pendingButtons.forEach { it.cancel() }; pendingButtons.clear()
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val builder = NotificationCompat.Builder(this, CHANNEL).setSmallIcon(R.drawable.ic_stat_tv)
            .setContentTitle(owner?.center?.name ?: "AD Linux TV")
            .setContentText(message.ifBlank { state.title.ifBlank { "Плеер недоступен" } })
            .setContentIntent(open).setOnlyAlertOnce(true).setOngoing(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
        val compact = mutableListOf<Int>()
        if (state.available && connection?.busy != true) {
            if (state.canPrevious) {
                compact.add(compact.size)
                builder.addAction(android.R.drawable.ic_media_previous, "Предыдущий", actionIntent("previous"))
            }
            val action = if (state.playing) "pause" else "play"
            if (state.permits(action)) {
                compact.add(compact.size)
                builder.addAction(if (state.playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play,
                    if (state.playing) "Пауза" else "Играть", actionIntent(action))
            }
            if (state.canNext) {
                compact.add(compact.size)
                builder.addAction(android.R.drawable.ic_media_next, "Следующий", actionIntent("next"))
            }
        }
        if (owner != null) builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Отключить", actionIntent(STOP))
        builder.setStyle(MediaStyle().setMediaSession(session.sessionToken).setShowActionsInCompactView(*compact.take(3).toIntArray()))
        return builder.build()
    }

    override fun onDestroy() {
        generation += 1
        val old = connection; old?.close()
        if (ActiveCenter.media === old) ActiveCenter.media = null
        connection = null
        pendingButtons.forEach { it.cancel() }; pendingButtons.clear()
        session.release(); stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
