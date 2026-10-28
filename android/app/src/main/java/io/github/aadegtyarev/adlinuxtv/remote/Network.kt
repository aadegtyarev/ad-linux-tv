package io.github.aadegtyarev.adlinuxtv.remote

import okhttp3.Call
import okhttp3.CookieJar
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

object Network {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS).readTimeout(5, TimeUnit.SECONDS)
        .callTimeout(7, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
        .cookieJar(CookieJar.NO_COOKIES).build()
    val io = ThreadPoolExecutor(2, 2, 0, TimeUnit.SECONDS, ArrayBlockingQueue(8))

    fun body(call: Call): JSONObject = call.execute().use { response ->
        require(response.code == 200)
        val body = requireNotNull(response.body)
        require(body.contentLength() <= 8192)
        val output = ByteArrayOutputStream()
        body.byteStream().use { input ->
            val buffer = ByteArray(1024)
            while (true) {
                val count = input.read(buffer)
                if (count == -1) break
                require(output.size() + count <= 8192)
                output.write(buffer, 0, count)
            }
        }
        JSONObject(output.toString("UTF-8"))
    }

    fun identity(endpoint: Endpoint, expectedId: String? = null): Center {
        val json = body(client.newCall(Request.Builder().url(endpoint.origin + "/api/device").build()))
        require(json.getString("app") == "ad-linux-tv" && json.getInt("protocol") == 1 &&
                json.getString("remote_path") == "/remote" && json.getInt("port") == endpoint.port)
        val center = Center(json.getString("id"), json.getString("name"), endpoint)
        require(expectedId == null || center.id == expectedId)
        return center
    }
}
