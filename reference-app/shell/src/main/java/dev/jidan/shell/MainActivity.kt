package dev.jidan.shell

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
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
import android.view.WindowInsets
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.window.OnBackInvokedDispatcher
import dev.jidan.shell.accessibility.JidanAccessibilityService

class MainActivity : Activity(), SpeechController.Listener {
    private lateinit var root: FrameLayout
    private lateinit var statusDot: TextView
    private lateinit var statusTitle: TextView
    private lateinit var statusSubtitle: TextView
    private lateinit var input: EditText
    private lateinit var microphoneButton: ImageButton
    private lateinit var receiptLabel: TextView
    private lateinit var speech: SpeechController
    private lateinit var launcher: FrontDoorLauncher
    private lateinit var receipts: ReceiptStore
    private var receiptsHealthy = true
    private var resumeAutomationAfterSettings = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()

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
            setBackgroundColor(Color.rgb(11, 11, 15))
            setOnApplyWindowInsetsListener { view, insets ->
                applySystemBarInsets(view, insets)
            }
        }
        root.addView(buildTopBar())
        root.addView(buildCommandCenter())
        receiptLabel = textView("", 1f, Color.TRANSPARENT).apply {
            visibility = View.GONE
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        setContentView(root)
        root.requestApplyInsets()
    }

    private fun buildTopBar(): View {
        val bar = FrameLayout(this)
        statusDot = TextView(this).apply {
            text = "●"
            textSize = 13f
            setTextColor(Color.rgb(101, 212, 170))
            gravity = Gravity.CENTER
            contentDescription = "鸡蛋已就绪"
            visibility = View.GONE
        }
        bar.addView(Button(this).apply {
            setText(R.string.settings)
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.rgb(210, 210, 218))
            minWidth = dp(64)
            minHeight = dp(44)
            background = rounded(Color.rgb(29, 29, 34), dp(22), Color.rgb(62, 62, 70), dp(1))
            contentDescription = getString(R.string.settings)
            setOnClickListener { openAppSettings() }
        }, FrameLayout.LayoutParams(dp(72), dp(44), Gravity.END or Gravity.CENTER_VERTICAL))
        return bar.apply {
            layoutParams = FrameLayout.LayoutParams(match, dp(56), Gravity.TOP).apply {
                marginStart = dp(20)
                marginEnd = dp(20)
                topMargin = dp(8)
            }
        }
    }

    private fun buildCommandCenter(): View {
        val area = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        statusTitle = textView("", 18f, Color.WHITE, bold = true).apply {
            visibility = View.GONE
            gravity = Gravity.START
        }
        statusSubtitle = textView("", 14f, Color.rgb(174, 174, 184)).apply {
            visibility = View.GONE
            gravity = Gravity.START
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            setPadding(0, dp(5), 0, dp(18))
        }
        area.addView(statusTitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(statusSubtitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(buildInputBar(), LinearLayout.LayoutParams(match, dp(62)))

        val suggestionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, 0)
            addView(suggestionButton(R.string.try_alipay, "打开支付宝"))
            addView(suggestionButton(R.string.try_mobileanjian, "打开按键精灵"))
            addView(suggestionButton(R.string.try_hand_brain_lab, "开始手脑实验"))
        }
        area.addView(suggestionRow, LinearLayout.LayoutParams(match, wrap))

        return area.apply {
            layoutParams = FrameLayout.LayoutParams(match, wrap, Gravity.CENTER).apply {
                marginStart = dp(26)
                marginEnd = dp(26)
            }
        }
    }

    private fun buildInputBar(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), 0, dp(6), 0)
            background = rounded(Color.rgb(29, 29, 34), dp(31), INPUT_BORDER, dp(1))
        }
        input = EditText(this).apply {
            setHint(R.string.input_hint)
            setHintTextColor(Color.rgb(145, 145, 156))
            setTextColor(Color.WHITE)
            textSize = 17f
            maxLines = 2
            minHeight = dp(56)
            setSingleLine(false)
            background = null
            setPadding(dp(8), 0, dp(8), 0)
        }
        row.addView(input, LinearLayout.LayoutParams(0, match, 1f))
        microphoneButton = roundImageButton(R.drawable.ic_mic, R.string.microphone).apply {
            setOnClickListener { toggleSpeech() }
        }
        row.addView(microphoneButton, LinearLayout.LayoutParams(dp(48), dp(48)).apply {
            marginEnd = dp(4)
        })
        row.addView(roundImageButton(R.drawable.ic_arrow_up, R.string.submit).apply {
            setOnClickListener { submitText() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        return row
    }

    private fun submitText() {
        if (!receiptsHealthy) {
            showFailure("安全回执需要检查", "鸡蛋没有执行任何外部动作。")
            return
        }
        hideKeyboard()
        showStatus(
            getString(R.string.thinking),
            "安全的打开动作会直接交给安卓。",
            OrbMode.THINKING,
        )
        val parsed = LocalCommandParser.parse(input.text.toString())
        when (val directive = CommandDispatchPolicy.classify(parsed)) {
            is DispatchDirective.DirectNavigation -> dispatchProposal(directive.proposal)
            is DispatchDirective.SandboxExperiment -> dispatchProposal(directive.proposal)
            is DispatchDirective.DoNotDispatch -> showFailure(directive.title, directive.message)
        }
    }

    private fun dispatchProposal(proposal: ActionProposal) {
        val preparedHash = runCatching {
            receipts.append(proposal, "dispatch_prepared")
        }.getOrNull()
        if (preparedHash == null) {
            receiptsHealthy = false
            showFailure("动作意图没有记好", "鸡蛋没有把动作交给安卓，也不会自动重试。")
            return
        }
        receiptLabel.text = getString(R.string.receipt_format, preparedHash.take(8))
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
            is DispatchResult.NeedsAccessibility -> {
                resumeAutomationAfterSettings = true
                openAccessibilitySettings()
                Quadruple(
                    "blocked_by_os",
                    "正在接上“手”",
                    "请在系统页打开鸡蛋辅助操作；返回后会自动继续。",
                    OrbMode.THINKING,
                )
            }
        }
        val receiptHash = runCatching { receipts.append(proposal, status) }.getOrNull()
        if (receiptHash == null) {
            if (proposal.action == ShellAction.OPEN_AUTOMATION_LAB) {
                launcher.cancelActiveLab()
            }
            receiptsHealthy = false
            showFailure("结果回执没有写好", "动作结果未知；鸡蛋已停下且不会自动重试。")
            return
        }
        receiptLabel.text = getString(R.string.receipt_format, receiptHash.take(8))
        showStatus(title, message, mode)
    }

    private fun showFailure(title: String, message: String) {
        showStatus(title, message, OrbMode.FAILURE)
    }

    @Suppress("DEPRECATION")
    private fun configureSystemBars() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            window.statusBarColor = Color.TRANSPARENT
            window.navigationBarColor = Color.rgb(8, 7, 19)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.setDecorFitsSystemWindows(false)
        } else {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        }
    }

    @Suppress("DEPRECATION")
    private fun applySystemBarInsets(view: View, insets: WindowInsets): WindowInsets {
        val top: Int
        val bottom: Int
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bars = insets.getInsets(WindowInsets.Type.systemBars())
            top = bars.top
            bottom = bars.bottom
        } else {
            top = insets.systemWindowInsetTop
            bottom = insets.systemWindowInsetBottom
        }
        view.setPadding(0, top, 0, bottom)
        return insets
    }

    private fun showStatus(title: String, message: String, mode: OrbMode) {
        statusTitle.text = title
        statusSubtitle.text = message
        statusTitle.visibility = View.VISIBLE
        statusSubtitle.visibility = View.VISIBLE
        statusDot.setTextColor(
            when (mode) {
                OrbMode.SUCCESS -> Color.rgb(101, 212, 170)
                OrbMode.FAILURE -> Color.rgb(255, 111, 112)
                OrbMode.LISTENING -> Color.rgb(112, 177, 255)
                OrbMode.THINKING -> Color.rgb(196, 156, 255)
                OrbMode.IDLE -> Color.rgb(174, 174, 184)
            },
        )
        statusDot.contentDescription = title
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
        microphoneButton.setImageResource(R.drawable.ic_stop)
        showStatus(
            getString(R.string.listening),
            if (onDevice) {
                "这次使用手机上的离线识别服务。"
            } else {
                "这次由手机的语音服务识别，是否联网取决于手机设置。"
            },
            OrbMode.LISTENING,
        )
    }

    override fun onPartialText(text: String) {
        updateInputFromSpeech(text)
    }

    override fun onFinalText(text: String) {
        microphoneButton.setImageResource(R.drawable.ic_mic)
        updateInputFromSpeech(text)
        submitText()
    }

    override fun onSpeechFailure() {
        microphoneButton.setImageResource(R.drawable.ic_mic)
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

    private fun openAccessibilitySettings() {
        val service = ComponentName(this, JidanAccessibilityService::class.java)
        val details = Intent(ACTION_ACCESSIBILITY_DETAILS_SETTINGS).apply {
            putExtra(Intent.EXTRA_COMPONENT_NAME, service)
        }
        runCatching { startActivity(details) }
            .recoverCatching { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
            .onFailure {
                resumeAutomationAfterSettings = false
                showFailure("无障碍设置没有打开", "安卓没有提供可用的设置入口。")
            }
    }

    override fun onResume() {
        super.onResume()
        if (!resumeAutomationAfterSettings || !::root.isInitialized) return
        root.postDelayed({
            if (!resumeAutomationAfterSettings || isFinishing) return@postDelayed
            resumeAutomationAfterSettings = false
            if (dev.jidan.shell.accessibility.AccessibilityServiceBridge.connected) {
                input.setText("开始手脑实验")
                input.setSelection(input.length())
                submitText()
            } else {
                showFailure("“手”还没有接好", "没有执行任何动作；需要时再点一次手脑实验。")
            }
        }, 450L)
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
        microphoneButton.setImageResource(R.drawable.ic_mic)
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
        setTextColor(Color.rgb(216, 216, 224))
        minHeight = dp(48)
        background = rounded(Color.rgb(24, 24, 29), dp(22), Color.rgb(62, 62, 70), dp(1))
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

    private fun roundImageButton(icon: Int, description: Int): ImageButton = ImageButton(this).apply {
        setImageResource(icon)
        imageTintList = android.content.res.ColorStateList.valueOf(Color.rgb(242, 242, 247))
        scaleType = android.widget.ImageView.ScaleType.CENTER
        setPadding(dp(13), dp(13), dp(13), dp(13))
        background = rounded(Color.rgb(38, 38, 44), dp(26), Color.rgb(74, 74, 84), dp(1))
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
        private const val ACTION_ACCESSIBILITY_DETAILS_SETTINGS =
            "android.settings.ACCESSIBILITY_DETAILS_SETTINGS"
        private const val match = ViewGroup.LayoutParams.MATCH_PARENT
        private const val wrap = ViewGroup.LayoutParams.WRAP_CONTENT
        private val INPUT_BORDER = Color.rgb(74, 74, 84)
    }
}
