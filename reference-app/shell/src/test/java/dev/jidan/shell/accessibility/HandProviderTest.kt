package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HandProviderTest {
    @Test
    fun generalAdapterStubDeclaresAllSixActionsButNeverClaimsDeviceReadiness() {
        assertEquals(UiActionKind.entries.toSet(), GeneralAdapterStubProvider.descriptor.capabilities)
        assertEquals(
            HandProviderAvailability.ADAPTER_STUB,
            GeneralAdapterStubProvider.descriptor.availability,
        )
        assertEquals(GeneralOwnedDemoContract.PACKAGE, GeneralAdapterStubProvider.descriptor.targetPackage)
        assertEquals(ExecutionLane.OWNED_APP, GeneralAdapterStubProvider.descriptor.lane)
    }

    @Test
    fun registryExposesReadyAndStubStatesSeparately() {
        val states = HandProviderRegistry.statuses().associate { it.id to it.availability }

        assertEquals(
            HandProviderAvailability.ADAPTER_STUB,
            states[HandProviderIds.GENERAL_ADAPTER_STUB],
        )
        assertEquals(
            HandProviderAvailability.VISIBLE_FILE_HANDOFF,
            states[HandProviderIds.MOBILEANJIAN_CANDIDATE],
        )
        assertTrue(MobileAnjianHandAdapter.descriptor.capabilities.isEmpty())
        assertTrue(states.size >= 2)
    }
}
