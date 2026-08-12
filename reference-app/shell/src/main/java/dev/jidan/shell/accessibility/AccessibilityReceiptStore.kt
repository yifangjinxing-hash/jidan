package dev.jidan.shell.accessibility

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

data class PreparedAccessibilityAttempt(val hash: String)

class AccessibilityReceiptStore(context: Context) {
    private val file = File(context.filesDir, "jidan-accessibility-receipts.jsonl")

    @Synchronized
    fun verify(): Boolean = runCatching { verifiedRecords() }.isSuccess

    /** Write and fsync intent before the OS action is called. */
    @Synchronized
    fun prepare(
        sessionId: String,
        targetIdentity: TargetIdentity,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): PreparedAccessibilityAttempt {
        val records = verifiedRecords()
        check(records.lastOrNull()?.data?.phase != PHASE_PREPARED) {
            "dangling prepared attempt must be recovered before a new action"
        }
        val previous = records.lastOrNull()?.hash ?: GENESIS
        val data = baseRecord(
            phase = PHASE_PREPARED,
            sessionId = sessionId,
            targetIdentity = targetIdentity,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
            afterSha256 = "",
            executorAttempted = false,
            osAccepted = null,
            postconditionVerified = false,
            effectStatus = EffectStatus.NOT_ATTEMPTED,
            outcome = "prepared",
            attemptHash = null,
            previousHash = previous,
        )
        return PreparedAccessibilityAttempt(appendVerified(data))
    }

    /** Complete exactly the immediately preceding, fsynced attempt. */
    @Synchronized
    fun complete(
        prepared: PreparedAccessibilityAttempt,
        sessionId: String,
        targetIdentity: TargetIdentity,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        afterSha256: String,
        executorAttempted: Boolean,
        osAccepted: Boolean?,
        postconditionVerified: Boolean,
    ): String {
        val records = verifiedRecords()
        val last = records.lastOrNull() ?: error("prepared attempt is missing")
        check(last.hash == prepared.hash && last.data.phase == PHASE_PREPARED) {
            "prepared attempt is not the receipt tail"
        }
        check(last.data.sessionId == sessionId)
        check(last.data.planSha256 == plan.planSha256)
        check(last.data.stepId == step.id)
        val effectStatus = when {
            !executorAttempted -> EffectStatus.FAILED_BEFORE_EFFECT
            postconditionVerified -> EffectStatus.TRANSITION_VERIFIED
            else -> EffectStatus.OUTCOME_UNKNOWN
        }
        val outcome = when (effectStatus) {
            EffectStatus.FAILED_BEFORE_EFFECT -> "failed_before_effect"
            EffectStatus.TRANSITION_VERIFIED -> "transition_verified"
            EffectStatus.OUTCOME_UNKNOWN -> "outcome_unknown"
            EffectStatus.NOT_ATTEMPTED -> error("prepared status cannot be completed")
        }
        val data = baseRecord(
            phase = PHASE_RESULT,
            sessionId = sessionId,
            targetIdentity = targetIdentity,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
            afterSha256 = afterSha256,
            executorAttempted = executorAttempted,
            osAccepted = osAccepted,
            postconditionVerified = postconditionVerified,
            effectStatus = effectStatus,
            outcome = outcome,
            attemptHash = prepared.hash,
            previousHash = prepared.hash,
        )
        return appendVerified(data)
    }

    @Synchronized
    fun failedBeforeEffect(
        sessionId: String,
        targetIdentity: TargetIdentity,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): String {
        val previous = verifiedRecords().lastOrNull()?.hash ?: GENESIS
        return appendVerified(
            baseRecord(
                phase = PHASE_RESULT,
                sessionId = sessionId,
                targetIdentity = targetIdentity,
                windowId = windowId,
                plan = plan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = beforeSha256,
                executorAttempted = false,
                osAccepted = false,
                postconditionVerified = false,
                effectStatus = EffectStatus.FAILED_BEFORE_EFFECT,
                outcome = "failed_before_effect",
                attemptHash = null,
                previousHash = previous,
            ),
        )
    }

    /** A crash after PREPARED may have happened before or after the OS call. */
    @Synchronized
    fun recoverDanglingAttempt(): Boolean {
        val records = verifiedRecords()
        val last = records.lastOrNull() ?: return false
        if (last.data.phase != PHASE_PREPARED) return false
        val prepared = last.data
        val recovery = prepared.copy(
            phase = PHASE_RECOVERY,
            timestampMs = System.currentTimeMillis(),
            afterSha256 = "",
            executorAttempted = null,
            osAccepted = null,
            postconditionVerified = false,
            effectStatus = EffectStatus.OUTCOME_UNKNOWN.name,
            syntheticCommit = false,
            outcome = "interrupted_outcome_unknown",
            attemptHash = last.hash,
            previousHash = last.hash,
        )
        appendVerified(recovery)
        return true
    }

