package dev.jidan.shell

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

enum class OrbMode(val spokenLabel: String) {
    IDLE("鸡蛋正在等待"),
    LISTENING("鸡蛋正在听"),
    THINKING("鸡蛋正在理解"),
    SUCCESS("鸡蛋完成了这一步"),
    FAILURE("鸡蛋没有执行"),
}

class JidanOrbView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = density(2f)
    }
    private val facePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(225, 249, 246, 255)
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeWidth = density(3f)
    }
    private var pulse = 0f
    private var mode = OrbMode.IDLE
    private val animator = ValueAnimator.ofFloat(0f, 1f).apply {
        duration = 2600L
        repeatCount = ValueAnimator.INFINITE
        repeatMode = ValueAnimator.REVERSE
        addUpdateListener { value ->
            pulse = value.animatedValue as Float
            invalidate()
        }
    }

    init {
        isFocusable = true
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        contentDescription = mode.spokenLabel
    }

    fun setMode(value: OrbMode) {
        mode = value
        contentDescription = value.spokenLabel
        invalidate()
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (ValueAnimator.areAnimatorsEnabled() && !animator.isStarted) animator.start()
    }

    override fun onDetachedFromWindow() {
        animator.cancel()
        super.onDetachedFromWindow()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val centerX = width / 2f
        val centerY = height / 2f
        val radius = min(width, height) * (0.34f + pulse * 0.018f)
        val color = when (mode) {
            OrbMode.IDLE -> Color.rgb(139, 120, 215)
            OrbMode.LISTENING -> Color.rgb(76, 206, 202)
            OrbMode.THINKING -> Color.rgb(236, 225, 194)
            OrbMode.SUCCESS -> Color.rgb(92, 201, 145)
            OrbMode.FAILURE -> Color.rgb(225, 112, 112)
        }
        glowPaint.shader = RadialGradient(
            centerX,
            centerY,
            radius * 1.45f,
            intArrayOf(
                Color.argb(55, Color.red(color), Color.green(color), Color.blue(color)),
                Color.argb(18, Color.red(color), Color.green(color), Color.blue(color)),
                Color.TRANSPARENT,
            ),
            floatArrayOf(0f, 0.6f, 1f),
            Shader.TileMode.CLAMP,
        )
        canvas.drawCircle(centerX, centerY, radius * 1.45f, glowPaint)
        ringPaint.color = Color.argb(115, Color.red(color), Color.green(color), Color.blue(color))
        canvas.drawCircle(centerX, centerY, radius, ringPaint)

        val eyeY = centerY - radius * 0.04f
        val eyeOffset = radius * 0.19f
        canvas.drawPoint(centerX - eyeOffset, eyeY, facePaint)
        canvas.drawPoint(centerX + eyeOffset, eyeY, facePaint)
        val smile = RectF(
            centerX - radius * 0.2f,
            centerY - radius * 0.02f,
            centerX + radius * 0.2f,
            centerY + radius * 0.3f,
        )
        canvas.drawArc(smile, 20f, 140f, false, facePaint)
    }

    private fun density(value: Float): Float = value * resources.displayMetrics.density
}
