package io.github.aadegtyarev.adlinuxtv.remote

import java.net.URI

/** Public package metadata only; no Android, credentials or callable bridge. */
internal class AppInfo private constructor(val version: String, val build: Int) {
    companion object {
        // Zero is not an installed versionCode: it represents unavailable/invalid metadata.
        fun read(packageInfo: () -> Pair<String?, Long>): AppInfo = try {
            val (version, build) = packageInfo()
            AppInfo(version?.takeIf { value ->
                value.length in 1..80 && value.isNotBlank() &&
                    value.none { it.isISOControl() || it.isSurrogate() }
            } ?: "unknown", build.takeIf { it in 1..Int.MAX_VALUE.toLong() }?.toInt() ?: 0)
        } catch (_: Exception) { AppInfo("unknown", 0) }

        fun mayInject(target: Target, selected: Target?, ownsPage: Boolean,
                      finishedUrl: String?, currentUrl: String?): Boolean {
            if (!ownsPage || selected != target || finishedUrl == null || finishedUrl != currentUrl) return false
            return runCatching {
                val uri = URI(finishedUrl)
                val endpoint = target.center.endpoint
                uri.scheme == endpoint.scheme && uri.rawUserInfo == null &&
                    Endpoint.privateAddress(requireNotNull(uri.host)) == endpoint.address &&
                    (if (uri.port == -1) { if (uri.scheme == "https") 443 else 80 } else uri.port) == endpoint.port &&
                    uri.rawPath == "/remote"
            }.getOrDefault(false)
        }
    }

    fun script(): String {
        // Escape every UTF-16 unit, including quotes, backslashes and JS/HTML delimiters.
        val escaped = version.map { "\\u" + it.code.toString(16).padStart(4, '0') }.joinToString("")
        // Immutable property + frozen scalars. Repeated page-finish callbacks are a no-op.
        return "(()=>{if(Object.prototype.hasOwnProperty.call(window,'adLinuxTvAppInfo'))return;" +
            "Object.defineProperty(window,'adLinuxTvAppInfo',{value:Object.freeze({version:\"$escaped\",build:$build})," +
            "writable:false,configurable:false,enumerable:true});})()"
    }
}
