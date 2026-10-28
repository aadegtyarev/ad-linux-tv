package io.github.aadegtyarev.adlinuxtv.remote

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Nonsecret favorites only. Cookies live exclusively in isolated WebView profiles. */
class CenterStore(context: Context) {
    private val prefs = context.getSharedPreferences("centers", Context.MODE_PRIVATE)
    fun all(): List<Center> {
        val raw = prefs.getString("items", "[]") ?: "[]"
        if (raw.length > 49152) return emptyList()
        return runCatching {
            val items = JSONArray(raw)
            (0 until minOf(items.length(), 64)).mapNotNull { index ->
                runCatching {
                    val item = items.getJSONObject(index)
                    Center(item.getString("id"), item.getString("name"), Endpoint.parse(item.getString("origin")))
                }.getOrNull()
            }.distinctBy { it.id }
        }.getOrDefault(emptyList())
    }
    fun save(center: Center) {
        val values = all().filter { it.id != center.id } + center
        require(values.size <= 64)
        val array = JSONArray()
        values.forEach { array.put(JSONObject().put("id", it.id).put("name", it.name).put("origin", it.endpoint.origin)) }
        prefs.edit().putString("items", array.toString()).putString("last", center.id).apply()
    }
    fun last(): String? = prefs.getString("last", null)
    fun forget(id: String) {
        val array = JSONArray()
        all().filter { it.id != id }.forEach {
            array.put(JSONObject().put("id", it.id).put("name", it.name).put("origin", it.endpoint.origin))
        }
        prefs.edit().putString("items", array.toString()).apply()
    }
}

object ActiveCenter {
    val selection = Selection()
    // Lifecycle callbacks and assignments occur on Android's main thread.
    val observers = mutableSetOf<() -> Unit>()
    @Volatile var media: MediaConnection? = null
        set(value) { field = value; changed() }
    fun changed() { observers.toList().forEach { it() } }
    fun revoke() { selection.revoke(); media?.close(); media = null }
}
