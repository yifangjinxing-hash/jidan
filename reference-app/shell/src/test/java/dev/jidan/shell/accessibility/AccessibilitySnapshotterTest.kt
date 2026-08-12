package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class AccessibilitySnapshotterTest {
    @Test
    fun androidHintTextDoesNotPretendAnEmptyEditorContainsUserData() {
        assertEquals("EMPTY", editableValueState("写下一件小事", isShowingHintText = true))
        assertEquals("EMPTY", editableValueState("", isShowingHintText = false))
        assertEquals("PRESENT", editableValueState("明天买鸡蛋", isShowingHintText = false))
    }
}
