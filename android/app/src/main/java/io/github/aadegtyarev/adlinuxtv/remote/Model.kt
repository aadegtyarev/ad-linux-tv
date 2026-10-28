package io.github.aadegtyarev.adlinuxtv.remote

import java.net.Inet6Address
import java.net.InetAddress
import java.net.URI
import java.security.MessageDigest
import java.util.UUID

/** No Android/network dependencies: validation and lifecycle rules are unit-testable. */
data class Endpoint(val scheme: String, val address: String, val port: Int) {
    init { require(scheme in setOf("http", "https") && port in 1..65535 && privateAddress(address) != null) }
    val origin: String get() = "$scheme://${if (address.contains(':')) "[$address]" else address}:$port"
    val remote: String get() = "$origin/remote"

    companion object {
        fun privateAddress(raw: String): String? {
            val host = raw.removePrefix("[").removeSuffix("]")
            if (host.contains(':')) {
                if (!Regex("[0-9a-fA-F:]+").matches(host)) return null
                val value = runCatching { InetAddress.getByName(host) }.getOrNull()
                if (value !is Inet6Address || (value.address[0].toInt() and 0xfe) != 0xfc) return null
                return value.hostAddress?.lowercase()
            }
            val parts = host.split('.')
            if (parts.size != 4 || parts.any { !Regex("0|[1-9][0-9]{0,2}").matches(it) }) return null
            val bytes = parts.map { it.toInt() }
            if (bytes.any { it > 255 }) return null
            if (!(bytes[0] == 10 || (bytes[0] == 172 && bytes[1] in 16..31) ||
                        (bytes[0] == 192 && bytes[1] == 168))) return null
            return bytes.joinToString(".")
        }

        fun parse(raw: String, resolve: (String) -> List<String> = { emptyList() }): Endpoint {
            val text = raw.trim()
            require(text.length in 1..512 && text.none { it.code <= 32 || it.code == 127 || it == '\\' || it == '%' })
            val uri = URI(if (text.contains("://")) text else "http://$text")
            val scheme = uri.scheme?.lowercase()
            require(scheme in setOf("http", "https") && uri.rawUserInfo == null &&
                    uri.rawQuery == null && uri.rawFragment == null &&
                    uri.rawPath in listOf("", "/", "/remote"))
            val host = requireNotNull(uri.host).removePrefix("[").removeSuffix("]")
            val port = if (uri.port == -1) 8765 else uri.port
            require(port in 1..65535)
            val literal = privateAddress(host)
            val candidates = if (literal != null) listOf(literal) else {
                require(!host.contains(':') && !Regex("[0-9.]+").matches(host))
                require(host.length <= 253 && host.trimEnd('.').split('.').all {
                    Regex("[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?").matches(it)
                })
                val resolved = resolve(host)
                require(resolved.isNotEmpty() && resolved.size <= 16)
                resolved.map { requireNotNull(privateAddress(it)) }
            }
            return Endpoint(requireNotNull(scheme), candidates.sorted().first(), port)
        }
    }
}

data class Center(val id: String, val name: String, val endpoint: Endpoint) {
    init {
        require(runCatching { UUID.fromString(id).toString() == id }.getOrDefault(false))
        require(name.isNotBlank() && name == name.trim() && name.length <= 80 &&
                name.toByteArray(Charsets.UTF_8).size <= 160 && name.none { it.code < 32 || it.code == 127 })
    }
    // Bind storage both to identity AND origin: no bearer-cookie migration after IP change.
    val profile: String get() = "tv_" + MessageDigest.getInstance("SHA-256")
        .digest("$id|${endpoint.origin}".toByteArray()).joinToString("") { "%02x".format(it) }
}

// A stale start may retire an obsolete owner, never a valid newly selected service.
fun retireStaleService(owner: Target?, current: Target?): Boolean = owner == null || owner != current

data class Target(val epoch: Long, val center: Center)

fun pickerCenters(found: List<Center>, saved: List<Center>): List<Center> =
    (found + saved.filter { old -> found.none { it.id == old.id } })
        .distinctBy { it.id + it.endpoint.origin }.sortedBy { it.name }

fun startupCenter(saved: List<Center>, lastId: String?, explicitPicker: Boolean): Center? =
    if (explicitPicker || lastId == null) null else saved.firstOrNull { it.id == lastId }

class Selection {
    private var generation = 0L
    private var current: Target? = null
    @Synchronized fun select(center: Center): Target {
        generation += 1
        return Target(generation, center).also { current = it }
    }
    @Synchronized fun revoke() { generation += 1; current = null }
    @Synchronized fun target(): Target? = current
    @Synchronized fun accepts(target: Target): Boolean = current == target
}

class Directory {
    private val records = linkedMapOf<String, Center>()
    fun observe(service: String, center: Center) {
        require(service.length in 1..256)
        if (records.size >= 64 && service !in records) return
        records[service] = center
    }
    fun lost(service: String) { records.remove(service) }
    fun clear() { records.clear() }
    fun centers(): List<Center> = records.values.distinct().sortedBy { it.name }
    fun ambiguous(id: String): Boolean = centers().filter { it.id == id }.map { it.endpoint }.distinct().size > 1
    fun rediscovered(id: String): Center? = centers().filter { it.id == id }.distinctBy { it.endpoint }.singleOrNull()
}

/** Notification buttons use observed state/capabilities, never toggle or replay. */
data class PendingPlayback(val playing: Boolean, val deadline: Long, val mediaId: String?) {
    fun sameSource(state: Playback): Boolean = state.available && mediaId == state.mediaId
}

data class Playback(
    val available: Boolean, val title: String = "", val playing: Boolean = false,
    val canPlay: Boolean = false, val canPause: Boolean = false,
    val canNext: Boolean = false, val canPrevious: Boolean = false,
    val mediaId: String? = null,
) {
    fun permits(action: String): Boolean = available && when (action) {
        "play" -> canPlay
        "pause" -> canPause
        "next" -> canNext
        "previous" -> canPrevious
        else -> false
    }
}
