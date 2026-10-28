package io.github.aadegtyarev.adlinuxtv.remote

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.os.Build
import android.text.TextUtils
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Presentation only. No discovery, authorization or endpoint selection logic. */
internal object RemoteUi {
    val ink = 0xffeaf6ff.toInt()
    val muted = 0xffbdd3e5.toInt()
    val cyan = 0xff7ed8ff.toInt()
    fun dp(context: Context, value: Int) = (value * context.resources.displayMetrics.density + 0.5f).toInt()

    fun background(context: Context, fill: Int): GradientDrawable = GradientDrawable().apply {
        setColor(fill); cornerRadius = dp(context, 18).toFloat()
        setStroke(dp(context, 1), 0xff4f6b85.toInt())
    }

    fun action(context: Context, label: String, clicked: () -> Unit): Button = Button(context).apply {
        text = label; textSize = 15f; minHeight = dp(context, 48)
        isAllCaps = false; setTextColor(ink)
        setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
        backgroundTintList = null; stateListAnimator = null; elevation = 0f
        background = StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed), RemoteUi.background(context, 0xff257fa4.toInt()))
            addState(intArrayOf(), RemoteUi.background(context, 0xff243a53.toInt()))
        }
        setOnClickListener { clicked() }
    }

    fun card(context: Context, name: String, origin: String, state: String, online: Boolean,
             enabled: Boolean, clicked: () -> Unit, held: () -> Unit): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(context, 16), dp(context, 14), dp(context, 16), dp(context, 14))
        background = RemoteUi.background(context, 0xff1d2f45.toInt())
        minimumHeight = dp(context, 88)
        contentDescription = "$name. $origin. $state"
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        fun line(value: String, size: Float, color: Int, bold: Boolean = false): TextView = TextView(context).apply {
            text = value; textSize = size; setTextColor(color); maxLines = 2
            ellipsize = TextUtils.TruncateAt.END
            if (bold) setTypeface(typeface, Typeface.BOLD)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        addView(line(name, 17f, ink, true))
        addView(line(origin, 13f, muted), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(context, 5) })
        addView(line(state, 12f, if (online) cyan else muted), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(context, 4) })
        isEnabled = enabled; isFocusable = true; alpha = if (enabled) 1f else 0.5f
        setOnClickListener { if (isEnabled) clicked() }
        setOnLongClickListener { if (isEnabled) { held(); true } else false }
    }

    fun applyInsets(view: View, insets: WindowInsets): WindowInsets {
        if (Build.VERSION.SDK_INT < 30) return insets
        val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
        val keyboard = insets.getInsets(WindowInsets.Type.ime())
        view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, keyboard.bottom))
        // The root already applies these insets. Forwarding them to WebView
        // counts status/navigation bars again in CSS env(safe-area-inset-*).
        return WindowInsets.CONSUMED
    }
}
