package io.github.aadegtyarev.adlinuxtv.remote

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.webkit.CookieManager
import okhttp3.Call
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean

/** One native media-only socket, no input/keyboard channel and no reconnect/replay. */
class MediaConnection(
    val target: Target, private val cookies: CookieManager,
    private val update: (Playback, String) -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    private var socket: WebSocket? = null
    @Volatile private var sessionCall: Call? = null
    private var ready = false
    private var sequence = 0L
    private var pending: Pair<Long, Long>? = null
    private var desired: PendingPlayback? = null
    var observed = Playback(false)
        private set
    val busy: Boolean get() = pending != null || desired != null
    private val tick = object : Runnable {
        override fun run() {
            if (!valid()) return
            val now = SystemClock.elapsedRealtime()
            if (pending?.second?.let { now > it } == true) { fail("Нет подтверждения; команда не повторялась"); return }
            if (desired?.deadline?.let { now > it } == true) {
                desired = null; update(observed, "Плеер не подтвердил команду")
            }
            if (ready && pending == null) send("GET", null)
            main.postDelayed(this, 1000)
        }
    }
    val isOpen: Boolean get() = !closed.get()
    fun owns(target: Target): Boolean = isOpen && this.target == target && ActiveCenter.selection.accepts(target)
    private fun valid(): Boolean = !closed.get() && ActiveCenter.selection.accepts(target)

    fun start() {
        try {
            Network.io.execute {
                try {
                    Network.identity(target.center.endpoint, target.center.id) // No cookies before identity check.
                    check(valid())
                    val origin = target.center.endpoint.origin
                    val existing = cookies.getCookie(origin).orEmpty()
                    require(existing.length in 1..8192 && existing.none { it == '\r' || it == '\n' })
                    val call = Network.client.newCall(Request.Builder().url("$origin/api/session")
                        .header("Cookie", existing).header("Origin", origin)
                        .header("X-AD-Linux-TV-Device", target.center.id).build())
                    sessionCall = call
                    // Publish before checking: close() either cancels this call or this
                    // check observes retirement, including a switch during getCookie().
                    if (!valid()) { call.cancel(); throw IllegalStateException("retired") }
                    val data = Network.body(call)
                    val csrf = data.getString("csrf")
                    require(Regex("[a-zA-Z0-9_-]{16,128}").matches(csrf))
                    // Session GET must use the already-paired profile; no credentials are persisted by us.
                    check(valid())
                    main.post {
                        if (!valid()) return@post
                        val url = origin.replaceFirst("http", "ws") + "/api/remote-ws"
                        val protocol = "csrf.$csrf"
                        val request = Request.Builder().url(url).header("Origin", origin)
                            .header("Cookie", existing).header("Sec-WebSocket-Protocol", protocol)
                            .header("X-AD-Linux-TV-Device", target.center.id).build()
                        socket = Network.client.newWebSocket(request, listener(protocol))
                    }
                } catch (_: Exception) {
                    main.post { if (valid()) fail("Откройте пульт и завершите подключение") }
                } finally { sessionCall = null }
            }
        } catch (_: RuntimeException) { fail("Подключение занято; попробуйте позже") }
    }

    private fun listener(protocol: String) = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            main.post {
                if (!valid() || socket !== webSocket) { webSocket.cancel(); return@post }
                if (response.header("Sec-WebSocket-Protocol") != protocol) { fail("Ошибка протокола"); return@post }
                ready = true; main.post(tick)
            }
        }
        override fun onMessage(webSocket: WebSocket, text: String) {
            main.post {
                if (!valid() || socket !== webSocket) return@post
                try {
                    require(text.length <= 32768)
                    val data = JSONObject(text)
                    require(data.keys().asSequence().toSet() == setOf("id", "status", "body"))
                    require(data.getLong("id") == pending?.first)
                    val status = data.getInt("status")
                    pending = null
                    if (status != 200 && status != 202) {
                        desired = null
                        if (status == 401 || status == 403) fail("Нужна повторная авторизация")
                        else update(observed, "Команда не подтверждена")
                        return@post
                    }
                    val body = data.getJSONObject("body")
                    observed = if (!body.getBoolean("available")) Playback(false) else {
                        val identity = if (body.has("media_id")) body.getString("media_id").also {
                            require(Regex("[0-9a-f]{32}").matches(it))
                        } else null
                        Playback(true, body.optString("title").take(160), body.getBoolean("playing"),
                            body.getBoolean("can_play"), body.getBoolean("can_pause"),
                            body.getBoolean("can_next"), body.getBoolean("can_previous"), identity)
                    }
                    if (desired?.sameSource(observed) == false) {
                        desired = null
                        update(observed, "Источник изменился; команда не повторялась")
                    } else {
                        if (desired?.playing == observed.playing) desired = null
                        update(observed, if (desired != null) "Ожидаем подтверждение…" else "")
                    }
                } catch (_: Exception) { fail("Некорректный ответ пульта") }
            }
        }
        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            main.post { if (valid() && socket === webSocket) fail("Нет связи; откройте пульт") }
        }
        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            main.post { if (valid() && socket === webSocket) fail("Соединение закрыто") }
        }
        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null) }
    }

    private fun send(method: String, body: JSONObject?) {
        if (!valid() || !ready || pending != null) return
        val id = ++sequence
        pending = id to (SystemClock.elapsedRealtime() + 5000)
        val frame = JSONObject().put("id", id).put("method", method).put("path", "/api/media")
            .put("body", body ?: JSONObject.NULL)
        if (socket?.send(frame.toString()) != true) fail("Соединение потеряно")
    }

    fun action(action: String) {
        if (!valid() || busy || !observed.permits(action)) return
        val body = JSONObject().put("action", action)
        observed.mediaId?.let { body.put("media_id", it) }
        if (action == "play" || action == "pause") desired = PendingPlayback(action == "play", SystemClock.elapsedRealtime() + 5000, observed.mediaId)
        send("POST", body)
        update(observed, "Ожидаем подтверждение…")
    }

    private fun fail(message: String) {
        if (closed.get()) return
        close(); observed = Playback(false); update(observed, message)
    }
    fun close() {
        if (!closed.compareAndSet(false, true)) return
        main.removeCallbacks(tick)
        sessionCall?.cancel(); sessionCall = null
        socket?.cancel(); socket = null; ready = false; pending = null; desired = null
        if (ActiveCenter.media === this) ActiveCenter.changed()
    }
}
