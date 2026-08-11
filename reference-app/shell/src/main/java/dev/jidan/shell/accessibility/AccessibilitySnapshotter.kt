package dev.jidan.shell.accessibility

import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicLong

object AccessibilitySnapshotter {
    private val sequence = AtomicLong(0)

    fun capture(root: AccessibilityNodeInfo): UiObservation {
        val nodes = mutableListOf<UiNodeSnapshot>()
        walk(root, "0", nodes)
        val packageName = root.packageName?.toString().orEmpty()
        val canonical = buildString {
            append(packageName).append('\n')
            append(root.windowId).append('\n')
            nodes.forEach { node ->
                append(listOf(
                node.path,
                node.packageName,
                node.className,
                node.viewId.orEmpty(),
                node.labelDigest.orEmpty(),
                node.valueState,
                node.clickable.toString(),
                node.editable.toString(),
                node.password.toString(),
                ).joinToString("|")).append('\n')
            }
        }
        return UiObservation(
            packageName = packageName,
            windowId = root.windowId,
            sequence = sequence.incrementAndGet(),
            nodes = nodes,
            evidenceSha256 = sha256(canonical),
        )
    }

    private fun walk(
        node: AccessibilityNodeInfo,
        path: String,
        output: MutableList<UiNodeSnapshot>,
    ) {
        val rawLabel = if (node.isPassword || node.isEditable) {
            null
        } else {
            listOfNotNull(node.text?.toString(), node.contentDescription?.toString())
                .filter { it.isNotBlank() }
                .joinToString("\u001f")
                .ifBlank { null }
        }
        output += UiNodeSnapshot(
            path = path,
            packageName = node.packageName?.toString().orEmpty(),
            className = node.className?.toString().orEmpty(),
            viewId = node.viewIdResourceName,
            labelDigest = rawLabel?.let(::sha256),
            valueState = if (node.isEditable) {
                if (node.text.isNullOrEmpty()) "EMPTY" else "PRESENT"
            } else {
                "NOT_APPLICABLE"
            },
            clickable = node.isClickable,
            editable = node.isEditable,
            password = node.isPassword,
        )
        for (index in 0 until node.childCount) {
            node.getChild(index)?.let { child -> walk(child, "$path.$index", output) }
        }
    }
}