    private fun baseRecord(
        phase: String,
        sessionId: String,
        targetIdentity: TargetIdentity,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        afterSha256: String,
        executorAttempted: Boolean?,
        osAccepted: Boolean?,
        postconditionVerified: Boolean,
        effectStatus: EffectStatus,
        outcome: String,
        attemptHash: String?,
        previousHash: String,
    ): AccessibilityReceiptData = AccessibilityReceiptData(
        phase = phase,
        timestampMs = System.currentTimeMillis(),
        sessionId = sessionId,
        lane = plan.lane.name,
        targetPackage = step.selector.packageName,
        targetIdentitySha256 = targetIdentity.digestSha256,
        windowId = windowId,
        planSha256 = plan.planSha256,
        stepId = step.id,
        kind = step.kind.name,
        sensitivity = step.sensitivity.name,
        beforeSha256 = beforeSha256,
        afterSha256 = afterSha256,
        executorAttempted = executorAttempted,
        osAccepted = osAccepted,
        postconditionVerified = postconditionVerified,
        effectStatus = effectStatus.name,
        realWorldStatus = RealWorldStatus.SYNTHETIC_ONLY.name,
        syntheticCommit = step.id == "submit_synthetic" && postconditionVerified,
        realPayment = false,
        sensitiveValuePersisted = false,
        outcome = outcome,
        attemptHash = attemptHash,
        previousHash = previousHash,
    )

    private fun appendVerified(data: AccessibilityReceiptData): String {
        validateSemantics(data)
        val hash = data.hash()
        val record = data.toJson().put("hash", hash)
        file.parentFile?.mkdirs()
        FileOutputStream(file, true).use { stream ->
            stream.write((record.toString() + "\n").toByteArray(Charsets.UTF_8))
            stream.flush()
            stream.fd.sync()
        }
        return hash
    }

    private fun verifiedRecords(): List<StoredReceipt> {
        if (!file.isFile) return emptyList()
        val records = file.readLines(Charsets.UTF_8)
            .filter { line -> line.isNotBlank() }
            .map { line -> JSONObject(line) }
        var previous = GENESIS
        val verified = records.map { json ->
            val keys = buildSet {
                val iterator = json.keys()
                while (iterator.hasNext()) add(iterator.next())
            }
            check(keys == EXPECTED_FIELDS) { "unexpected accessibility receipt fields" }
            val data = json.toReceiptData()
            validateSemantics(data)
            check(data.previousHash == previous) { "accessibility receipt chain is broken" }
            val hash = json.getString("hash")
            check(hash == data.hash()) { "accessibility receipt hash mismatch" }
            previous = hash
            StoredReceipt(data, hash)
        }
        verified.forEachIndexed { index, record ->
            if (record.data.phase == PHASE_PREPARED && index < verified.lastIndex) {
                val completion = verified[index + 1]
                check(
                    completion.data.phase in setOf(PHASE_RESULT, PHASE_RECOVERY) &&
                        completion.data.attemptHash == record.hash
                ) { "historical prepared attempt is unresolved" }
            }
            if (
                record.data.phase in setOf(PHASE_RESULT, PHASE_RECOVERY) &&
                record.data.attemptHash != null
            ) {
                check(index > 0 && verified[index - 1].hash == record.data.attemptHash) {
                    "attempt completion is not adjacent to its prepared record"
                }
            }
        }
        return verified
    }

    private fun validateSemantics(data: AccessibilityReceiptData) {
        check(data.lane == ExecutionLane.SANDBOX.name)
        check(data.targetPackage == ExecutionLaneResolver.SANDBOX_PACKAGE)
        check(data.realWorldStatus == RealWorldStatus.SYNTHETIC_ONLY.name)
        check(!data.realPayment)
        check(!data.sensitiveValuePersisted)
        check(data.targetIdentitySha256.matches(SHA256))
        check(data.planSha256.matches(SHA256))
        check(data.beforeSha256.matches(SHA256))
        check(data.afterSha256.isEmpty() || data.afterSha256.matches(SHA256))
        check(data.previousHash.matches(SHA256))
        check(data.attemptHash == null || data.attemptHash.matches(SHA256))
        when (data.phase) {
            PHASE_PREPARED -> {
                check(data.executorAttempted == false && data.osAccepted == null)
                check(!data.postconditionVerified)
                check(data.effectStatus == EffectStatus.NOT_ATTEMPTED.name)
                check(data.outcome == "prepared" && data.attemptHash == null)
            }
            PHASE_RESULT -> when {
                data.executorAttempted == false -> {
                    check(data.osAccepted != true && !data.postconditionVerified)
                    check(data.effectStatus == EffectStatus.FAILED_BEFORE_EFFECT.name)
                    check(data.outcome == "failed_before_effect")
                    check(data.attemptHash == null || data.attemptHash == data.previousHash)
                }
                data.postconditionVerified -> {
                    check(data.executorAttempted == true && data.osAccepted == true)
                    check(data.afterSha256.matches(SHA256))
                    check(data.afterSha256 != data.beforeSha256)
                    check(data.effectStatus == EffectStatus.TRANSITION_VERIFIED.name)
                    check(data.outcome == "transition_verified")
                    check(data.attemptHash == data.previousHash)
                }
                else -> {
                    check(data.executorAttempted == true)
                    check(data.effectStatus == EffectStatus.OUTCOME_UNKNOWN.name)
                    check(data.outcome == "outcome_unknown")
                    check(data.attemptHash == data.previousHash)
                }
            }
            PHASE_RECOVERY -> {
                check(data.executorAttempted == null && data.osAccepted == null)
                check(!data.postconditionVerified)
                check(data.effectStatus == EffectStatus.OUTCOME_UNKNOWN.name)
                check(data.outcome == "interrupted_outcome_unknown")
                check(data.attemptHash == data.previousHash)
            }
            else -> error("unsupported accessibility receipt phase")
        }
        check(data.syntheticCommit == (
            data.phase == PHASE_RESULT &&
                data.stepId == "submit_synthetic" &&
                data.postconditionVerified
            ))
    }

