package io.orion.desktop

import android.os.Bundle
import android.view.View
import androidx.activity.enableEdgeToEdge
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)

    val content = findViewById<View>(android.R.id.content)
    val systemInsets = WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
    ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
      // Some Android WebViews report zero CSS safe-area insets while the bars
      // still cover the app. Keep the WebView inside the tappable screen area.
      val bars = insets.getInsets(systemInsets)
      view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
      // Leave IME insets available so the WebView can still resize its viewport.
      WindowInsetsCompat.Builder(insets).setInsets(systemInsets, Insets.NONE).build()
    }
    ViewCompat.requestApplyInsets(content)
  }
}
