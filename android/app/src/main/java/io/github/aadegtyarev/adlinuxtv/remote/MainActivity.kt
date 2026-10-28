package io.github.aadegtyarev.adlinuxtv.remote

import android.app.Activity
import android.app.AlertDialog
import android.Manifest
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.CheckBox
import androidx.core.content.ContextCompat
import android.content.pm.PackageManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.webkit.ProfileStore
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.google.zxing.integration.android.IntentIntegrator
import java.io.ByteArrayInputStream
import java.net.InetAddress
import java.net.URI

class MainActivity : Activity() {
    private lateinit var store: CenterStore
    private lateinit var discovery: Discovery
    private lateinit var content: FrameLayout
    private lateinit var status: TextView
    private lateinit var centerTitle: TextView
    private lateinit var switchCenter: Button
    private var page: WebView? = null
    private var shown: Target? = null
    private var found = emptyList<Center>()
    private var lookup = 0L
    private var unavailable = false
    private var connectingCenter = false
    private var pickerRequested = false
    private var activityForeground = false
    private var pageReady: Target? = null
    private val notificationRequest = 47
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        if (Build.VERSION.SDK_INT >= 30) window.setDecorFitsSystemWindows(false)
        store = CenterStore(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = android.graphics.drawable.GradientDrawable(
                android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
                intArrayOf(0xff1d3048.toInt(), 0xff10151f.toInt()))
        }
        root.setOnApplyWindowInsetsListener { view, insets -> RemoteUi.applyInsets(view, insets) }
        val bar = LinearLayout(this).apply { setPadding(dp(12), 0, dp(4), 0); gravity = android.view.Gravity.CENTER_VERTICAL }
        centerTitle = TextView(this).apply {
            textSize = 13f; maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END
        }
        bar.addView(centerTitle, LinearLayout.LayoutParams(0, -2, 1f))
        val settings = Button(this, null, android.R.attr.borderlessButtonStyle).apply {
            text = "⚙"; contentDescription = "Настройки медиакнопок"; textSize = 18f
            minHeight = dp(48); minimumWidth = dp(40); setPadding(0, 0, 0, 0)
            setTextColor(0xff7ed8ff.toInt()); setOnClickListener { mediaSettings() }
        }
        bar.addView(settings, LinearLayout.LayoutParams(dp(40), dp(48)))
        switchCenter = Button(this, null, android.R.attr.borderlessButtonStyle).apply {
            text = "Сменить медиацентр"; textSize = 14f; isAllCaps = false; maxLines = 1
            minHeight = dp(48); minimumWidth = 0; setPadding(dp(8), 0, dp(8), 0)
            setTextColor(0xff7ed8ff.toInt()); setOnClickListener { picker(true) }
        }
        bar.addView(switchCenter, LinearLayout.LayoutParams(-2, dp(48)))
        root.addView(bar, LinearLayout.LayoutParams(-1, dp(48)))
        status = TextView(this).apply { textSize = 13f; setTextColor(RemoteUi.muted); setPadding(dp(14), dp(4), dp(14), dp(4)) }
        root.addView(status)
        content = FrameLayout(this)
        root.addView(content, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        discovery = Discovery(this) { centers, message ->
            found = centers
            if (shown == null) { if (!connectingCenter) renderPicker(message) }
            else {
                val current = shown ?: return@Discovery
                val matches = centers.filter { it.id == current.center.id }.distinctBy { it.endpoint }
                if (matches.size == 1 && matches[0].endpoint != current.center.endpoint) {
                    // Discovery is correlation, not authentication. New origin needs explicit
                    // confirmation and its own empty/persisted profile, never bearer migration.
                    status.text = "Найден новый адрес. Выберите медиацентр заново."
                    status.visibility = View.VISIBLE
                }
            }
        }
        val explicitPicker = state?.getBoolean("picker_requested", false) == true
        picker(false)
        startupCenter(store.all(), store.last(), explicitPicker)?.let { connect(it.endpoint.origin, it.id) }
    }

