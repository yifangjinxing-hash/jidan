package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class AccessibilityReturnPolicyTest {
    @Test
    fun returnsOnlyWhileTheOwnedTargetIsStillForeground() {
        assertEquals(
            true,
            AccessibilityReturnPolicy.shouldReturn(
                targetPackage = "dev.jidan.daily.demo",
                foregroundPackage = "dev.jidan.daily.demo",
            ),
        )
        assertEquals(
            false,
            AccessibilityReturnPolicy.shouldReturn(
                targetPackage = "dev.jidan.daily.demo",
                foregroundPackage = "dev.jidan.shell",
            ),
        )
        assertEquals(
            false,
            AccessibilityReturnPolicy.shouldReturn(
                targetPackage = "dev.jidan.daily.demo",
                foregroundPackage = null,
            ),
        )
    }
}
