package io.github.aadegtyarev.adlinuxtv.remote

import android.app.Application
import android.graphics.Insets
import android.graphics.drawable.AdaptiveIconDrawable
import android.view.WindowInsets
import android.widget.LinearLayout
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30])
class RemoteUiTest {
    private val app: Application get() = RuntimeEnvironment.getApplication()

    @Test fun nativeButtonsKeepCompactTouchTargetAndReadableCase() {
        val button = RemoteUi.action(app, "Добавить") {}
        assertEquals("Добавить", button.text.toString())
        assertEquals(RemoteUi.dp(app, 48), button.minHeight)
        assertNotNull(button.background)
    }

    @Test fun centerCardHasNameOriginAndAccessibleStatus() {
        var clicks = 0
        val card = RemoteUi.card(app, "Гостиная", "http://tv.example:8765", "Доступен", true, true,
            { clicks++ }, {})
        val labels = (card as LinearLayout).let { root ->
            (0 until root.childCount).map { root.getChildAt(it) }.filterIsInstance<TextView>()
        }
        assertEquals(listOf("Гостиная", "http://tv.example:8765", "Доступен"), labels.map { it.text.toString() })
        assertTrue(labels.first().textSize > labels[1].textSize)
        card.performClick()
        assertEquals(1, clicks)
        assertTrue(card.contentDescription.toString().contains("Гостиная"))
    }

    @Test fun rootConsumesBarsCutoutAndImeOnce() {
        val root = LinearLayout(app)
        val insets = WindowInsets.Builder()
            .setInsets(WindowInsets.Type.systemBars(), Insets.of(2, 24, 3, 32))
            .setInsets(WindowInsets.Type.ime(), Insets.of(0, 0, 0, 200))
            .build()
        val consumed = RemoteUi.applyInsets(root, insets)
        assertTrue(consumed.isConsumed)
        assertEquals(2, root.paddingLeft)
        assertEquals(24, root.paddingTop)
        assertEquals(3, root.paddingRight)
        assertEquals(200, root.paddingBottom)
    }

    @Test fun launcherUsesAdaptiveIconRatherThanLegacyWhiteWrapper() {
        assertTrue(app.getDrawable(R.mipmap.ic_launcher) is AdaptiveIconDrawable)
    }
}