    private fun mediaSettings() {
        val prefs = getSharedPreferences("remote", MODE_PRIVATE)
        val enabled = CheckBox(this).apply { text = "Медиакнопки в шторке"; isChecked = prefs.getBoolean(MediaOptIn.PREFERENCE, false) }
        AlertDialog.Builder(this).setTitle("Медиакнопки") .setView(enabled)
            .setMessage("Показывайте кнопки управления текущим медиацентром в системной шторке.")
            .setPositiveButton("Сохранить") { _, _ ->
                if (!enabled.isChecked) {
                    prefs.edit().putBoolean(MediaOptIn.PREFERENCE, false).apply()
                    stopService(Intent(this, RemoteMediaService::class.java))
                } else if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), notificationRequest)
                } else {
                    prefs.edit().putBoolean(MediaOptIn.PREFERENCE, true).apply(); syncMediaService()
                }
            }.setNegativeButton("Отмена", null).show()
    }

    private fun showMediaPermissionMessage() {
        AlertDialog.Builder(this).setMessage("Разрешите уведомления в настройках Android, чтобы включить медиакнопки. Сейчас они не работают.")
            .setPositiveButton("Понятно", null).show()
    }

    private fun notificationBlocked(): Boolean {
        val manager = getSystemService(android.app.NotificationManager::class.java)
        return !manager.areNotificationsEnabled() || manager.getNotificationChannel("remote-media")?.importance == android.app.NotificationManager.IMPORTANCE_NONE
    }

    private fun syncMediaService() {
        val granted = Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        val selected = ActiveCenter.selection.target()
        val target = shown?.takeIf { it == selected && pageReady == it && page != null }
        val enabled = getSharedPreferences("remote", MODE_PRIVATE).getBoolean(MediaOptIn.PREFERENCE, false)
        if (!granted || notificationBlocked()) {
            stopService(Intent(this, RemoteMediaService::class.java))
            if (enabled && activityForeground && target != null) {
                status.text = if (!granted) "Медиакнопки не работают: разрешите уведомления в настройках Android." else "Медиакнопки не работают: включите уведомления приложения и канал «Управление телевизором» в настройках Android."
                status.visibility = View.VISIBLE
            }
            return
        }
        if (MediaOptIn.mayConnect(enabled, granted, activityForeground, target)) {
            val current = ActiveCenter.media
            if (!MediaOptIn.needsConnect(target!!, current?.target, current?.owns(target) == true)) return
            try {
                ContextCompat.startForegroundService(this, Intent(this, RemoteMediaService::class.java).setAction(RemoteMediaService.CONNECT).putExtra("epoch", target.epoch))
            } catch (_: RuntimeException) {
                stopService(Intent(this, RemoteMediaService::class.java))
                status.text = "Не удалось включить медиакнопки. Попробуйте снова при открытом пульте."
                status.visibility = View.VISIBLE
            }
        }
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density + 0.5f).toInt()
    private fun button(label: String, clicked: () -> Unit) = RemoteUi.action(this, label, clicked)

    private fun suspendPage() {
        page?.let { view ->
            // Fixed application lifecycle hook, not a bridge accepting arbitrary JavaScript.
            view.evaluateJavascript("window.adLinuxTvRemoteLifecycle?.suspend()", null)
            view.stopLoading(); view.onPause()
            (view.parent as? ViewGroup)?.removeView(view)
            view.destroy()
        }
        page = null; shown = null; pageReady = null
    }

    private fun revoke() {
        lookup += 1
        ActiveCenter.revoke()
        stopService(Intent(this, RemoteMediaService::class.java))
        suspendPage()
    }

    private fun picker(disconnect: Boolean) {
        connectingCenter = false
        pickerRequested = true
        if (disconnect) revoke() else { lookup += 1; suspendPage() }
        unavailable = false
        renderPicker("")
        discovery.start()
    }

    private fun renderPicker(message: String) {
        if (shown != null) return
        connectingCenter = false
        pickerRequested = true
        centerTitle.text = "AD·TV"
        centerTitle.setTextColor(RemoteUi.cyan)
        switchCenter.visibility = View.GONE
        status.visibility = if (message.isBlank()) View.GONE else View.VISIBLE
        status.text = message
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(8), dp(14), dp(16)) }
        val heading = LinearLayout(this).apply { gravity = android.view.Gravity.CENTER_VERTICAL }
        heading.addView(TextView(this).apply { text = "Медиацентры"; textSize = 23f; setTextColor(RemoteUi.ink) }, LinearLayout.LayoutParams(0, -2, 1f))
        heading.addView(button("Обновить") { discovery.start() })
        list.addView(heading)
        val actions = LinearLayout(this)
        actions.addView(button("Ввести адрес") { manual() }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(8) })
        actions.addView(button("Сканировать QR") {
            IntentIntegrator(this).setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                .setPrompt("QR с экрана медиацентра").setBeepEnabled(false).setOrientationLocked(false).initiateScan()
        }, LinearLayout.LayoutParams(0, -2, 1f))
        list.addView(actions, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12); bottomMargin = dp(2) })
        val centers = pickerCenters(found, store.all())
        if (centers.isEmpty()) list.addView(TextView(this).apply {
            text = "Пока ничего не найдено. Можно ввести адрес или открыть QR с телевизора."
            textSize = 14f; setTextColor(RemoteUi.muted); setPadding(0, dp(20), 0, dp(8))
        })
        centers.forEach { center ->
            val conflict = found.filter { it.id == center.id }.map { it.endpoint }.distinct().size > 1
            val online = found.any { it.id == center.id && it.endpoint == center.endpoint }
            val name = "${center.name}${if (store.last() == center.id) " ★" else ""}"
            val availability = if (conflict) "Конфликт ID — проверьте конфигурации" else if (online) "Найден в сети" else "Сохранён — проверить подключение"
            val card = RemoteUi.card(this, name, center.endpoint.origin, availability, online, !conflict,
                clicked = { connect(center.endpoint.origin, center.id) },
                held = {
                    AlertDialog.Builder(this@MainActivity).setMessage("Удалить сохранённый медиацентр?")
                        .setPositiveButton("Удалить") { _, _ -> store.forget(center.id); renderPicker("") }
                        .setNegativeButton("Отмена", null).show()
                })
            list.addView(card, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        }
        val scroll = ScrollView(this).apply { addView(list) }
        content.removeAllViews(); content.addView(scroll)
    }

    private fun manual(initial: String = "") {
        val input = EditText(this).apply {
            setSingleLine(); textSize = 20f; minHeight = dp(56)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            hint = "192.168.1.20:8765"; setText(initial)
        }
        AlertDialog.Builder(this).setTitle("Адрес в домашней сети").setView(input)
            .setPositiveButton("Подключиться") { _, _ -> connect(input.text.toString(), null) }
            .setNegativeButton("Отмена", null).show()
    }

    private fun connect(raw: String, expected: String?, confirmedOrigin: String? = null) {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.MULTI_PROFILE)) {
            AlertDialog.Builder(this).setMessage("Обновите Android System WebView: нужны отдельные профили авторизации. Общие cookies использовать небезопасно.")
                .setPositiveButton("Понятно", null).show(); return
        }
        revoke()
        val generation = ++lookup
        connectingCenter = true
        pickerRequested = false
        switchCenter.visibility = View.VISIBLE
        content.removeAllViews()
        content.addView(android.widget.ProgressBar(this), FrameLayout.LayoutParams(-2, -2, android.view.Gravity.CENTER))
        status.visibility = View.VISIBLE
        status.text = "Подключение…"
        try {
            Network.io.execute {
                val result = runCatching {
                    val endpoint = Endpoint.parse(raw) { host ->
                        InetAddress.getAllByName(host).mapNotNull { it.hostAddress }
                    }
                    Network.identity(endpoint, expected)
                }
                runOnUiThread {
                    if (generation != lookup || isFinishing || isDestroyed) return@runOnUiThread
                    result.onSuccess { center ->
                        val saved = store.all().find { it.id == center.id }
                        if (saved != null && saved.endpoint != center.endpoint && confirmedOrigin != center.endpoint.origin) {
                            AlertDialog.Builder(this).setTitle("Новый адрес медиацентра")
                                .setMessage("${center.name}\n${saved.endpoint.origin} → ${center.endpoint.origin}\n\nИспользовать новый адрес? Авторизация для него отдельная; cookies не переносятся. ID — не сертификат подлинности устройства.")
                                .setPositiveButton("Использовать") { _, _ ->
                                    if (generation == lookup) connect(center.endpoint.origin, center.id, center.endpoint.origin)
                                }.setNegativeButton("Отмена") { _, _ ->
                                    if (generation == lookup) renderPicker("Адрес не изменён")
                                }.show()
                            return@onSuccess
                        }
                        if (runCatching { store.save(center) }.isFailure) {
                            renderPicker("Не удалось сохранить центр. Удалите ненужные записи (максимум64).")
                            return@onSuccess
                        }
                        val target = ActiveCenter.selection.select(center)
                        showRemote(target)
                    }.onFailure { renderPicker("Не удалось проверить этот медиацентр. Проверьте адрес, сеть и сервер с настроенным discovery ID.") }
                }
            }
        } catch (_: RuntimeException) { renderPicker("Подключение занято; попробуйте позже") }
    }

    private fun sameOrigin(url: String, center: Center): Boolean = runCatching {
        val uri = URI(url)
        val scheme = when (uri.scheme) { "ws" -> "http"; "wss" -> "https"; else -> uri.scheme }
        scheme == center.endpoint.scheme && uri.rawUserInfo == null &&
                Endpoint.privateAddress(requireNotNull(uri.host)) == center.endpoint.address &&
                (if (uri.port == -1) { if (scheme == "https") 443 else 80 } else uri.port) == center.endpoint.port
    }.getOrDefault(false)

    @Suppress("SetJavaScriptEnabled", "DEPRECATION")
    private fun showRemote(target: Target) {
        shown = target; unavailable = false
        connectingCenter = false; pickerRequested = false
        switchCenter.visibility = View.VISIBLE
        centerTitle.setTextColor(RemoteUi.muted)
        val center = target.center
        val generation = lookup
        val appInfo = AppInfo.read {
            val info = packageManager.getPackageInfo(packageName, 0)
            info.versionName to info.longVersionCode
        }
        val view = WebView(this)
        // Must occur before loading any page; never use the process-wide default profile.
        WebViewCompat.setProfile(view, center.profile)
        val profile = ProfileStore.getInstance().getOrCreateProfile(center.profile)
        profile.cookieManager.setAcceptCookie(true)
        profile.cookieManager.setAcceptThirdPartyCookies(view, false)
        view.settings.apply {
            javaScriptEnabled = true; domStorageEnabled = true
            // Rem-based layout and container breakpoints must scale WITH text,
            // not just paint larger glyphs into fixed-width old button columns.
            defaultFontSize = (16 * resources.configuration.fontScale).toInt().coerceIn(16, 32)
            textZoom = 100
            allowFileAccess = false; allowContentAccess = false
            allowFileAccessFromFileURLs = false; allowUniversalAccessFromFileURLs = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false; setSupportMultipleWindows(false)
            mediaPlaybackRequiresUserGesture = true
        }
        view.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) { request.deny() }
        }
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean =
                !ActiveCenter.selection.accepts(target) || !sameOrigin(request.url.toString(), center) ||
                        request.url.path !in listOf("/remote", "/")
            override fun shouldInterceptRequest(v: WebView, request: WebResourceRequest): WebResourceResponse? =
                if (ActiveCenter.selection.accepts(target) && sameOrigin(request.url.toString(), center)) null
                else WebResourceResponse("text/plain", "UTF-8", ByteArrayInputStream(ByteArray(0)))
            override fun onReceivedSslError(v: WebView, handler: SslErrorHandler, error: SslError) { handler.cancel() }
            override fun onPageStarted(v: WebView, url: String?, icon: Bitmap?) {
                if (url == null || !sameOrigin(url, center)) v.stopLoading()
            }
            override fun onPageFinished(v: WebView, url: String?) {
                if (AppInfo.mayInject(target, ActiveCenter.selection.target(),
                        page === v && shown == target && generation == lookup && !isFinishing && !isDestroyed,
                        url, v.url)) {
                    v.evaluateJavascript(appInfo.script(), null)
                }
                if (ActiveCenter.selection.accepts(target) && url != null && sameOrigin(url, center)) {
                    profile.cookieManager.flush()
                    centerTitle.text = center.name
                    pageReady = target
                    if (!unavailable && !(getSharedPreferences("remote", MODE_PRIVATE).getBoolean(MediaOptIn.PREFERENCE, false) && notificationBlocked())) status.visibility = View.GONE
                    syncMediaService()
                }
            }
            override fun onReceivedError(v: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && ActiveCenter.selection.accepts(target)) {
                    unavailable = true
                    status.text = "${center.name} недоступен. Проверьте подключение."
                    status.visibility = View.VISIBLE
                }
            }
        }
        content.removeAllViews(); content.addView(view)
        page = view
        pageReady = null
        centerTitle.text = center.name
        status.visibility = View.GONE
        view.loadUrl(center.endpoint.remote + "#device=" + center.id)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("picker_requested", pickerRequested)
        super.onSaveInstanceState(outState)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == notificationRequest) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
                getSharedPreferences("remote", MODE_PRIVATE).edit().putBoolean(MediaOptIn.PREFERENCE, true).apply(); syncMediaService()
            } else {
                getSharedPreferences("remote", MODE_PRIVATE).edit().putBoolean(MediaOptIn.PREFERENCE, false).apply()
                stopService(Intent(this, RemoteMediaService::class.java)); showMediaPermissionMessage()
            }
        }
    }

    @Deprecated("Activity result API supported for the embedded scanner")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val scanned = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (scanned?.contents != null) manual(scanned.contents)
    }
    @Deprecated("Back navigation remains available on API28+")
    override fun onBackPressed() { if (shown != null || connectingCenter) picker(true) else super.onBackPressed() }
    override fun onPause() { activityForeground = false; page?.onPause(); super.onPause() }
    override fun onResume() {
        super.onResume()
        activityForeground = true
        if (getSharedPreferences("remote", MODE_PRIVATE).getBoolean(MediaOptIn.PREFERENCE, false) && Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            status.text = "Медиакнопки выключены: разрешите уведомления в настройках Android."
            status.visibility = View.VISIBLE
            stopService(Intent(this, RemoteMediaService::class.java))
        } else syncMediaService()
        if (shown?.let { !ActiveCenter.selection.accepts(it) } == true) picker(true)
        syncMediaService()
        page?.onResume()
        page?.evaluateJavascript("window.adLinuxTvRemoteLifecycle?.resume?.()", null)
    }
    override fun onDestroy() {
        lookup += 1; discovery.stop(); suspendPage()
        if (ActiveCenter.media == null) ActiveCenter.selection.revoke()
        super.onDestroy()
    }
}
