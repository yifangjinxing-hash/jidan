package dev.jidan.shell

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
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
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.window.OnBackInvokedDispatcher
import dev.jidan.shell.accessibility.JidanAccessibilityService
import dev.jidan.shell.accessibility.AccessibilityServiceBridge

class MainActivity : Activity(), SpeechController.Listener {
    private lateinit var root: FrameLayout
    private lateinit var statusDot: TextView
    private lateinit var statusTitle: TextView
    private lateinit var statusSubtitle: TextView
    private lateinit var input: EditText
    private lateinit var microphoneButton: ImageButton
    private lateinit var handButton: ImageButton
    private lateinit var receiptLabel: TextView
    private lateinit var speech: SpeechController
    private lateinit var launcher: FrontDoorLauncher
    private lateinit var receipts: ReceiptStore
    private var receiptsHealthy = true
    private var pendingProposalAfterSettings: ActionProposal? = null
    private var pendingProposalAfterPackageSource: ActionProposal? = null
    private var awaitingCompanionInstall = false
    private var resumedGeneration = 0L
    private var activeDailyRequestId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()

        speech = SpeechController(this, this)
        launcher = FrontDoorLauncher(this)
        receipts = ReceiptStore(this)
        receiptsHealthy = receipts.verify()
        activeDailyRequestId = savedInstanceState?.getString(STATE_DAILY_REQUEST_ID)
        awaitingCompanionInstall = savedInstanceState?.getBoolean(STATE_COMPANION_INSTALL) == true
        if (savedInstanceState?.getBoolean(STATE_PACKAGE_SOURCE_PENDING) == true) {
            pendingProposalAfterPackageSource =
                (LocalCommandParser.parse("打开按键精灵") as? ParseResult.Proposal)?.value
        }
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
            textSize = 12f
            setTextColor(Color.rgb(101, 212, 170))
            gravity = Gravity.CENTER
            contentDescription = "鸡蛋已就绪"
        }
        bar.addView(statusDot, FrameLayout.LayoutParams(dp(28), dp(44), Gravity.START or Gravity.CENTER_VERTICAL))
        bar.addView(ImageButton(this).apply {
            setImageResource(R.drawable.ic_settings)
            imageTintList = android.content.res.ColorStateList.valueOf(Color.rgb(210, 210, 218))
            scaleType = ImageView.ScaleType.CENTER
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = rounded(Color.rgb(29, 29, 34), dp(22), Color.rgb(62, 62, 70), dp(1))
            contentDescription = getString(R.string.settings)
            setOnClickListener { openAppSettings() }
        }, FrameLayout.LayoutParams(dp(44), dp(44), Gravity.END or Gravity.CENTER_VERTICAL))
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
        area.addView(ImageView(this).apply {
            setImageResource(R.drawable.jidan_hand_core_v1)
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = rounded(Color.rgb(5, 5, 8), dp(123), Color.TRANSPARENT, 0)
            clipToOutline = true
            contentDescription = getString(R.string.hand_center)
            setOnClickListener { showHandCenter() }
        }, LinearLayout.LayoutParams(dp(246), dp(246)).apply {
            bottomMargin = dp(6)
        })
        statusTitle = textView("", 18f, Color.WHITE, bold = true).apply {
            visibility = View.GONE
            gravity = Gravity.CENTER
        }
        statusSubtitle = textView("", 14f, Color.rgb(174, 174, 184)).apply {
            visibility = View.GONE
            gravity = Gravity.CENTER
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            setPadding(0, dp(4), 0, dp(12))
        }
        area.addView(statusTitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(statusSubtitle, LinearLayout.LayoutParams(match, wrap))
        area.addView(buildInputBar(), LinearLayout.LayoutParams(match, dp(62)))

        val suggestionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(20), dp(16), dp(20), 0)
            addView(quickAction(R.drawable.ic_pay, R.string.pay_short) {
                runCommand("打开支付宝")
            })
            addView(quickAction(R.drawable.ic_hand, R.string.hand_short) {
                showHandCenter()
            })
            addView(quickAction(R.drawable.ic_note, R.string.note_short) {
                runCommand("记下明天买鸡蛋")
            })
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
            is DispatchDirective.OwnedAppAction -> dispatchProposal(directive.proposal)
            is DispatchDirective.DoNotDispatch -> showFailure(directive.title, directive.message)
        }
    }

    private fun runCommand(command: String) {
        input.setText(command)
        input.setSelection(input.length())
        submitText()
    }

    private fun dispatchProposal(proposal: ActionProposal) {
        val dailyArguments = proposal.arguments as? ActionArguments.DailyNote
        if (proposal.action == ShellAction.CREATE_DAILY_NOTE && dailyArguments == null) {
            showFailure("待办没有准备好", "鸡蛋没有打开日常小事 App，也没有保存任何内容。")
            return
        }
        if (dailyArguments != null) activeDailyRequestId = dailyArguments.requestId
        val preparedHash = runCatching {
            receipts.append(proposal, "dispatch_prepared")
        }.getOrNull()
        if (preparedHash == null) {
            if (dailyArguments != null) activeDailyRequestId = null
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
                pendingProposalAfterSettings = proposal
                if (openAccessibilitySettings()) {
                    Quadruple(
                        "blocked_by_os",
                        "正在接上“手”",
                        "请在系统页打开鸡蛋辅助操作；返回后会自动继续。",
                        OrbMode.THINKING,
                    )
                } else {
                    pendingProposalAfterSettings = null
                    if (dailyArguments != null) activeDailyRequestId = null
                    Quadruple(
                        "blocked_by_os",
                        "无障碍设置没有打开",
                        "安卓没有提供可用的设置入口；没有执行任何动作。",
                        OrbMode.FAILURE,
                    )
                }
            }
            is DispatchResult.NeedsPackageSourcePermission -> {
                pendingProposalAfterPackageSource = proposal
                Quadruple(
                    "blocked_by_os",
                    getString(R.string.install_hand),
                    "",
                    OrbMode.THINKING,
                )
            }
            is DispatchResult.CompanionInstallStarted -> {
                awaitingCompanionInstall = true
                Quadruple(
                    "handoff_dispatched",
                    getString(R.string.installing_hand),
                    "",
                    OrbMode.THINKING,
                )
            }
        }
        if (
            dailyArguments != null &&
            result !is DispatchResult.Dispatched &&
            result !is DispatchResult.NeedsAccessibility
        ) {
            activeDailyRequestId = null
        }
        val receiptHash = runCatching { receipts.append(proposal, status) }.getOrNull()
        if (receiptHash == null) {
            if (
                proposal.action == ShellAction.OPEN_AUTOMATION_LAB ||
                proposal.action == ShellAction.CREATE_DAILY_NOTE
            ) {
                launcher.cancelActiveLab()
            }
            if (dailyArguments != null) activeDailyRequestId = null
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

    private fun openAccessibilitySettings(): Boolean {
        val service = ComponentName(this, JidanAccessibilityService::class.java)
        val details = Intent(ACTION_ACCESSIBILITY_DETAILS_SETTINGS).apply {
            putExtra(Intent.EXTRA_COMPONENT_NAME, service)
        }
        return runCatching { startActivity(details) }
            .recoverCatching { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
            .isSuccess
    }

    override fun onResume() {
        super.onResume()
        if (!::root.isInitialized) return
        resumedGeneration += 1
        refreshHandState()
        postWhileResumed(450L) { refreshHandState() }
        postWhileResumed(1_400L) { refreshHandState() }
        consumeDailyCompletionIfReady()
        resumeEmbeddedHandInstallIfReady()
        resolveCompanionInstallIfReady()
        val pending = pendingProposalAfterSettings ?: return
        postWhileResumed(450L) {
            if (pendingProposalAfterSettings !== pending) return@postWhileResumed
            pendingProposalAfterSettings = null
            if (AccessibilityServiceBridge.connected) {
                dispatchProposal(pending)
            } else {
                if (pending.arguments is ActionArguments.DailyNote) activeDailyRequestId = null
                showFailure("“手”还没有接好", "没有执行任何动作；接好后再试一次。")
            }
        }
    }

    private fun resumeEmbeddedHandInstallIfReady() {
        val pending = pendingProposalAfterPackageSource ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || packageManager.canRequestPackageInstalls()) {
            postWhileResumed(250L) {
                if (pendingProposalAfterPackageSource !== pending) return@postWhileResumed
                pendingProposalAfterPackageSource = null
                dispatchProposal(pending)
            }
        } else {
            pendingProposalAfterPackageSource = null
            showFailure(getString(R.string.hand_not_installed), "")
        }
    }

    private fun resolveCompanionInstallIfReady() {
        if (!awaitingCompanionInstall) return
        checkCompanionInstall(attempt = 0)
    }

    private fun checkCompanionInstall(attempt: Int) {
        postWhileResumed(if (attempt == 0) 250L else 400L) {
            if (!awaitingCompanionInstall) return@postWhileResumed
            if (launcher.isVerifiedMobileAnjianCandidateInstalled()) {
                awaitingCompanionInstall = false
                showStatus(getString(R.string.hand_installed), "", OrbMode.SUCCESS)
                refreshHandState()
            } else if (attempt < 9) {
                checkCompanionInstall(attempt + 1)
            } else {
                awaitingCompanionInstall = false
                showFailure(getString(R.string.hand_not_installed), "")
                refreshHandState()
            }
        }
    }

    private fun postWhileResumed(delayMs: Long, action: () -> Unit) {
        val generation = resumedGeneration
        root.postDelayed({
            if (
                generation == resumedGeneration &&
                !isFinishing &&
                (Build.VERSION.SDK_INT < Build.VERSION_CODES.JELLY_BEAN_MR1 || !isDestroyed)
            ) {
                action()
            }
        }, delayMs)
    }

    private fun refreshHandState() {
        val connected = AccessibilityServiceBridge.connected
        statusDot.setTextColor(
            if (connected) Color.rgb(101, 212, 170) else Color.rgb(112, 112, 122),
        )
        statusDot.contentDescription = if (connected) {
            getString(R.string.hand_connected)
        } else {
            getString(R.string.hand_disconnected)
        }
        if (::handButton.isInitialized) {
            handButton.background = rounded(
                if (connected) Color.rgb(28, 50, 43) else Color.rgb(30, 30, 36),
                dp(30),
                if (connected) Color.rgb(101, 212, 170) else Color.rgb(72, 72, 82),
                dp(1),
            )
        }
    }

    private fun showHandCenter() {
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24), dp(20), dp(24), dp(24))
            background = rounded(Color.rgb(20, 20, 25), dp(30), Color.rgb(70, 70, 80), dp(1))
        }
        panel.addView(ImageView(this).apply {
            setImageResource(R.drawable.jidan_hand_core_v1)
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = rounded(Color.rgb(5, 5, 8), dp(63), Color.TRANSPARENT, 0)
            clipToOutline = true
            contentDescription = getString(R.string.hand_center)
        }, LinearLayout.LayoutParams(dp(126), dp(126)))
        panel.addView(textView(getString(R.string.hand_center), 19f, Color.WHITE, bold = true).apply {
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(match, wrap).apply {
            bottomMargin = dp(16)
        })

        val choices = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val dialog = Dialog(this)
        choices.addView(handChoice(
            icon = R.drawable.ic_hand,
            label = getString(R.string.jidan_hand),
            active = AccessibilityServiceBridge.connected,
        ) {
            dialog.dismiss()
            if (AccessibilityServiceBridge.connected) {
                showStatus(getString(R.string.hand_connected), "", OrbMode.SUCCESS)
            } else if (openAccessibilitySettings()) {
                showStatus(getString(R.string.connect_hand), "", OrbMode.THINKING)
            } else {
                showFailure(getString(R.string.hand_disconnected), "")
            }
        })
        choices.addView(handChoice(
            icon = R.drawable.ic_gesture,
            label = getString(R.string.gesture_hand),
            active = launcher.isVerifiedMobileAnjianCandidateInstalled(),
        ) {
            dialog.dismiss()
            runCommand("打开按键精灵")
        })
        panel.addView(choices, LinearLayout.LayoutParams(match, wrap))

        dialog.setContentView(panel)
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setDimAmount(0.6f)
            addFlags(android.view.WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setLayout(match, wrap)
            setGravity(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
        }
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setLayout(match, wrap)
            setGravity(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
        }
    }

    private fun handChoice(
        icon: Int,
        label: String,
        active: Boolean,
        onClick: () -> Unit,
    ): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        isClickable = true
        isFocusable = true
        contentDescription = label
        setPadding(dp(8), dp(8), dp(8), dp(8))
        addView(ImageButton(this@MainActivity).apply {
            setImageResource(icon)
            imageTintList = android.content.res.ColorStateList.valueOf(Color.WHITE)
            setPadding(dp(17), dp(17), dp(17), dp(17))
            background = rounded(
                if (active) Color.rgb(28, 50, 43) else Color.rgb(34, 34, 40),
                dp(32),
                if (active) Color.rgb(101, 212, 170) else Color.rgb(72, 72, 82),
                dp(1),
            )
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(dp(64), dp(64)))
        addView(textView(label, 13f, Color.rgb(215, 215, 224)).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(7), 0, 0)
        }, LinearLayout.LayoutParams(match, wrap))
        setOnClickListener { onClick() }
        layoutParams = LinearLayout.LayoutParams(0, wrap, 1f).apply {
            marginStart = dp(8)
            marginEnd = dp(8)
        }
    }

    private fun consumeDailyCompletionIfReady() {
        val requestId = activeDailyRequestId ?: return
        val completion = AccessibilityServiceBridge.consumeDailyCompletion(requestId) ?: return
        activeDailyRequestId = null
        if (
            completion.noteSha256 != ActionProposal.sha256(completion.noteText) ||
            !completion.receiptHash.matches(Regex("^[0-9a-f]{64}$"))
        ) {
            showFailure("保存结果无法核对", "鸡蛋没有把这次结果显示成已保存，也不会自动重试。")
            return
        }
        receiptLabel.text = getString(R.string.receipt_format, completion.receiptHash.take(8))
        showStatus(
            "已经记下",
            if (completion.navigationAccepted) {
                completion.noteText
            } else {
                "${completion.noteText}\n内容已经保存；这次返回动作由你手动完成。"
            },
            OrbMode.SUCCESS,
        )
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        activeDailyRequestId?.let { outState.putString(STATE_DAILY_REQUEST_ID, it) }
        outState.putBoolean(STATE_COMPANION_INSTALL, awaitingCompanionInstall)
        outState.putBoolean(
            STATE_PACKAGE_SOURCE_PENDING,
            pendingProposalAfterPackageSource?.action == ShellAction.OPEN_MOBILEANJIAN,
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

    override fun onPause() {
        resumedGeneration += 1
        super.onPause()
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

    private fun quickAction(icon: Int, label: Int, onClick: () -> Unit): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            val button = ImageButton(this@MainActivity).apply {
                setImageResource(icon)
                imageTintList = android.content.res.ColorStateList.valueOf(Color.WHITE)
                scaleType = ImageView.ScaleType.CENTER
                setPadding(dp(16), dp(16), dp(16), dp(16))
                background = rounded(Color.rgb(30, 30, 36), dp(30), Color.rgb(72, 72, 82), dp(1))
                contentDescription = getString(label)
                setOnClickListener { onClick() }
            }
            if (label == R.string.hand_short) handButton = button
            addView(button, LinearLayout.LayoutParams(dp(60), dp(60)))
            addView(textView(getString(label), 12f, Color.rgb(190, 190, 200)).apply {
                gravity = Gravity.CENTER
                setPadding(0, dp(6), 0, 0)
            }, LinearLayout.LayoutParams(match, wrap))
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(0, wrap, 1f)
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
        private const val STATE_DAILY_REQUEST_ID = "daily_request_id"
        private const val STATE_COMPANION_INSTALL = "companion_install"
        private const val STATE_PACKAGE_SOURCE_PENDING = "package_source_pending"
    }
}
