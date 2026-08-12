package dev.jidan.shell.accessibility

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

data class DailyNoteReceiptData(
    val phase: String,
    val timestampMs: Long,
    val sessionId: String,
    val requestId: String,
    val targetIdentitySha256: String,
    val windowId: Int,
    val planSha256: String,
    val stepId: String,
    val kind: String,
    val payloadSha256: String,
    val beforeSha256: String,
    val afterSha256: String,
    val executorAttempted: Boolean?,
    val osAccepted: Boolean?,
    val postconditionVerified: Boolean,
    val effectStatus: String,
    val noteSaved: Boolean,
    val navigationAccepted: Boolean?,
    val rawPayloadInReceipt: Boolean,
    val outcome: String,
    val attemptHash: String?,
    val previousHash: String,
) {
    fun canonical(): String = listOf(
        SCHEMA_VERSION,
        phase,
        timestampMs.toString(),
        sessionId,
        requestId,
        ExecutionLane.OWNED_APP.name,
        ExecutionLaneResolver.DAILY_PACKAGE,
        targetIdentitySha256,
        windowId.toString(),
        planSha256,
        stepId,
        kind,
        payloadSha256,
        beforeSha256,
        afterSha256,
        executorAttempted?.toString() ?: "null",
        osAccepted?.toString() ?: "null",
        postconditionVerified.toString(),
        effectStatus,
        RealWorldStatus.OWNED_LOCAL_APP.name,
        noteSaved.toString(),
        navigationAccepted?.toString() ?: "null",
        rawPayloadInReceipt.toString(),
        outcome,
        attemptHash.orEmpty(),
        previousHash,
    ).joinToString("\n")

    fun hash(): String = sha256(canonical())

    companion object {
        const val SCHEMA_VERSION = "jidan.daily-note.receipt.v0.1"
    }
}

object DailyNoteReceiptSemantics {
    fun validate(data: DailyNoteReceiptData) {
        check(data.requestId.matches(UUID))
        check(data.targetIdentitySha256.matches(SHA256))
        check(data.planSha256.matches(SHA256))
        check(data.payloadSha256.matches(SHA256))
        check(data.beforeSha256.matches(SHA256))
        check(data.afterSha256.isEmpty() || data.afterSha256.matches(SHA256))
        check(data.previousHash.matches(SHA256))
        check(data.attemptHash == null || data.attemptHash.matches(SHA256))
        check(data.windowId >= 0)
        check(!data.rawPayloadInReceipt)
        when (data.stepId) {
            "set_daily_note" -> {
                check(data.kind == UiActionKind.SET_TEXT.name)
                check(!data.noteSaved)
            }
            "save_daily_note" -> check(data.kind == UiActionKind.CLICK.name)
            else -> error("unsupported daily receipt step")
        }
        when (data.phase) {
            PREPARED -> {
                check(data.executorAttempted == false && data.osAccepted == null)
                check(!data.postconditionVerified && !data.noteSaved)
                check(data.navigationAccepted == null)
                check(data.afterSha256.isEmpty())
                check(data.effectStatus == EffectStatus.NOT_ATTEMPTED.name)
                check(data.outcome == "prepared" && data.attemptHash == null)
            }
            RESULT -> when {
                data.executorAttempted == false -> {
                    check(data.osAccepted != true && !data.postconditionVerified)
                    check(!data.noteSaved && data.navigationAccepted == null)
                    check(data.afterSha256 == data.beforeSha256)
                    check(data.effectStatus == EffectStatus.FAILED_BEFORE_EFFECT.name)
                    check(data.outcome == "failed_before_effect")
                    check(data.attemptHash == null || data.attemptHash == data.previousHash)
                }
                data.postconditionVerified -> {
                    check(data.executorAttempted == true && data.osAccepted == true)
                    check(data.afterSha256.matches(SHA256) && data.afterSha256 != data.beforeSha256)
                    check(data.effectStatus == EffectStatus.TRANSITION_VERIFIED.name)
                    check(data.outcome == "transition_verified")
                    check(data.attemptHash == data.previousHash)
                    check(data.noteSaved == (data.stepId == "save_daily_note"))
                    if (!data.noteSaved) check(data.navigationAccepted == null)
                }
                else -> {
                    check(data.executorAttempted == true && !data.noteSaved)
                    check(data.navigationAccepted == null)
                    check(data.effectStatus == EffectStatus.OUTCOME_UNKNOWN.name)
                    check(data.outcome == "outcome_unknown")
                    check(data.attemptHash == data.previousHash)
                }
            }
            RECOVERY -> {
                check(data.executorAttempted == null && data.osAccepted == null)
                check(!data.postconditionVerified && !data.noteSaved)
                check(data.navigationAccepted == null)
                check(data.afterSha256.isEmpty())
                check(data.effectStatus == EffectStatus.OUTCOME_UNKNOWN.name)
                check(data.outcome == "interrupted_outcome_unknown")
                check(data.attemptHash == data.previousHash)
            }
            else -> error("unsupported daily receipt phase")
        }
    }