    private fun AccessibilityReceiptData.toJson(): JSONObject = JSONObject()
        .put("schemaVersion", AccessibilityReceiptData.SCHEMA_VERSION)
        .put("phase", phase)
        .put("timestampMs", timestampMs)
        .put("sessionId", sessionId)
        .put("lane", lane)
        .put("targetPackage", targetPackage)
        .put("targetIdentitySha256", targetIdentitySha256)
        .put("windowId", windowId)
        .put("planSha256", planSha256)
        .put("stepId", stepId)
        .put("kind", kind)
        .put("sensitivity", sensitivity)
        .put("beforeSha256", beforeSha256)
        .put("afterSha256", afterSha256)
        .put("executorAttempted", executorAttempted ?: JSONObject.NULL)
        .put("osAccepted", osAccepted ?: JSONObject.NULL)
        .put("postconditionVerified", postconditionVerified)
        .put("effectStatus", effectStatus)
        .put("realWorldStatus", realWorldStatus)
        .put("syntheticCommit", syntheticCommit)
        .put("realPayment", realPayment)
        .put("sensitiveValuePersisted", sensitiveValuePersisted)
        .put("outcome", outcome)
        .put("attemptHash", attemptHash ?: JSONObject.NULL)
        .put("previousHash", previousHash)

    private fun JSONObject.toReceiptData(): AccessibilityReceiptData {
        check(getString("schemaVersion") == AccessibilityReceiptData.SCHEMA_VERSION)
        return AccessibilityReceiptData(
            phase = getString("phase"),
            timestampMs = getLong("timestampMs"),
            sessionId = getString("sessionId"),
            lane = getString("lane"),
            targetPackage = getString("targetPackage"),
            targetIdentitySha256 = getString("targetIdentitySha256"),
            windowId = getInt("windowId"),
            planSha256 = getString("planSha256"),
            stepId = getString("stepId"),
            kind = getString("kind"),
            sensitivity = getString("sensitivity"),
            beforeSha256 = getString("beforeSha256"),
            afterSha256 = getString("afterSha256"),
            executorAttempted = nullableBoolean("executorAttempted"),
            osAccepted = nullableBoolean("osAccepted"),
            postconditionVerified = getBoolean("postconditionVerified"),
            effectStatus = getString("effectStatus"),
            realWorldStatus = getString("realWorldStatus"),
            syntheticCommit = getBoolean("syntheticCommit"),
            realPayment = getBoolean("realPayment"),
            sensitiveValuePersisted = getBoolean("sensitiveValuePersisted"),
            outcome = getString("outcome"),
            attemptHash = nullableString("attemptHash"),
            previousHash = getString("previousHash"),
        )
    }

    private fun JSONObject.nullableBoolean(name: String): Boolean? =
        if (isNull(name)) null else getBoolean(name)

    private fun JSONObject.nullableString(name: String): String? =
        if (isNull(name)) null else getString(name)

    private data class StoredReceipt(
        val data: AccessibilityReceiptData,
        val hash: String,
    )

    companion object {
        private const val PHASE_PREPARED = "PREPARED"
        private const val PHASE_RESULT = "RESULT"
        private const val PHASE_RECOVERY = "RECOVERY"
        private const val GENESIS =
            "0000000000000000000000000000000000000000000000000000000000000000"
        private val SHA256 = Regex("^[0-9a-f]{64}$")
        private val EXPECTED_FIELDS = setOf(
            "schemaVersion",
            "phase",
            "timestampMs",
            "sessionId",
            "lane",
            "targetPackage",
            "targetIdentitySha256",
            "windowId",
            "planSha256",
            "stepId",
            "kind",
            "sensitivity",
            "beforeSha256",
            "afterSha256",
            "executorAttempted",
            "osAccepted",
            "postconditionVerified",
            "effectStatus",
            "realWorldStatus",
            "syntheticCommit",
            "realPayment",
            "sensitiveValuePersisted",
            "outcome",
            "attemptHash",
            "previousHash",
            "hash",
        )
    }
}
