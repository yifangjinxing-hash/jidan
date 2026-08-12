package dev.jidan.shell

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantDiagnosticsTest {
    @Test
    fun rotationKeepsOnlyTwoBoundedSegments() {
        val directory = Files.createTempDirectory("jidan-diagnostics").toFile()
        try {
            val line = "x".repeat(1023) + "\n"
            repeat(700) { DiagnosticsFileStore.append(directory, line) }

            val current = directory.resolve(DiagnosticsFileStore.FILE_NAME)
            val previous = directory.resolve(DiagnosticsFileStore.PREVIOUS_FILE_NAME)
            assertTrue(current.length() <= DiagnosticsFileStore.SEGMENT_MAX_BYTES)
            assertTrue(previous.length() <= DiagnosticsFileStore.SEGMENT_MAX_BYTES)
            assertTrue(current.length() + previous.length() <= DiagnosticsFileStore.SEGMENT_MAX_BYTES * 2)
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun aRotationDoesNotAppendToTheAlreadyFullCurrentSegment() {
        val directory = Files.createTempDirectory("jidan-diagnostics-boundary").toFile()
        try {
            val current = directory.resolve(DiagnosticsFileStore.FILE_NAME)
            current.writeBytes(ByteArray(DiagnosticsFileStore.SEGMENT_MAX_BYTES.toInt()))

            DiagnosticsFileStore.append(directory, "next\n")

            assertEquals("next\n", current.readText())
            assertEquals(
                DiagnosticsFileStore.SEGMENT_MAX_BYTES,
                directory.resolve(DiagnosticsFileStore.PREVIOUS_FILE_NAME).length(),
            )
        } finally {
            directory.deleteRecursively()
        }
    }
}
