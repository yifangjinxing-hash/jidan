package dev.jidan.reference

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.text.BidiFormatter
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import dev.jidan.reference.appfunctions.MemoStore
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var stateView: TextView
    private lateinit var memoHeaderView: TextView
    private lateinit var memoView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val density = resources.displayMetrics.density
        val padding = (24 * density).toInt()
        val smallPadding = (14 * density).toInt()
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPaddingRelative(padding, padding, padding, padding)
        }
        content.addView(TextView(this).apply {
            setText(R.string.screen_title)
            textSize = 28f
            setTypeface(typeface, Typeface.BOLD)
        })
        content.addView(TextView(this).apply {
            setText(R.string.screen_subtitle)
            textSize = 16f
            setTextColor(Color.DKGRAY)
            setPaddingRelative(0, padding / 2, 0, padding)
        })
        stateView = TextView(this).apply {
            textSize = 17f
            setTextIsSelectable(true)
            textDirection = View.TEXT_DIRECTION_FIRST_STRONG
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            )
        }
        content.addView(stateView)
        memoHeaderView = TextView(this).apply {
            setText(R.string.memo_header)
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.rgb(25, 90, 65))
            setPaddingRelative(0, padding, 0, smallPadding)
        }
        content.addView(memoHeaderView)
        memoView = TextView(this).apply {
            textSize = 21f
            setTextColor(Color.BLACK)
            setTextIsSelectable(true)
            textDirection = View.TEXT_DIRECTION_FIRST_STRONG
            setBackgroundColor(Color.rgb(242, 248, 245))
            setPaddingRelative(smallPadding, smallPadding, smallPadding, smallPadding)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            )
        }
        content.addView(memoView)
        content.addView(Button(this).apply {
            setText(R.string.refresh)
            setOnClickListener { renderState() }
        })
        content.addView(TextView(this).apply {
            text = getString(R.string.storage_notice, packageName, BuildConfig.VERSION_NAME)
            textSize = 14f
            setTextColor(Color.DKGRAY)
            textDirection = View.TEXT_DIRECTION_FIRST_STRONG
            setPaddingRelative(0, padding, 0, 0)
        })

        setContentView(ScrollView(this).apply { addView(content) })
        renderState()
    }

    override fun onResume() {
        super.onResume()
        renderState()
    }

    private fun renderState() {
        val store = MemoStore(applicationContext)
        val stats = JSONObject(store.getStoreStats())
        val nlpMemo = JSONObject(store.getMemoState(NLP_MEMO_ID))
        stateView.text = buildString {
            appendLine(getString(R.string.state_package, packageName))
            appendLine(getString(R.string.state_version, BuildConfig.VERSION_NAME))
            appendLine(getString(R.string.state_android_api, android.os.Build.VERSION.SDK_INT))
            appendLine()
            appendLine(getString(R.string.state_physical_mutations, stats.getLong("physicalMutationCount")))
            appendLine(getString(R.string.state_put_invocations, stats.getLong("putInvocationCount")))
            appendLine(getString(R.string.state_memo_count, stats.getLong("memoCount")))
        }
        val present = nlpMemo.getString("status") == "present"
        memoHeaderView.visibility = if (present) View.VISIBLE else View.GONE
        memoView.visibility = if (present) View.VISIBLE else View.GONE
        memoView.text =
            if (present) BidiFormatter.getInstance().unicodeWrap(nlpMemo.getString("content")) else null
    }

    private companion object {
        const val NLP_MEMO_ID = "jidan.nlp.latest"
    }
}
