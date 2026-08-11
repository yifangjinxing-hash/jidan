package dev.jidan.shell

/**
 * Turns parser output into the only two routing outcomes the shell understands.
 *
 * A [DirectNavigation] is front-door navigation: the user already asked to open an
 * app or Android settings, so another confirmation would add no safety. Payment,
 * transfer and other sensitive wording never reaches this branch because the
 * parser returns [ParseResult.Rejected].
 */
sealed interface DispatchDirective {
    data class DirectNavigation(val proposal: ActionProposal) : DispatchDirective
    data class SandboxExperiment(val proposal: ActionProposal) : DispatchDirective

    data class DoNotDispatch(val title: String, val message: String) : DispatchDirective
}

object CommandDispatchPolicy {
    fun classify(result: ParseResult): DispatchDirective = when (result) {
        is ParseResult.Proposal -> when (result.value.action) {
            ShellAction.OPEN_ALIPAY,
            ShellAction.OPEN_MOBILEANJIAN,
            ShellAction.OPEN_SYSTEM_SETTINGS -> DispatchDirective.DirectNavigation(result.value)
            ShellAction.OPEN_AUTOMATION_LAB -> DispatchDirective.SandboxExperiment(result.value)
        }

        is ParseResult.Rejected -> DispatchDirective.DoNotDispatch(
            title = "这一步我不能做",
            message = result.reason,
        )
        is ParseResult.Unknown -> DispatchDirective.DoNotDispatch(
            title = "现在还没学会",
            message = result.suggestion,
        )
    }
}