    const val PREPARED = "PREPARED"
    const val RESULT = "RESULT"
    const val RECOVERY = "RECOVERY"
    val SHA256 = Regex("^[0-9a-f]{64}$")
    private val UUID = Regex(
        "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        RegexOption.IGNORE_CASE,
    )
}

class DailyNoteReceiptStore(context: Context) {
    private val file = File(context.filesDir, "jidan-daily-note-receipts.jsonl")

    @Synchronized
    fun verify(): Boolean = runCatching { verifiedRecords() }.isSuccess

    @Synchronized
    fun prepare(
        session: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): PreparedAccessibilityAttempt {
        requireDaily(session, plan, step)
        val records = verifiedRecords()
        check(records.lastOrNull()?.data?.phase != DailyNoteReceiptSemantics.PREPARED)
        val previous = records.lastOrNull()?.hash ?: GENESIS
        val data = baseRecord(
            phase = DailyNoteReceiptSemantics.PREPARED,
            session = session,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
            afterSha256 = "",
            executorAttempted = false,
            osAccepted = null,
            postconditionVerified = false,
            navigationAccepted = null,
            outcome = "prepared",
            attemptHash = null,
            previousHash = previous,
        )
        return PreparedAccessibilityAttempt(appendVerified(data))
    }

    @Synchronized
    fun complete(
        prepared: PreparedAccessibilityAttempt,
        session: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        afterSha256: String,
        executorAttempted: Boolean,
        osAccepted: Boolean?,
        postconditionVerified: Boolean,
        navigationAccepted: Boolean? = null,
    ): String {
        requireDaily(session, plan, step)
        val records = verifiedRecords()
        val last = records.lastOrNull() ?: error("prepared daily attempt is missing")
        check(last.hash == prepared.hash && last.data.phase == DailyNoteReceiptSemantics.PREPARED)
        check(last.data.sessionId == session.id && last.data.planSha256 == plan.planSha256)
        check(last.data.stepId == step.id)
        check(last.data.requestId == session.requestId)
        check(last.data.targetIdentitySha256 == session.targetIdentity.digestSha256)
        check(last.data.windowId == windowId)
        check(last.data.kind == step.kind.name)
        check(last.data.payloadSha256 == session.payloadSha256)
        check(last.data.beforeSha256 == beforeSha256)
        val effectStatus = when {
            !executorAttempted -> EffectStatus.FAILED_BEFORE_EFFECT
            postconditionVerified -> EffectStatus.TRANSITION_VERIFIED
            else -> EffectStatus.OUTCOME_UNKNOWN
        }
        val outcome = when (effectStatus) {
            EffectStatus.FAILED_BEFORE_EFFECT -> "failed_before_effect"
            EffectStatus.TRANSITION_VERIFIED -> "transition_verified"
            EffectStatus.OUTCOME_UNKNOWN -> "outcome_unknown"
            EffectStatus.NOT_ATTEMPTED -> error("prepared status cannot complete")
        }
        return appendVerified(
            baseRecord(
                phase = DailyNoteReceiptSemantics.RESULT,
                session = session,
                windowId = windowId,
                plan = plan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = afterSha256,
                executorAttempted = executorAttempted,
                osAccepted = osAccepted,
                postconditionVerified = postconditionVerified,
                navigationAccepted = navigationAccepted,
                outcome = outcome,
                attemptHash = prepared.hash,
                previousHash = prepared.hash,
            ),
        )
    }

    @Synchronized
    fun failedBeforeEffect(
        session: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): String {
        requireDaily(session, plan, step)
        val records = verifiedRecords()
        check(records.lastOrNull()?.data?.phase != DailyNoteReceiptSemantics.PREPARED)
        val previous = records.lastOrNull()?.hash ?: GENESIS
        return appendVerified(
            baseRecord(
                phase = DailyNoteReceiptSemantics.RESULT,
                session = session,
                windowId = windowId,
                plan = plan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = beforeSha256,
                executorAttempted = false,
                osAccepted = false,
                postconditionVerified = false,
                navigationAccepted = null,
                outcome = "failed_before_effect",
                attemptHash = null,
                previousHash = previous,
            ),
        )
    }

