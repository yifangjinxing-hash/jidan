package dev.jidan.shell.accessibility

import java.util.UUID

object GeneralOwnedDemoContract {
    const val PACKAGE = "dev.jidan.general.demo"
    const val CONTRACT_ID = "jidan.general.demo.v0.1.actions.6"
    const val INPUT_ID = "$PACKAGE:id/general_input"
    const val PRIMARY_ID = "$PACKAGE:id/general_primary"
    const val SCROLL_ID = "$PACKAGE:id/general_scroll"
    const val ANCHOR_ID = "$PACKAGE:id/general_anchor"
    const val STATUS_ID = "$PACKAGE:id/general_status"
}

data class BoundGeneralValue(
    val actionId: String,
    val selectorViewId: String,
    val value: String,
)

/** One-shot in-memory values used by SET_TEXT instructions. */
class GeneralValueVault {
    private val values = linkedMapOf<String, BoundGeneralValue>()

    @Synchronized
    fun bind(actionId: String, selectorViewId: String, value: String): String {
        val reference = "ephemeral:${UUID.randomUUID()}"
        values[reference] = BoundGeneralValue(actionId, selectorViewId, value)
        return reference
    }

    @Synchronized
    fun consume(reference: String, actionId: String, selectorViewId: String): String? {
        val bound = values[reference] ?: return null
        if (bound.actionId != actionId || bound.selectorViewId != selectorViewId) return null
        values.remove(reference)
        return bound.value
    }

    @Synchronized
    fun clear() = values.clear()

    @Synchronized
    internal fun remainingCount(): Int = values.size
}

fun interface GeneralValueBinder {
    fun bind(actionId: String, selectorViewId: String, value: String): String
}

interface GeneralBrain {
    fun plan(
        planId: String,
        userInput: String,
        observation: UiObservation,
        targetIdentity: TargetIdentity,
        provider: HandProviderDescriptor,
        valueBinder: GeneralValueBinder,
    ): UiActionPlan
}

/**
 * Deterministic, replaceable first brain for the owned general demo. It parses
 * action verbs only; it does not inspect or ban the content being typed.
 */
