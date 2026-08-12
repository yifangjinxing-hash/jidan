package dev.jidan.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EmbeddedHandInstallerTest {
    @Test
    fun embeddedCandidateIsPinnedToTheAuditedArtifact() {
        assertEquals(83_933_160L, EmbeddedHandInstaller.EXPECTED_SIZE_BYTES)
        assertEquals(
            "2d554d35d3c20de38c2adb6b51bdea2ddcf19e4dcdc6f3c3da52244037bb803d",
            EmbeddedHandInstaller.EXPECTED_SHA256,
        )
        assertEquals("mobileanjian-4.2.3.apk", EmbeddedHandInstaller.FILE_NAME)
        assertTrue(EmbeddedHandInstaller.ASSET_PATH.endsWith(EmbeddedHandInstaller.FILE_NAME))
        assertEquals(2026000224L, FrontDoorLauncher.MOBILEANJIAN_VERSION_CODE)
        assertEquals(
            "800614aaf2494f4dc1c4d43fff92ee42771d01fc09435d0b8d4b8e54dbd91413",
            FrontDoorLauncher.MOBILEANJIAN_CERT_SHA256,
        )
    }
}