    @Synchronized
    fun recoverDanglingAttempt(): Boolean {
        val records = verifiedRecords()
        val last = records.lastOrNull() ?: return false
        if (last.data.phase != DailyNoteReceiptSemantics.PREPARED) return false
        appendVerified(
            last.data.copy(
                phase = DailyNoteReceiptSemantics.RECOVERY,
                timestampMs = System.currentTimeMillis(),
                afterSha256 = "",
                executorAttempted = null,
                osAccepted = null,
                postconditionVerified = false,
                effectStatus = EffectStatus.OUTCOME_UNKNOWN.name,
                noteSaved = false,
                navigationAccepted = null,
                outcome = "interrupted_outcome_unknown",
                attemptHash = last.hash,
                previousHash = last.hash,
            ),
        )
        return true
    }

    private fun baseRecord(
        phase: String,
        session: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        afterSha256: String,
        executorAttempted: Boolean?,
        osAccepted: Boolean?,
        postconditionVerified: Boolean,
        navigationAccepted: Boolean?,
        outcome: String,
        attemptHash: String?,
        previousHash: String,
    ): DailyNoteReceiptData {
        val effectStatus = when {
            phase == DailyNoteReceiptSemantics.PREPARED -> EffectStatus.NOT_ATTEMPTED
            phase == DailyNoteReceiptSemantics.RECOVERY -> EffectStatus.OUTCOME_UNKNOWN
            executorAttempted == false -> EffectStatus.FAILED_BEFORE_EFFECT
            postconditionVerified -> EffectStatus.TRANSITION_VERIFIED
            else -> EffectStatus.OUTCOME_UNKNOWN
        }
        return DailyNoteReceiptData(
            phase = phase,
            timestampMs = System.currentTimeMillis(),
            sessionId = session.id,
            requestId = requireNotNull(session.requestId),
            targetIdentitySha256 = session.targetIdentity.digestSha256,
            windowId = windowId,
            planSha256 = plan.planSha256,
            stepId = step.id,
            kind = step.kind.name,
            payloadSha256 = requireNotNull(session.payloadSha256),
            beforeSha256 = beforeSha256,
            afterSha256 = afterSha256,
            executorAttempted = executorAttempted,
            osAccepted = osAccepted,
            postconditionVerified = postconditionVerified,
            effectStatus = effectStatus.name,
            noteSaved = step.id == "save_daily_note" && postconditionVerified,
            navigationAccepted = navigationAccepted,
            rawPayloadInReceipt = false,
            outcome = outcome,
            attemptHash = attemptHash,
            previousHash = previousHash,
        )
    }

    private fun requireDaily(session: LabSession, plan: UiActionPlan, step: PlannedUiAction) {
        check(session.taskKind == AccessibilityTaskKind.DAILY_NOTE)
        check(session.targetIdentity.packageName == ExecutionLaneResolver.DAILY_PACKAGE)
        check(plan.lane == ExecutionLane.OWNED_APP)
        check(step.selector.packageName == ExecutionLaneResolver.DAILY_PACKAGE)
    }

    private fun appendVerified(data: DailyNoteReceiptData): String {
        DailyNoteReceiptSemantics.validate(data)
        val hash = data.hash()
        val record = data.toJson().put("hash", hash)
        FileOutputStream(file, true).use { stream ->
            stream.write((record.toString() + "\n").toByteArray(Charsets.UTF_8))
            stream.flush()
            stream.fd.sync()
        }
        return hash
    }

    private fun verifiedRecords(): List<Stored> {
        if (!file.isFile) return emptyList()
        val records = file.readLines(Charsets.UTF_8).filter(String::isNotBlank).map(::JSONObject)
        var previous = GENESIS
        val verified = records.map { json ->
            check(json.keys().asSequence().toSet() == EXPECTED_FIELDS)
            val data = json.toData()
            DailyNoteReceiptSemantics.validate(data)
            check(data.previousHash == previous)
            val hash = json.getString("hash")
            check(hash == data.hash())
            previous = hash
            Stored(data, hash)
        }
        verified.forEachIndexed { index, record ->
            if (record.data.phase == DailyNoteReceiptSemantics.PREPARED && index < verified.lastIndex) {
                val completion = verified[index + 1]
                check(
                    completion.data.phase in setOf(
                        DailyNoteReceiptSemantics.RESULT,
                        DailyNoteReceiptSemantics.RECOVERY,
                    ) && completion.data.attemptHash == record.hash,
                )
                check(
                    listOf(
                        completion.data.sessionId == record.data.sessionId,
                        completion.data.requestId == record.data.requestId,
                        completion.data.targetIdentitySha256 == record.data.targetIdentitySha256,
                        completion.data.windowId == record.data.windowId,
                        completion.data.planSha256 == record.data.planSha256,
                        completion.data.stepId == record.data.stepId,
                        completion.data.kind == record.data.kind,
                        completion.data.payloadSha256 == record.data.payloadSha256,
                        completion.data.beforeSha256 == record.data.beforeSha256,
                    ).all { it },
                )
            }
            if (record.data.attemptHash != null) {
                check(index > 0 && verified[index - 1].hash == record.data.attemptHash)
            }
        }
        return verified
    }

