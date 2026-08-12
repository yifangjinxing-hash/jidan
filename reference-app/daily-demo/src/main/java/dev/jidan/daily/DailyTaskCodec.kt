package dev.jidan.daily.demo

import java.nio.charset.StandardCharsets
import java.util.Base64

/** A small, versioned local format. Task text is encoded so tabs and Unicode round-trip safely. */
object DailyTaskCodec {
    private const val VERSION = "jidan-daily-v1"

    fun encode(tasks: List<DailyTask>): String = buildString {
        append(VERSION)
        tasks.forEach { task ->
            append('\n')
            append(encodePart(task.id))
            append('\t')
            append(if (task.completed) '1' else '0')
            append('\t')
            append(task.createdAtEpochMs)
            append('\t')
            append(encodePart(task.title))
        }
    }

    fun decode(raw: String?): List<DailyTask> {
        if (raw.isNullOrBlank()) return emptyList()
        val lines = raw.lineSequence().toList()
        if (lines.firstOrNull() != VERSION) return emptyList()

        val seenIds = mutableSetOf<String>()
        return lines.drop(1).mapNotNull { line ->
            decodeLine(line)?.takeIf { task -> seenIds.add(task.id) }
        }
    }

    private fun decodeLine(line: String): DailyTask? {
        val parts = line.split('\t')
        if (parts.size != 4) return null

        val id = decodePart(parts[0]) ?: return null
        val completed = when (parts[1]) {
            "0" -> false
            "1" -> true
            else -> return null
        }
        val createdAt = parts[2].toLongOrNull()?.takeIf { it >= 0 } ?: return null
        val title = decodePart(parts[3])?.trim()?.takeIf(String::isNotBlank) ?: return null
        if (id.isBlank()) return null

        return DailyTask(
            id = id,
            title = title,
            completed = completed,
            createdAtEpochMs = createdAt,
        )
    }

    private fun encodePart(value: String): String = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.toByteArray(StandardCharsets.UTF_8))

    private fun decodePart(value: String): String? = try {
        String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8)
    } catch (_: IllegalArgumentException) {
        null
    }
}