object GeneralCommandBrain : GeneralBrain {
    override fun plan(
        planId: String,
        userInput: String,
        observation: UiObservation,
        targetIdentity: TargetIdentity,
        provider: HandProviderDescriptor,
        valueBinder: GeneralValueBinder,
    ): UiActionPlan {
        require(planId.isNotBlank())
        require(observation.packageName == GeneralOwnedDemoContract.PACKAGE)
        require(targetIdentity.packageName == GeneralOwnedDemoContract.PACKAGE)
        require(targetIdentity.contractId == GeneralOwnedDemoContract.CONTRACT_ID)
        val commands = parse(userInput)
        require(commands.isNotEmpty()) { "at least one command is required" }
        require(commands.dropLast(1).none { it is Command.Back || it is Command.Launch }) {
            "BACK and LAUNCH must be the final command"
        }

        val input = observation.uniqueNode(GeneralOwnedDemoContract.INPUT_ID)
        val primary = observation.uniqueNode(GeneralOwnedDemoContract.PRIMARY_ID)
        val scroll = observation.uniqueNode(GeneralOwnedDemoContract.SCROLL_ID)
        val anchor = observation.uniqueNode(GeneralOwnedDemoContract.ANCHOR_ID)
        observation.uniqueNode(GeneralOwnedDemoContract.STATUS_ID)
        require(input.editable) { "general input role mismatch" }
        require(primary.clickable) { "general primary role mismatch" }
        require(scroll.scrollable) { "general scroll role mismatch" }

        val steps = commands.mapIndexed { index, command ->
            val actionId = "general_${index + 1}"
            when (command) {
                is Command.SetText -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.SET_TEXT,
                    selector = input.selector(),
                    ephemeralValueRef = valueBinder.bind(actionId, input.requireViewId(), command.value),
                    postconditionViewId = GeneralOwnedDemoContract.STATUS_ID,
                    postconditionMarker = "general:${index + 1}:text_set",
                )
                Command.Click -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.CLICK,
                    selector = primary.selector(),
                    postconditionViewId = GeneralOwnedDemoContract.STATUS_ID,
                    postconditionMarker = "general:${index + 1}:clicked",
                )
                is Command.Scroll -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.SCROLL,
                    selector = scroll.selector(),
                    postconditionViewId = GeneralOwnedDemoContract.STATUS_ID,
                    postconditionMarker = "",
                    scrollDirection = command.direction,
                    postconditionKind = UiPostconditionKind.EVIDENCE_CHANGED,
                )
                Command.Back -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.BACK,
                    selector = anchor.selector(),
                    postconditionViewId = "",
                    postconditionMarker = "",
                    postconditionKind = UiPostconditionKind.LEFT_TARGET,
                )
                is Command.Wait -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.WAIT,
                    selector = anchor.selector(),
                    postconditionViewId = "",
                    postconditionMarker = "",
                    waitMs = command.milliseconds,
                    postconditionKind = UiPostconditionKind.SAME_WINDOW,
                )
                is Command.Launch -> PlannedUiAction(
                    id = actionId,
                    kind = UiActionKind.LAUNCH,
                    selector = anchor.selector(),
                    postconditionViewId = "",
                    postconditionMarker = "",
                    launchPackageName = command.packageName,
                    postconditionKind = UiPostconditionKind.TARGET_PACKAGE,
                )
            }
        }
        return UiActionPlan.create(
            id = planId,
            handProviderId = provider.id,
            handProviderRegistrationSha256 = provider.registrationSha256,
            lane = ExecutionLane.OWNED_APP,
            observationSha256 = observation.evidenceSha256,
            targetIdentitySha256 = targetIdentity.digestSha256,
            steps = steps,
        )
    }

    fun plan(
        planId: String,
        userInput: String,
        observation: UiObservation,
        targetIdentity: TargetIdentity,
        valueBinder: GeneralValueBinder,
    ): UiActionPlan = plan(
        planId = planId,
        userInput = userInput,
        observation = observation,
        targetIdentity = targetIdentity,
        provider = GeneralAdapterStubProvider.descriptor,
        valueBinder = valueBinder,
    )

    private fun parse(input: String): List<Command> = input
        .split(Regex("(?:\\r?\\n|[;；]|然后)"))
        .map(String::trim)
        .filter(String::isNotEmpty)
        .map(::parseOne)

    private fun parseOne(command: String): Command {
        if (command.startsWith("输入")) {
            val value = command.removePrefix("输入").trimStart(' ', '：', ':')
            require(value.isNotEmpty()) { "SET_TEXT value is empty" }
            return Command.SetText(value)
        }
        if (command in setOf("点击", "点一下", "按下")) return Command.Click
        if (command in setOf("向下滚动", "下滑", "往下滚")) {
            return Command.Scroll(UiScrollDirection.FORWARD)
        }
        if (command in setOf("向上滚动", "上滑", "往上滚")) {
            return Command.Scroll(UiScrollDirection.BACKWARD)
        }
        if (command in setOf("返回", "后退")) return Command.Back
        WAIT.matchEntire(command)?.let { match ->
            val amount = match.groupValues[1].toLong()
            val unit = match.groupValues[2]
            val milliseconds = if (unit == "秒") Math.multiplyExact(amount, 1_000L) else amount
            return Command.Wait(milliseconds)
        }
        LAUNCH.matchEntire(command)?.let { match -> return Command.Launch(match.groupValues[1]) }
        throw IllegalArgumentException("unknown general command: $command")
    }

    private fun UiObservation.uniqueNode(viewId: String): UiNodeSnapshot {
        val matches = nodes.filter { it.packageName == packageName && it.viewId == viewId }
        require(matches.size == 1) { "general semantic node must be unique: $viewId" }
        return matches.single()
    }

    private fun UiNodeSnapshot.requireViewId(): String = requireNotNull(viewId)

    private fun UiNodeSnapshot.selector() = UiNodeSelector(
        packageName = packageName,
        viewId = requireViewId(),
        expectedPath = path,
        expectedClassName = className,
        expectedClickable = clickable,
        expectedEditable = editable,
        expectedPassword = password,
        expectedScrollable = scrollable,
    )

    private sealed interface Command {
        data class SetText(val value: String) : Command
        data object Click : Command
        data class Scroll(val direction: UiScrollDirection) : Command
        data object Back : Command
        data class Wait(val milliseconds: Long) : Command
        data class Launch(val packageName: String) : Command
    }

    private val WAIT = Regex("等待\\s*(\\d+)\\s*(毫秒|秒)?")
    private val LAUNCH = Regex("(?:打开包|启动包)\\s*([A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z][A-Za-z0-9_]*)+)")
}
