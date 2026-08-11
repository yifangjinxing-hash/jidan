package dev.jidan.accessibility.sandbox

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsetsController
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.security.MessageDigest

/**
 * A deliberately isolated fixture for exercising sensitive UI automation.
 *
 * It has no INTERNET permission, accepts only same-signature callers and never
 * creates an order or moves money. Passwords and OTPs live only in the current
 * process and are cleared after a synthetic commit.
 */
class MainActivity : Activity() {
    private val watchdog = Handler(Looper.getMainLooper())
    private lateinit var recipient: EditText
    private lateinit var amount: EditText
    private lateinit var password: EditText
    private lateinit var otp: EditText
    private lateinit var status: TextView
    private lateinit var result: TextView
    private val launchNonce: String by lazy {
        intent?.getStringExtra(EXTRA_SESSION_NONCE).orEmpty().ifBlank { "unarmed" }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildInterface())
        // Android 17 can return no WindowInsetsController until the decor view exists.
        configureSystemBars()
        watchdog.postDelayed({
            if (
                ::status.isInitialized &&
                status.contentDescription?.toString()?.endsWith("|lab_idle") == true
            ) {
                setStatus("鸡蛋的手没有响应，实验已经停下", "executor_unavailable")
            }
        }, FIRST_ACTION_TIMEOUT_MS)
    }

    @Suppress("DEPRECATION")
    private fun configureSystemBars() {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            window.statusBarColor = Color.rgb(246, 246, 248)
            window.navigationBarColor = Color.rgb(246, 246, 248)
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            val lightBars =
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(lightBars, lightBars)
        } else {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
    }

    private fun buildInterface(): ScrollView = ScrollView(this).apply {
        setBackgroundColor(Color.rgb(246, 246, 248))
        importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(28), dp(24), dp(28))

            addView(label("手 + 脑实验室", 28f, bold = true))
            addView(label("这是隔离的假支付页：0 元真实资金、0 个真实账户、0 次联网。", 15f).apply {
                setTextColor(Color.rgb(88, 88, 94))
                setPadding(0, dp(8), 0, dp(22))
            })

            recipient = field(R.id.lab_recipient, "虚构收款人", InputType.TYPE_CLASS_TEXT)
            amount = field(
                R.id.lab_amount,
                "虚构金额",
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            )
            password = field(
                R.id.lab_password,
                "假支付密码",
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD,
            )
            otp = field(
                R.id.lab_otp,
                "假验证码",
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD,
            )

            addView(recipient, fieldParams())
            addView(amount, fieldParams())
            addView(password, fieldParams())
            addView(otp, fieldParams())

            status = label("等待鸡蛋观察页面", 14f).apply {
                id = R.id.lab_status
                contentDescription = sessionMarker("lab_idle")
                setTextColor(Color.rgb(88, 88, 94))
                setPadding(0, dp(10), 0, dp(10))
            }
            addView(status)

            addView(Button(this@MainActivity).apply {
                id = R.id.lab_submit
                text = "提交假实验"
                isAllCaps = false
                textSize = 17f
                minHeight = dp(52)
                setOnClickListener { syntheticCommit() }
            }, LinearLayout.LayoutParams(match, dp(58)))

            addView(Button(this@MainActivity).apply {
                id = R.id.lab_reset
                text = "清空重来"
                isAllCaps = false
                setOnClickListener { reset() }
            }, LinearLayout.LayoutParams(match, dp(52)).apply {
                topMargin = dp(8)
            })

            result = label("尚未提交", 18f, bold = true).apply {
                id = R.id.lab_result
                contentDescription = "not_committed"
                gravity = Gravity.CENTER
                setPadding(0, dp(24), 0, 0)
            }
            addView(result)
        }, ViewGroup.LayoutParams(match, wrap))

        recipient.watch("recipient_ready")
        amount.watch("amount_ready")
        password.watch("password_ready")
        otp.watch("otp_ready")
    }

    private fun syntheticCommit() {
        if (listOf(recipient, amount, password, otp).any { it.text.isNullOrBlank() }) {
            setStatus("还有实验字段未填写", "fields_missing")
            return
        }
        result.text = "实验完成：外部交易 0 笔"
        result.contentDescription = "synthetic_committed"
        setStatus("动作链已完成，真实世界没有变化", "synthetic_committed")
        password.text?.clear()
        otp.text?.clear()
    }

    private fun reset() {
        recipient.text?.clear()
        amount.text?.clear()
        password.text?.clear()
        otp.text?.clear()
        setStatus("等待鸡蛋观察页面", "lab_idle")
        result.text = "尚未提交"
        result.contentDescription = "not_committed"
    }

    private fun EditText.watch(marker: String) {
        addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(value: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(value: CharSequence?, start: Int, before: Int, count: Int) {
                if (!value.isNullOrBlank()) {
                    setStatus(marker, marker)
                }
            }
            override fun afterTextChanged(value: Editable?) = Unit
        })
    }

    private fun field(idValue: Int, hintValue: String, inputTypeValue: Int): EditText =
        EditText(this).apply {
            id = idValue
            hint = hintValue
            inputType = inputTypeValue
            textSize = 17f
            minHeight = dp(54)
            setPadding(dp(12), 0, dp(12), 0)
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            isSaveEnabled = false
            isSaveFromParentEnabled = false
        }

    override fun onStop() {
        clearTransientFields()
        super.onStop()
    }

    override fun onDestroy() {
        watchdog.removeCallbacksAndMessages(null)
        clearTransientFields()
        super.onDestroy()
    }

    private fun clearTransientFields() {
        if (!::recipient.isInitialized) return
        recipient.text?.clear()
        amount.text?.clear()
        password.text?.clear()
        otp.text?.clear()
    }

    private fun setStatus(message: String, marker: String) {
        status.text = message
        status.contentDescription = sessionMarker(marker)
    }

    private fun sessionMarker(marker: String): String =
        "$SESSION_MARKER_PREFIX${sha256(launchNonce)}|$marker"

    private fun sha256(value: String): String = MessageDigest
        .getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

    private fun fieldParams(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(match, dp(58)).apply { bottomMargin = dp(10) }

    private fun label(value: String, size: Float, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(Color.rgb(25, 25, 28))
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val EXTRA_SESSION_NONCE = "dev.jidan.extra.ACCESSIBILITY_LAB_SESSION_NONCE"
        private const val SESSION_MARKER_PREFIX = "jidan_lab_session:"
        private const val FIRST_ACTION_TIMEOUT_MS = 3_500L
        private const val match = ViewGroup.LayoutParams.MATCH_PARENT
        private const val wrap = ViewGroup.LayoutParams.WRAP_CONTENT
    }
}
