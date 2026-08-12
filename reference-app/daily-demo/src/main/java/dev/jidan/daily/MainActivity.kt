package dev.jidan.daily.demo

import android.app.Activity
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.text.Editable
import android.text.InputFilter
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsetsController
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.util.UUID

class MainActivity : Activity() {
    private lateinit var store: DailyTaskStore
    private lateinit var root: LinearLayout
    private lateinit var input: EditText
    private lateinit var automationStatus: TextView
    private lateinit var automationResult: TextView
    private lateinit var summary: TextView
    private lateinit var clearCompleted: Button
    private lateinit var list: LinearLayout
    private var tasks: List<DailyTask> = emptyList()
    private var sessionNonce: String = ""
    private var requestId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        bindAutomationIntent(intent)
        store = DailyTaskStore(this)
        tasks = store.load()
        setContentView(buildInterface())
        configureWindow()
        renderTasks()
        resetAutomationState()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        bindAutomationIntent(intent)
        tasks = store.load()
        renderTasks()
        input.text?.clear()
        resetAutomationState()
    }

    private fun bindAutomationIntent(intent: Intent?) {
        sessionNonce = intent
            ?.getStringExtra(DailyAutomationContract.SESSION_NONCE_EXTRA)
            .orEmpty()
        requestId = intent
            ?.getStringExtra(DailyAutomationContract.REQUEST_ID_EXTRA)
            ?.trim()
            ?.takeIf(String::isNotBlank)
    }

    private fun resetAutomationState() {
        val emptyMarker = DailyAutomationContract.emptyMarker(sessionNonce)
        setAutomationState("等待输入事项", emptyMarker)
        automationResult.text = "尚未保存"
        automationResult.contentDescription = emptyMarker
    }

    override fun onResume() {
        super.onResume()
        if (!::store.isInitialized || !::list.isInitialized) return
        val latest = store.load()
        if (latest != tasks) {
            tasks = latest
            renderTasks()
        }
    }

    private fun buildInterface(): LinearLayout = LinearLayout(this).apply {
        id = R.id.daily_root
        root = this
        orientation = LinearLayout.VERTICAL
        setPadding(dp(22), dp(22), dp(22), dp(12))
        setBackgroundColor(PAGE_COLOR)

        addView(text("小事清单", 30f, bold = true).apply {
            id = R.id.daily_title
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) isAccessibilityHeading = true
        })

        val inputLabel = text("新增事项", 14f, bold = true).apply {
            id = R.id.daily_input_label
            labelFor = R.id.daily_note_input
            setTextColor(SECONDARY_TEXT_COLOR)
        }
        addView(inputLabel, LinearLayout.LayoutParams(match, wrap).apply {
            topMargin = dp(24)
            bottomMargin = dp(8)
        })

        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL

            input = EditText(this@MainActivity).apply {
                id = R.id.daily_note_input
                hint = "写下一件小事"
                textSize = 17f
                setTextColor(PRIMARY_TEXT_COLOR)
                setHintTextColor(HINT_COLOR)
                setSingleLine(true)
                imeOptions = EditorInfo.IME_ACTION_DONE
                filters = arrayOf(InputFilter.LengthFilter(MAX_TITLE_LENGTH))
                setPadding(dp(16), 0, dp(16), 0)
                background = roundedBackground(Color.WHITE, 16f, BORDER_COLOR)
                setOnEditorActionListener { _, actionId, _ ->
                    if (actionId == EditorInfo.IME_ACTION_DONE) {
                        addTask()
                        true
                    } else {
                        false
                    }
                }
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(
                        value: CharSequence?,
                        start: Int,
                        count: Int,
                        after: Int,
                    ) = Unit

                    override fun onTextChanged(
                        value: CharSequence?,
                        start: Int,
                        before: Int,
                        count: Int,
                    ) {
                        val note = value?.toString()?.trim().orEmpty()
                        if (note.isBlank()) {
                            setAutomationState(
                                "等待输入事项",
                                DailyAutomationContract.emptyMarker(sessionNonce),
                            )
                        } else {
                            setAutomationState(
                                "事项已写好，可以保存",
                                DailyAutomationContract.noteReadyMarker(sessionNonce, note),
                            )
                        }
                    }

                    override fun afterTextChanged(value: Editable?) = Unit
                })
            }
            addView(input, LinearLayout.LayoutParams(0, dp(54), 1f))

            addView(Button(this@MainActivity).apply {
                id = R.id.daily_note_save
                text = "保存"
                isAllCaps = false
                textSize = 16f
                setTextColor(Color.WHITE)
                backgroundTintList = ColorStateList.valueOf(ACCENT_COLOR)
                setOnClickListener { addTask() }
            }, LinearLayout.LayoutParams(dp(76), dp(54)).apply {
                leftMargin = dp(10)
            })
        }, LinearLayout.LayoutParams(match, wrap))

        automationStatus = text("等待输入事项", 13f).apply {
            id = R.id.daily_note_status
            setTextColor(SECONDARY_TEXT_COLOR)
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        addView(automationStatus, LinearLayout.LayoutParams(match, wrap).apply {
            topMargin = dp(10)
        })

        automationResult = text("尚未保存", 13f).apply {
            id = R.id.daily_note_result
            setTextColor(SECONDARY_TEXT_COLOR)
        }
        addView(automationResult, LinearLayout.LayoutParams(match, wrap).apply {
            topMargin = dp(4)
        })

        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL

            summary = text("", 15f, bold = true).apply {
                id = R.id.daily_task_summary
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            }
            addView(summary, LinearLayout.LayoutParams(0, wrap, 1f))

            clearCompleted = Button(this@MainActivity).apply {
                id = R.id.daily_task_clear_completed
                text = "清空已完成"
                isAllCaps = false
                textSize = 14f
                minHeight = 0
                minimumHeight = 0
                minWidth = 0
                minimumWidth = 0
                setPadding(dp(12), dp(8), dp(12), dp(8))
                backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
                setTextColor(ACCENT_COLOR)
                setOnClickListener { clearCompletedTasks() }
            }
            addView(clearCompleted, LinearLayout.LayoutParams(wrap, wrap))
        }, LinearLayout.LayoutParams(match, wrap).apply {
            topMargin = dp(22)
            bottomMargin = dp(8)
        })

        addView(ScrollView(this@MainActivity).apply {
            id = R.id.daily_task_scroll
            isFillViewport = true
            clipToPadding = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS

            list = LinearLayout(this@MainActivity).apply {
                id = R.id.daily_task_list
                orientation = LinearLayout.VERTICAL
                setPadding(0, 0, 0, dp(18))
            }
            addView(list, ViewGroup.LayoutParams(match, wrap))
        }, LinearLayout.LayoutParams(match, 0, 1f))
    }

    private fun addTask() {
        val title = input.text?.toString()?.trim().orEmpty()
        if (title.isBlank()) {
            input.error = "请先写下一件小事"
            input.requestFocus()
            return
        }

        val result = store.add(
            task = DailyTask(
                id = UUID.randomUUID().toString(),
                title = title,
                completed = false,
                createdAtEpochMs = System.currentTimeMillis(),
            ),
            requestId = requestId,
        )
        tasks = result.tasks
        renderTasks()
        when (result.status) {
            DailyTaskAddStatus.DUPLICATE -> {
                input.text?.clear()
                markSaved(title, duplicate = true)
                return
            }
            DailyTaskAddStatus.CONFLICT -> {
                setAutomationState(
                    "这个请求已经保存过另一条事项，未重复执行",
                    DailyAutomationContract.marker(
                        sessionNonce,
                        "request_conflict:${result.noteDigest}",
                    ),
                )
                automationResult.text = "没有新增事项"
                return
            }
            DailyTaskAddStatus.SAVE_FAILED -> {
                setAutomationState(
                    "保存失败，事项没有落盘",
                    DailyAutomationContract.marker(
                        sessionNonce,
                        "save_failed:${result.noteDigest}",
                    ),
                )
                automationResult.text = "没有新增事项"
                return
            }
            DailyTaskAddStatus.ADDED -> {
                input.text?.clear()
                markSaved(title, duplicate = false)
            }
        }
    }

    private fun setTaskCompleted(taskId: String, completed: Boolean) {
        applySaveResult(store.setCompleted(taskId, completed))
    }

    private fun clearCompletedTasks() {
        val result = store.clearCompleted()
        if (result.changedCount == 0) {
            if (!result.saved) showSaveFailure()
            return
        }
        if (applySaveResult(result)) {
            Toast.makeText(
                this,
                "已清空 ${result.changedCount} 个完成事项",
                Toast.LENGTH_SHORT,
            ).show()
        }
    }

    private fun applySaveResult(result: DailyTaskSaveResult): Boolean {
        tasks = result.tasks
        renderTasks()
        if (!result.saved) {
            showSaveFailure()
            return false
        }
        return true
    }

    private fun showSaveFailure() {
        Toast.makeText(this, "没有保存成功，请重试", Toast.LENGTH_SHORT).show()
    }

    @Suppress("DEPRECATION")
    private fun markSaved(title: String, duplicate: Boolean) {
        val marker = DailyAutomationContract.savedMarker(sessionNonce, title)
        setAutomationState(if (duplicate) "这件事已经保存过" else "已经保存到本机", marker)
        automationResult.text = if (duplicate) "已保存过：$title" else "刚刚保存：$title"
        automationResult.contentDescription = marker
        root.announceForAccessibility(if (duplicate) "这件事已经保存过" else "已保存：$title")
    }

    private fun setAutomationState(message: String, marker: String) {
        if (!::automationStatus.isInitialized) return
        automationStatus.text = message
        automationStatus.contentDescription = marker
    }

    private fun renderTasks() {
        val remaining = DailyTaskLogic.remainingCount(tasks)
        val completed = tasks.size - remaining
        summary.text = when {
            tasks.isEmpty() -> "还没有事项"
            remaining == 0 -> "今天都完成了"
            else -> "$remaining 件待完成"
        }
        clearCompleted.isEnabled = completed > 0
        clearCompleted.alpha = if (completed > 0) 1f else 0.38f

        list.removeAllViews()
        if (tasks.isEmpty()) {
            list.addView(text("写下一件小事，保存后会留在这台手机里。", 16f).apply {
                id = R.id.daily_task_empty
                gravity = Gravity.CENTER
                setTextColor(SECONDARY_TEXT_COLOR)
                setPadding(dp(18), dp(54), dp(18), dp(54))
            }, LinearLayout.LayoutParams(match, wrap))
            return
        }

        tasks.forEach { task -> list.addView(taskRow(task), taskRowParams()) }
    }

    private fun taskRow(task: DailyTask): LinearLayout = LinearLayout(this).apply {
        id = R.id.daily_task_row
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dp(12), dp(8), dp(12), dp(8))
        background = roundedBackground(Color.WHITE, 16f, BORDER_COLOR)
        setTag(R.id.daily_task_item_key, task.id)

        addView(CheckBox(this@MainActivity).apply {
            id = R.id.daily_task_toggle
            text = task.title
            textSize = 17f
            setTextColor(PRIMARY_TEXT_COLOR)
            buttonTintList = ColorStateList.valueOf(ACCENT_COLOR)
            gravity = Gravity.CENTER_VERTICAL
            minHeight = dp(52)
            isChecked = task.completed
            paintFlags = if (task.completed) {
                paintFlags or Paint.STRIKE_THRU_TEXT_FLAG
            } else {
                paintFlags and Paint.STRIKE_THRU_TEXT_FLAG.inv()
            }
            alpha = if (task.completed) 0.56f else 1f
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                stateDescription = if (task.completed) "已完成" else "未完成"
            }
            setOnCheckedChangeListener { _, checked ->
                setTaskCompleted(task.id, checked)
            }
        }, LinearLayout.LayoutParams(match, wrap))
    }

    private fun taskRowParams(): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(match, wrap).apply { bottomMargin = dp(10) }

    @Suppress("DEPRECATION")
    private fun configureWindow() {
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            window.statusBarColor = PAGE_COLOR
            window.navigationBarColor = PAGE_COLOR
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val lightBars =
                WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
            window.insetsController?.setSystemBarsAppearance(lightBars, lightBars)
        } else {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        }
    }

    private fun text(value: String, size: Float, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = value
            textSize = size
            setTextColor(PRIMARY_TEXT_COLOR)
            if (bold) setTypeface(typeface, Typeface.BOLD)
        }

    private fun roundedBackground(fill: Int, radiusDp: Float, stroke: Int): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fill)
            cornerRadius = dp(radiusDp).toFloat()
            setStroke(dp(1), stroke)
        }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun dp(value: Float): Int = (value * resources.displayMetrics.density).toInt()

    private companion object {
        const val MAX_TITLE_LENGTH = 200
        const val PAGE_COLOR = 0xFFF6F6F8.toInt()
        const val PRIMARY_TEXT_COLOR = 0xFF1C1C1E.toInt()
        const val SECONDARY_TEXT_COLOR = 0xFF68686E.toInt()
        const val HINT_COLOR = 0xFF8A8A90.toInt()
        const val BORDER_COLOR = 0xFFE1E1E6.toInt()
        const val ACCENT_COLOR = 0xFF315BD7.toInt()
        const val match = ViewGroup.LayoutParams.MATCH_PARENT
        const val wrap = ViewGroup.LayoutParams.WRAP_CONTENT
    }
}
