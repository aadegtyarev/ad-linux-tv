package io.github.aadegtyarev.adlinuxtv.remote

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper

/** Discovery is untrusted metadata. A cookie-free identity check precedes every page load. */
class Discovery internal constructor(
    private val manager: NsdManager,
    private val update: (List<Center>, String) -> Unit,
) {
    constructor(context: Context, update: (List<Center>, String) -> Unit) :
        this(context.getSystemService(Context.NSD_SERVICE) as NsdManager, update)
    private val main = Handler(Looper.getMainLooper())
    private val directory = Directory()
    private val queue = ArrayDeque<Pair<NsdServiceInfo, Long>>()
    private val seen = mutableMapOf<String, Long>()
    private var serial = 0L
    private var resolutionToken = 0L
    private var stalled = false
    private var generation = 0L
    private var listener: NsdManager.DiscoveryListener? = null
    private var resolving = false

    fun start() {
        stop()
        val epoch = generation
        val observer = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(type: String) = Unit
            override fun onDiscoveryStopped(type: String) = Unit
            override fun onStartDiscoveryFailed(type: String, error: Int) = failure(epoch)
            override fun onStopDiscoveryFailed(type: String, error: Int) = Unit
            override fun onServiceFound(info: NsdServiceInfo) {
                main.post {
                    if (epoch != generation || info.serviceType.trimEnd('.') != "_ad-linux-tv._tcp") return@post
                    if (queue.size < 64 && (seen.size < 64 || info.serviceName in seen)) {
                        serial += 1; seen[info.serviceName] = serial
                        queue.add(info to serial); next(epoch)
                    }
                }
            }
            override fun onServiceLost(info: NsdServiceInfo) {
                main.post {
                    if (epoch != generation) return@post
                    seen.remove(info.serviceName)
                    directory.lost(info.serviceName)
                    queue.removeAll { it.first.serviceName == info.serviceName }
                    update(directory.centers(), "")
                }
            }
        }
        listener = observer
        try { manager.discoverServices("_ad-linux-tv._tcp.", NsdManager.PROTOCOL_DNS_SD, observer) }
        catch (_: RuntimeException) { failure(epoch) }
    }

    private fun failure(epoch: Long) {
        main.post { if (epoch == generation) update(directory.centers(), "Поиск недоступен; используйте адрес или QR") }
    }

    @Suppress("DEPRECATION") // Serial resolution supports Android 9+, not just API34 callbacks.
    private fun next(epoch: Long) {
        if (stalled || resolving || queue.isEmpty() || epoch != generation) return
        resolving = true
        val (candidate, observed) = queue.removeFirst()
        val token = ++resolutionToken
        main.postDelayed({
            if (epoch == generation && token == resolutionToken && resolving) {
                stalled = true; resolving = false; resolutionToken += 1; queue.clear()
                update(directory.centers(), "Поиск не завершился; нажмите «Обновить»")
            }
        }, 7000)
        try {
            manager.resolveService(candidate, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, error: Int) = done(null)
                override fun onServiceResolved(info: NsdServiceInfo) = done(info)
                private fun done(info: NsdServiceInfo?) {
                    main.post {
                        if (epoch != generation || token != resolutionToken) return@post
                        resolutionToken += 1
                        resolving = false
                        if (info != null && seen[candidate.serviceName] == observed) runCatching {
                            fun txt(key: String) = requireNotNull(info.attributes[key]).toString(Charsets.UTF_8)
                            require(txt("protocol") == "1" && txt("path") == "/remote")
                            val address = requireNotNull(info.host?.hostAddress)
                            val authority = if (address.contains(':')) "[$address]" else address
                            val center = Center(txt("id"), txt("name"), Endpoint.parse("http://$authority:${info.port}"))
                            directory.observe(candidate.serviceName, center)
                        }
                        update(directory.centers(), "")
                        next(epoch)
                    }
                }
            })
        } catch (_: RuntimeException) { resolving = false; failure(epoch); next(epoch) }
    }

    fun stop() {
        generation += 1
        listener?.let { runCatching { manager.stopServiceDiscovery(it) } }
        listener = null
        queue.clear(); seen.clear(); directory.clear(); resolving = false; stalled = false
        resolutionToken += 1
    }
}
