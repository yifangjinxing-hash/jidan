package dev.jidan.shell.accessibility

sealed interface GeneralBridgeResult {
    data class Prepared(
        val plan: UiActionPlan,
        val handProgram: HandProgram,
        val valueVault: GeneralValueVault,
    ) : GeneralBridgeResult

    data class ProviderUnavailable(
        val plan: UiActionPlan,
        val provider: HandProviderDescriptor,
    ) : GeneralBridgeResult

    data class Rejected(val reason: String) : GeneralBridgeResult
}

/** User words -> replaceable brain -> UiActionPlan -> selected hand language. */
object GeneralActionBridge {
    fun prepare(
        planId: String,
        userInput: String,
        observation: UiObservation,
        targetIdentity: TargetIdentity,
        providerId: String = HandProviderIds.GENERAL_ADAPTER_STUB,
        brain: GeneralBrain = GeneralCommandBrain,
    ): GeneralBridgeResult {
        val provider = HandProviderRegistry.find(providerId)
            ?: return GeneralBridgeResult.Rejected("unknown hand provider")
        val vault = GeneralValueVault()
        val plan = runCatching {
            brain.plan(
                planId = planId,
                userInput = userInput,
                observation = observation,
                targetIdentity = targetIdentity,
                provider = provider.descriptor,
                valueBinder = vault::bind,
            )
        }.getOrElse {
            vault.clear()
            return GeneralBridgeResult.Rejected(it.message ?: "brain could not compile the request")
        }
        return when (val translation = provider.translate(plan)) {
            is HandTranslationResult.Ready -> GeneralBridgeResult.Prepared(
                plan = plan,
                handProgram = translation.program,
                valueVault = vault,
            )
            is HandTranslationResult.Unavailable -> {
                vault.clear()
                GeneralBridgeResult.ProviderUnavailable(plan, translation.descriptor)
            }
            is HandTranslationResult.Rejected -> {
                vault.clear()
                GeneralBridgeResult.Rejected(translation.reason)
            }
        }
    }
}
