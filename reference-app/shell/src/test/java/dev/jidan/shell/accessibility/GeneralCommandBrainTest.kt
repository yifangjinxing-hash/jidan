package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeneralCommandBrainTest {
    @Test
    fun wordsCompileToAllGeneralHandActionsWithoutContentFiltering() {
        val bound = linkedMapOf<String, String>()
        val plan = GeneralCommandBrain.plan(
            planId = "general-test-1",
            userInput = "输入 支付密码 123456；点击；向下滚动；等待 500 毫秒；打开包 com.example.target",
            observation = readyObservation(),
            targetIdentity = identity(),
            valueBinder = GeneralValueBinder { actionId, _, value ->
                bound[actionId] = value
                "ephemeral:general-$actionId"
            },
        )

        assertEquals(
            listOf(
                UiActionKind.SET_TEXT,
                UiActionKind.CLICK,
                UiActionKind.SCROLL,
                UiActionKind.WAIT,
                UiActionKind.LAUNCH,
            ),
            plan.steps.map { it.kind },
        )
        assertEquals("支付密码 123456", bound["general_1"])
        assertFalse(plan.toString().contains("支付密码"))
        assertFalse(plan.toString().contains("123456"))
        assertEquals(UiScrollDirection.FORWARD, plan.steps[2].scrollDirection)
        assertEquals(500L, plan.steps[3].waitMs)
        assertEquals("com.example.target", plan.steps[4].launchPackageName)
        assertEquals(UiPostconditionKind.TARGET_PACKAGE, plan.steps[4].postconditionKind)
    }

    @Test
    fun backIsAvailableAsATerminalGeneralAction() {
        val plan = GeneralCommandBrain.plan(
            planId = "general-test-back",
            userInput = "返回",
            observation = readyObservation(),
            targetIdentity = identity(),
            valueBinder = GeneralValueBinder { _, _, _ -> error("BACK must not bind a value") },
        )

        assertEquals(UiActionKind.BACK, plan.steps.single().kind)
        assertEquals(UiPostconditionKind.LEFT_TARGET, plan.steps.single().postconditionKind)
    }

    @Test
    fun sameInputsAndBinderProduceTheSamePlan() {
        fun compile() = GeneralCommandBrain.plan(
            planId = "stable-plan",
            userInput = "输入 任意内容；向上滚动；等待 1 秒",
            observation = readyObservation(),
            targetIdentity = identity(),
            valueBinder = GeneralValueBinder { actionId, _, _ -> "stable:$actionId" },
        )

        assertEquals(compile().planSha256, compile().planSha256)
    }

    @Test(expected = IllegalArgumentException::class)
    fun navigationCannotHideUnreachableStepsAfterIt() {
        GeneralCommandBrain.plan(
            planId = "bad-plan",
            userInput = "返回；点击",
            observation = readyObservation(),
            targetIdentity = identity(),
            valueBinder = GeneralValueBinder { _, _, _ -> "unused" },
        )
    }

    @Test
    fun bridgeCompilesButDoesNotClaimTheUnwiredGeneralProviderIsExecutable() {
        val result = GeneralActionBridge.prepare(
            planId = "bridge-1",
            userInput = "输入 这是原样内容；点击",
            observation = readyObservation(),
            targetIdentity = identity(),
        ) as GeneralBridgeResult.ProviderUnavailable

        assertEquals(HandProviderAvailability.ADAPTER_STUB, result.provider.availability)
        assertEquals(HandProviderIds.GENERAL_ADAPTER_STUB, result.plan.handProviderId)
        assertEquals(ExecutionLane.OWNED_APP, result.plan.lane)
        assertTrue(result.provider.status.contains("no Android device consumer"))
    }

    @Test
    fun mobileAnjianStaysAnHonestAdapterStubWithoutInventingAPrivateIngress() {
        val result = GeneralActionBridge.prepare(
            planId = "bridge-mobileanjian",
            userInput = "点击",
            observation = readyObservation(),
            targetIdentity = identity(),
            providerId = HandProviderIds.MOBILEANJIAN_CANDIDATE,
        ) as GeneralBridgeResult.ProviderUnavailable

        assertEquals(HandProviderAvailability.VISIBLE_FILE_HANDOFF, result.provider.availability)
        assertTrue(result.provider.status.contains("not verified"))
        assertEquals(HandProviderIds.MOBILEANJIAN_CANDIDATE, result.plan.handProviderId)
    }

    private fun identity() = TargetIdentity(
        packageName = GeneralOwnedDemoContract.PACKAGE,
        versionCode = 1,
        uid = 12345,
        signingCertificateSha256 = "a".repeat(64),
        contractId = GeneralOwnedDemoContract.CONTRACT_ID,
    )

    private fun readyObservation(): UiObservation {
        fun node(
            suffix: String,
            index: Int,
            className: String,
            clickable: Boolean = false,
            editable: Boolean = false,
            scrollable: Boolean = false,
        ) = UiNodeSnapshot(
            path = "0.$index",
            packageName = GeneralOwnedDemoContract.PACKAGE,
            className = className,
            viewId = "${GeneralOwnedDemoContract.PACKAGE}:id/$suffix",
            labelDigest = null,
            valueState = if (editable) "EMPTY" else "NOT_APPLICABLE",
            clickable = clickable,
            editable = editable,
            password = false,
            scrollable = scrollable,
        )
        return UiObservation(
            packageName = GeneralOwnedDemoContract.PACKAGE,
            windowId = 8,
            sequence = 1,
            nodes = listOf(
                node("general_input", 0, "android.widget.EditText", editable = true),
                node("general_primary", 1, "android.widget.Button", clickable = true),
                node("general_scroll", 2, "android.widget.ScrollView", scrollable = true),
                node("general_anchor", 3, "android.view.View"),
                node("general_status", 4, "android.widget.TextView"),
            ),
            evidenceSha256 = "b".repeat(64),
        )
    }
}
