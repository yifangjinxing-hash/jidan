package dev.jidan.shell.accessibility

data class OwnedTargetSpec(
    val packageName: String,
    val activityClassName: String,
    val versionCode: Long,
    val contractId: String,
    val lane: ExecutionLane,
    val taskKind: AccessibilityTaskKind,
    val statusViewId: String,
    val resultViewId: String,
    val sessionMarkerPrefix: String,
)

object OwnedTargetRegistry {
    const val CONTRACT_METADATA = "dev.jidan.ACCESSIBILITY_LAB_CONTRACT"
    const val SANDBOX_CONTRACT_ID = "jidan.accessibility.sandbox.v0.1.semantic-form.5"
    const val DAILY_CONTRACT_ID = "jidan.daily.demo.v0.1.note-form.1"

    val sandbox = OwnedTargetSpec(
        packageName = ExecutionLaneResolver.SANDBOX_PACKAGE,
        activityClassName = "${ExecutionLaneResolver.SANDBOX_PACKAGE}.MainActivity",
        versionCode = 1L,
        contractId = SANDBOX_CONTRACT_ID,
        lane = ExecutionLane.SANDBOX,
        taskKind = AccessibilityTaskKind.SANDBOX_LAB,
        statusViewId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_status",
        resultViewId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_result",
        sessionMarkerPrefix = "jidan_lab_session:",
    )

    val daily = OwnedTargetSpec(
        packageName = ExecutionLaneResolver.DAILY_PACKAGE,
        activityClassName = "${ExecutionLaneResolver.DAILY_PACKAGE}.MainActivity",
        versionCode = 1L,
        contractId = DAILY_CONTRACT_ID,
        lane = ExecutionLane.OWNED_APP,
        taskKind = AccessibilityTaskKind.DAILY_NOTE,
        statusViewId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/daily_note_status",
        resultViewId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/daily_note_result",
        sessionMarkerPrefix = "jidan_daily_session:",
    )

    private val byPackage = listOf(sandbox, daily).associateBy(OwnedTargetSpec::packageName)

    fun find(packageName: String): OwnedTargetSpec? = byPackage[packageName]
}
