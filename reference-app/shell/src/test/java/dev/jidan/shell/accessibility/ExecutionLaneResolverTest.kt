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

    @Test
    fun ownedTargetResolutionCannotTurnCandidatesIntoExecutors() {
        assertEquals(
            ExecutionLane.OWNED_APP,
            ExecutionLaneResolver.resolveOwnedTarget(
                ExecutionLaneResolver.DAILY_PACKAGE,
                trusted = true,
            ),
        )
        assertEquals(
            ExecutionLane.SHADOW,
            ExecutionLaneResolver.resolveOwnedTarget(
                ExecutionLaneResolver.DAILY_PACKAGE,
                trusted = false,
            ),
        )
        assertEquals(
            ExecutionLane.SHADOW,
            ExecutionLaneResolver.resolveOwnedTarget(
                "com.cyjh.mobileanjian",
                trusted = true,
            ),
        )
    }
}