    private fun DailyNoteReceiptData.toJson(): JSONObject = JSONObject()
        .put("schemaVersion", DailyNoteReceiptData.SCHEMA_VERSION)
        .put("phase", phase).put("timestampMs", timestampMs)
        .put("sessionId", sessionId).put("requestId", requestId)
        .put("lane", ExecutionLane.OWNED_APP.name)
        .put("targetPackage", ExecutionLaneResolver.DAILY_PACKAGE)
        .put("targetIdentitySha256", targetIdentitySha256).put("windowId", windowId)
        .put("planSha256", planSha256).put("stepId", stepId).put("kind", kind)
        .put("payloadSha256", payloadSha256).put("beforeSha256", beforeSha256)
        .put("afterSha256", afterSha256)
        .put("executorAttempted", executorAttempted ?: JSONObject.NULL)
        .put("osAccepted", osAccepted ?: JSONObject.NULL)
        .put("postconditionVerified", postconditionVerified).put("effectStatus", effectStatus)
        .put("realWorldStatus", RealWorldStatus.OWNED_LOCAL_APP.name)
        .put("noteSaved", noteSaved)
        .put("navigationAccepted", navigationAccepted ?: JSONObject.NULL)
        .put("rawPayloadInReceipt", rawPayloadInReceipt).put("outcome", outcome)
        .put("attemptHash", attemptHash ?: JSONObject.NULL).put("previousHash", previousHash)

    private fun JSONObject.toData(): DailyNoteReceiptData {
        check(getString("schemaVersion") == DailyNoteReceiptData.SCHEMA_VERSION)
        check(getString("lane") == ExecutionLane.OWNED_APP.name)
        check(getString("targetPackage") == ExecutionLaneResolver.DAILY_PACKAGE)
        check(getString("realWorldStatus") == RealWorldStatus.OWNED_LOCAL_APP.name)
        return DailyNoteReceiptData(
            phase = getString("phase"), timestampMs = getLong("timestampMs"),
            sessionId = getString("sessionId"), requestId = getString("requestId"),
            targetIdentitySha256 = getString("targetIdentitySha256"), windowId = getInt("windowId"),
            planSha256 = getString("planSha256"), stepId = getString("stepId"), kind = getString("kind"),
            payloadSha256 = getString("payloadSha256"), beforeSha256 = getString("beforeSha256"),
            afterSha256 = getString("afterSha256"), executorAttempted = nullableBoolean("executorAttempted"),
            osAccepted = nullableBoolean("osAccepted"), postconditionVerified = getBoolean("postconditionVerified"),
            effectStatus = getString("effectStatus"), noteSaved = getBoolean("noteSaved"),
            navigationAccepted = nullableBoolean("navigationAccepted"),
            rawPayloadInReceipt = getBoolean("rawPayloadInReceipt"), outcome = getString("outcome"),
            attemptHash = if (isNull("attemptHash")) null else getString("attemptHash"),
            previousHash = getString("previousHash"),
        )
    }

    private fun JSONObject.nullableBoolean(name: String): Boolean? =
        if (isNull(name)) null else getBoolean(name)

    private data class Stored(val data: DailyNoteReceiptData, val hash: String)

    companion object {
        private const val GENESIS =
            "0000000000000000000000000000000000000000000000000000000000000000"
        private val EXPECTED_FIELDS = setOf(
            "schemaVersion", "phase", "timestampMs", "sessionId", "requestId", "lane",
            "targetPackage", "targetIdentitySha256", "windowId", "planSha256", "stepId", "kind",
            "payloadSha256", "beforeSha256", "afterSha256", "executorAttempted", "osAccepted",
            "postconditionVerified", "effectStatus", "realWorldStatus", "noteSaved",
            "navigationAccepted", "rawPayloadInReceipt", "outcome", "attemptHash", "previousHash", "hash",
        )
    }
}
