package dev.jidan.shell

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.window.OnBackInvokedDispatcher

class MainActivity : Activity(), SpeechController.Listener {
    private lateinit var root: FrameLayout
    private lateinit var orb: JidanOrbView
    private lateinit var statusTitle: TextView
    private lateinit var statusSubtitle: TextView
    private lateinit var input: EditText
    private lateinit var microphoneButton: Button
    private lateinit var receiptLabel: TextView
    private lateinit var speech: SpeechController
    private lateinit var launcher: FrontDoorLauncher
    private lateinit var receipts: ReceiptStore
    private var receiptsHealthy = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.rgb(8, 7, 19)
        window.decorView.systemUiVisibility =
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN

        speech = SpeechController(this, this)
        launcher = FrontDoorLauncher(this)
        receipts = ReceiptStore(this)
        receiptsHealthy = receipts.verify()
        buildInterface()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(
                OnBackInvokedDispatcher.PRIORITY_DEFAULT,
            ) { handleBack() }
        }
        if (!receiptsHealthy) {
            showFailure(
                "安全回执需要检查",
                "本机回执链不完整。鸡蛋已经停下，不会打开外部应用。",
            )
        }
    }

    private fun buildInterface() {
        root = FrameLayout(this).apply {
            setBackgroundColor(Color.rgb(5, 5, 16))
            setOnApplyWindowInsetsListener { view, insets ->
                view.setPadding(
                    0,
                    insets.systemWindowInsetTop,
                    0,
                    insets.systemWindowInsetBottom,
                )
                insets
            }
        }
        root.addView(ImageView(this).apply {
            setImageResource(R.drawable.jidan_cosmos)
            scaleType = ImageView.ScaleType.CENTER_CROP
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, matchFrame())
        root.addView(View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(
                    Color.argb(90, 2, 3, 12),
                    Color.argb(12, 6, 5, 18),
                    Color.argb(125, 5, 4, 15),
                ),
            )
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, matchFrame())

        root.addView(buildTopBar())
        root.addView(buildOrb())
        root.addView(buildBottomArea())
        root.addView(buildFooter())
        setContentView(root)
        root.requestApplyInsets()
    }

    private fun buildTopBar(): View {
        val bar = FrameLayout(this)
        val brand = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(textView(getString(R.string.brand_name), 26f, Color.WHITE, bold = true))
            addView(textView(getString(R.string.prototype_badge), 12f, SOFT_TEXT))
        }
        bar.addView(brand, FrameLayout.LayoutParams(wrap, wrap, Gravity.START or Gravity.CENTER_VERTICAL))
        bar.addView(Button(this).apply {
            setText(R.string.settings)
            textSize = 14f
            isAllCaps = false
            setTextColor(Color.WHITE)
            minWidth = dp(64)
            minHeight = dp(48)
            background = rounded(Color.argb(72, 255, 255, 255), dp(24), SOFT_BORDER, dp(1))
            contentDescription = getString(R.string.settings)
            setOnClickListener { openAppSettings() }
        }, FrameLayout.LayoutParams(dp(76), dp(48), Gravity.END or Gravity.CENTER_VERTICAL))
        return bar.apply {
            layoutParams = FrameLayout.LayoutParams(match, dp(68), Gravity.TOP).apply {
                marginStart = dp(24)
                marginEnd = dp(24)
                topMargin = dp(12)
            }
        }
    }

    private fun buildOrb(): View {
        val container = FrameLayout(this)
        orb = JidanOrbView(this)
        container.addView(orb, matchFrame())
        container.addView(TextView(this).apply {
            setText(R.string.orb_greeting)
            textSize = 20f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setShadowLayer(12f, 0f, 2f, Color.rgb(83, 55, 140))
            contentDescription = getString(R.string.orb_greeting)
        }, matchFrame())
        return container.apply {
            layoutParams = FrameLayout.LayoutParams(dp(270), dp(270), Gravity.CENTER)
            translationY = -dp(54).toFloat()
        }
    }

    private fun buildBottomArea(): View {
        val area = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        statusTitle = textView(getString(R.string.idle_title), 23f, Color.WHITE, bold = true).apply {
            gravity = Gravity.CENTER
        }
        statusSubtitle = textView(getString(R.string.idle_subtitle), 16f, SOFT_TEXT).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(14))
        }
        area.addView(statusTitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(statusSubtitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(buildInputBar(), LinearLayout.LayoutParams(match, dp(66)))

        val suggestionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, 0)
            addView(suggestionButton(R.string.try_alipay, "打开支付宝"))
            addView(suggestionButton(R.string.try_settings, "打开系统设置"))
        }
        area.addView(suggestionRow, LinearLayout.LayoutParams(match, wrap))
        area.addView(textView(getString(R.string.privacy_short), 12f, MUTED_TEXT).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, 0)
        }, LinearLayout.LayoutParams(match, wrap))

        return area.apply {
            layoutParams = FrameLayout.LayoutParams(match, wrap, Gravity.BOTTOM).apply {
                marginStart = dp(22)
                marginEnd = dp(22)
                bottomMargin = dp(78)
            }
        }
    }

    private fun buildInputBar(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), 0, dp(7), 0)
            background = rounded(Color.argb(165, 13, 12, 32), dp(33), INPUT_BORDER, dp(1))
        }
        input = EditText(this).apply {
            setHint(R.string.input_hint)
            setHintTextColor(Color.argb(165, 235, 229, 247))
            setTextColor(Color.WHITE)
            textSize = 18f
            maxLines = 2
            minHeight = dp(56)
            setSingleLine(false)
            background = null
            setPadding(dp(8), 0, dp(8), 0)
        }
        row.addView(input, LinearLayout.LayoutParams(0, match, 1f))
        microphoneButton = roundActionButton("🎙", R.string.microphone).apply {
            setOnClickListener { toggleSpeech() }
        }
        row.addView(microphoneButton, LinearLayout.LayoutParams(dp(52), dp(52)).apply {
            marginEnd = dp(4)
        })
        row.addView(roundActionButton("→", R.string.submit).apply {
            setOnClickListener { submitText() }
        }, LinearLayout.LayoutParams(dp(52), dp(52)))
        return row
    }

    private fun buildFooter(): View {
        val footer = FrameLayout(this)
        footer.addView(TextView(this).apply {
            text = "◉  ∞"
            textSize = 19f
            setTextColor(Color.rgb(181, 225, 213))
            gravity = Gravity.CENTER
            background = rounded(Color.argb(80, 8, 25, 28), dp(26), Color.rgb(76, 140, 127), dp(1))
            contentDescription = getString(R.string.local_mode)
        }, FrameLayout.LayoutParams(dp(92), dp(48), Gravity.START or Gravity.CENTER_VERTICAL))
        receiptLabel = textView("•   0001", 12f, Color.argb(150, 230, 222, 241)).apply {
            gravity = Gravity.CENTER
        }
        footer.addView(receiptLabel, FrameLayout.LayoutParams(dp(120), dp(48), Gravity.CENTER))
        footer.addView(Button(this).apply {
            text = "?"
            textSize = 20f
            setTextColor(Color.WHITE)
            background = rounded(Color.argb(95, 31, 28, 50), dp(26), SOFT_BORDER, dp(1))
            contentDescription = getString(R.string.help)
            setOnClickListener { showHelp() }
        }, FrameLayout.LayoutParams(dp(52), dp(48), Gravity.END or Gravity.CENTER_VERTICAL))
        return footer.apply {
            layoutParams = FrameLayout.LayoutParams(match, dp(52), Gravity.BOTTOM).apply {
                marginStart = dp(24)
                marginEnd = dp(24)
                bottomMargin = dp(12)
            }
        }
    }

    private fun submitText() {
        if (!receiptsHealthy) {
            showFailure("安全回执需要检查", "鸡蛋没有执行任何外部动作。")
            return
        }
        hideKeyboard()
        orb.setMode(OrbMode.THINKING)
        statusTitle.text = getString(R.string.thinking)
        statusSubtitle.text = "安全的打开动作会直接交给安卓。"
        val parsed = LocalCommandParser.parse(input.text.toString())
        when (val directive = CommandDispatchPolicy.classify(parsed)) {
            is DispatchDirective.DirectNavigation -> dispatchProposal(directive.proposal)
            is DispatchDirective.DoNotDispatch -> showFailure(directive.title, directive.message)
        }
    }

    private fun dispatchProposal(proposal: ActionProposal) {
        val result = launcher.dispatch(proposal)
        val (status, title, message, mode) = when (result) {
            is DispatchResult.Dispatched -> Quadruple(
                "handoff_dispatched",
                "已经交给安卓",
                result.message,
                OrbMode.SUCCESS,
            )
            is DispatchResult.TargetUnavailable -> Quadruple(
                "target_unavailable",
                "没有打开",
                result.message,
                OrbMode.FAILURE,
            )
            is DispatchResult.Blocked -> Quadruple(
                "blocked_by_os",
                "安全停下了",
                result.message,
                OrbMode.FAILURE,
            )
        }
        val receiptHash = runCatching { receipts.append(proposal, status) }.getOrNull()
        if (receiptHash == null) {
            receiptsHealthy = false
            showFailure("回执没有写好", "鸡蛋不会自动重试。请先检查本机数据。")
            return
        }
        receiptLabel.text = getString(R.string.receipt_format, receiptHash.take(8))
        orb.setMode(mode)
        statusTitle.text = title
        statusSubtitle.text = message
    }

    private fun showFailure(title: String, message: String) {
        orb.setMode(OrbMode.FAILURE)
        statusTitle.text = title
        statusSubtitle.text = message
        statusSubtitle.announceForAccessibility("$title。$message")
    }

    private fun toggleSpeech() {
        if (speech.isListening) {
            speech.stop()
            return
        }
        if (!speech.isAvailable()) {
            showFailure("语音暂不可用", getString(R.string.speech_unavailable))
            return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            speech.start()
        } else {
            showMicrophoneExplanation()
        }
    }

    private fun showMicrophoneExplanation() {
        AlertDialog.Builder(this)
            .setTitle(R.string.audio_permission_title)
            .setMessage(R.string.audio_permission_body)
            .setNegativeButton(R.string.type_instead, null)
            .setPositiveButton(R.string.allow_microphone) { _, _ ->
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO)
            }
            .show()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_AUDIO && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            speech.start()
        } else if (requestCode == REQUEST_AUDIO) {
            showFailure("没有麦克风权限", "没关系，你还可以打字告诉我。")
        }
    }

    override fun onListeningStarted(onDevice: Boolean) {
        microphoneButton.text = "■"
        orb.setMode(OrbMode.LISTENING)
        statusTitle.text = getString(R.string.listening)
        statusSubtitle.text = if (onDevice) {
            "这次使用手机上的离线识别服务。"
        } else {
            "这次由手机的语音服务识别，是否联网取决于手机设置。"
        }
    }

    override fun onPartialText(text: String) {
        updateInputFromSpeech(text)
    }

    override fun onFinalText(text: String) {
        microphoneButton.text = "🎙"
        updateInputFromSpeech(text)
        submitText()
    }

    override fun onSpeechFailure() {
        microphoneButton.text = "🎙"
        showFailure("没有听清", getString(R.string.speech_error))
    }

    private fun updateInputFromSpeech(text: String) {
        input.setText(text)
        input.setSelection(input.length())
    }

    private fun openAppSettings() {
        startActivity(
            Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.parse("package:$packageName"),
            ),
        )
    }

    private fun showHelp() {
        AlertDialog.Builder(this)
            .setTitle(R.string.help_title)
            .setMessage(R.string.help_body)
            .setPositiveButton(R.string.close, null)
            .show()
    }

    private fun hideKeyboard() {
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager)
            .hideSoftInputFromWindow(input.windowToken, 0)
        input.clearFocus()
    }

    override fun onStop() {
        speech.destroy()
        microphoneButton.text = "🎙"
        super.onStop()
    }

    override fun onDestroy() {
        speech.destroy()
        super.onDestroy()
    }

    @SuppressLint("GestureBackNavigation")
    @Deprecated("Only used on Android 12L and older; newer versions use OnBackInvokedDispatcher")
    override fun onBackPressed() {
        handleBack()
    }

    private fun handleBack() {
        finishAfterTransition()
    }

    private fun suggestionButton(label: Int, command: String): View = Button(this).apply {
        setText(label)
        textSize = 13f
        isAllCaps = false
        setTextColor(Color.rgb(226, 220, 240))
        minHeight = dp(48)
        background = rounded(Color.argb(72, 31, 27, 52), dp(22), SOFT_BORDER, dp(1))
        setOnClickListener {
            input.setText(command)
            input.setSelection(input.length())
            submitText()
        }
        layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply {
            marginStart = dp(4)
            marginEnd = dp(4)
        }
    }

    private fun roundActionButton(symbol: String, description: Int): Button = Button(this).apply {
        text = symbol
        textSize = 21f
        setTextColor(Color.WHITE)
        minWidth = 0
        minHeight = 0
        setPadding(0, 0, 0, 0)
        background = rounded(Color.argb(118, 37, 31, 68), dp(26), Color.argb(95, 213, 202, 242), dp(1))
        contentDescription = getString(description)
    }

    private fun textView(value: String, size: Float, color: Int, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }

    private fun rounded(fill: Int, radius: Int, stroke: Int, strokeWidth: Int): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fill)
            cornerRadius = radius.toFloat()
            if (strokeWidth > 0) setStroke(strokeWidth, stroke)
        }

    private fun matchFrame(): FrameLayout.LayoutParams =
        FrameLayout.LayoutParams(match, match)

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private data class Quadruple(
        val status: String,
        val title: String,
        val message: String,
        val mode: OrbMode,
    )

    companion object {
        private const val REQUEST_AUDIO = 501
        private const val match = ViewGroup.LayoutParams.MATCH_PARENT
        private const val wrap = ViewGroup.LayoutParams.WRAP_CONTENT
        private val SOFT_TEXT = Color.rgb(221, 214, 235)
        private val MUTED_TEXT = Color.argb(165, 210, 203, 221)
        private val SOFT_BORDER = Color.argb(95, 219, 208, 239)
        private val INPUT_BORDER = Color.rgb(172, 160, 204)
    }
}
