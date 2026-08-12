package dev.jidan.shell.accessibility

enum class HandProviderAvailability {
    READY,
    ADAPTER_STUB,
    VISIBLE_FILE_HANDOFF,
}

data class HandProviderDescriptor(
    val id: String,
    val registrationSha256: String,
    val availability: HandProviderAvailability,
    val capabilities: Set<UiActionKind>,
    val status: String,
    val targetPackage: String? = null,
    val lane: ExecutionLane? = null,
)

data class HandInstruction(
    val actionId: String,
    val kind: UiActionKind,
    val selectorViewId: String,
    val ephemeralValueRef: String?,
    val scrollDirection: UiScrollDirection?,
    val waitMs: Long?,
    val launchPackageName: String?,
)

data class HandProgram(
    val providerId: String,
    val sourcePlanSha256: String,
    val instructions: List<HandInstruction>,
)

sealed interface HandTranslationResult {
    data class Ready(val program: HandProgram) : HandTranslationResult
    data class Unavailable(val descriptor: HandProviderDescriptor) : HandTranslationResult
    data class Rejected(val reason: String) : HandTranslationResult
}

interface HandProvider {
    val descriptor: HandProviderDescriptor

    fun translate(plan: UiActionPlan): HandTranslationResult
}

/**
 * A compiler target for Jidan's owned general-demo contract. It can validate
 * the plan shape, but deliberately has no device executor registration.
 */
object GeneralAdapterStubProvider : HandProvider {
    override val descriptor = HandProviderDescriptor(
        id = HandProviderIds.GENERAL_ADAPTER_STUB,
        registrationSha256 = HandProviderIds.GENERAL_ADAPTER_STUB_REGISTRATION_SHA256,
        availability = HandProviderAvailability.ADAPTER_STUB,
        capabilities = UiActionKind.entries.toSet(),
        status = "adapter stub only; no Android device consumer is registered",
        targetPackage = GeneralOwnedDemoContract.PACKAGE,
        lane = ExecutionLane.OWNED_APP,
    )

    override fun translate(plan: UiActionPlan): HandTranslationResult {
        val mismatch = plan.handProviderId != descriptor.id ||
            plan.handProviderRegistrationSha256 != descriptor.registrationSha256
        if (mismatch) return HandTranslationResult.Rejected("provider registration mismatch")
        val unsupported = plan.steps.map { it.kind }.firstOrNull { it !in descriptor.capabilities }
        if (unsupported != null) {
            return HandTranslationResult.Rejected("unsupported action: ${unsupported.name}")
        }
        val targetMismatch = plan.lane != descriptor.lane ||
            plan.steps.any { it.selector.packageName != descriptor.targetPackage }
        if (targetMismatch) return HandTranslationResult.Rejected("provider target contract mismatch")
        return HandTranslationResult.Unavailable(descriptor)
    }
}

/**
 * The installed APK is visible as a candidate hand, but no stable documented
 * command ingress has been demonstrated. Keep the adapter honest until one is.
 */
object MobileAnjianHandAdapter : HandProvider {
    override val descriptor = HandProviderDescriptor(
        id = HandProviderIds.MOBILEANJIAN_CANDIDATE,
        registrationSha256 =
            "1d187f13e4971ed4562ebea23ce8debe2663eac4471f1b3916887c70140a37c7",
        availability = HandProviderAvailability.VISIBLE_FILE_HANDOFF,
        capabilities = emptySet(),
        status = (
            "candidate Help.html describes a GBK .mq/.prop file handoff; " +
                "script generation is not implemented and command ingress is not verified"
            ),
    )

    override fun translate(plan: UiActionPlan): HandTranslationResult =
        HandTranslationResult.Unavailable(descriptor)
}

object HandProviderRegistry {
    private val providers = listOf(GeneralAdapterStubProvider, MobileAnjianHandAdapter)
        .associateBy { it.descriptor.id }

    fun find(id: String): HandProvider? = providers[id]

    fun statuses(): List<HandProviderDescriptor> = providers.values
        .map { it.descriptor }
        .sortedBy { it.id }
}
