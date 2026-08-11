package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class ExecutionLaneResolverTest {
    @Test
    fun onlyTrustedFixtureGetsAnExecutingLane() {
        assertEquals(
            ExecutionLane.SANDBOX,
            ExecutionLaneResolver.resolve(ExecutionLaneResolver.SANDBOX_PACKAGE, trustedSandbox = true),
        )
        assertEquals(
            ExecutionLane.SHADOW,
            ExecutionLaneResolver.resolve(ExecutionLaneResolver.SANDBOX_PACKAGE, trustedSandbox = false),
        )
        assertEquals(
            ExecutionLane.SHADOW,
            ExecutionLaneResolver.resolve("com.cyjh.mobileanjian", trustedSandbox = true),
        )
        assertEquals(
            ExecutionLane.SHADOW,
            ExecutionLaneResolver.resolve("com.eg.android.AlipayGphone", trustedSandbox = true),
        )
    }
}
