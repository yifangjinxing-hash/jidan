package dev.jidan.shell.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

data class DailyNoteCompletion(
    val requestId: String,
    val noteText: String,
    val noteSha256: String,
    val receiptHash: String,
    val navigationAccepted: Boolean,
    val createdAtMs: Long,
)

object AccessibilityServiceBridge {
    private val bridgeHandler = Handler(Looper.getMainLooper())

    @Volatile
    var connected: Boolean = false
        private set

    @Volatile
    var lastStatus: String = "辅助操作尚未开启"
        private set

    @Volatile
    private var watchedSessionId: String? = null

    @Volatile
    private var dailyCompletion: DailyNoteCompletion? = null

    internal fun onConnected() {
        connected = true
        lastStatus = "辅助操作已就绪"
    }

    internal fun onDisconnected() {
        connected = false
        lastStatus = "辅助操作已断开"
    }

    internal fun update(status: String) {
        lastStatus = status
    }

    fun armFirstFrameWatchdog(sessionId: String) {
        watchedSessionId = sessionId
        bridgeHandler.postDelayed({
            if (watchedSessionId != sessionId) return@postDelayed
            watchedSessionId = null
            LabSessionRegistry.clear(sessionId)
            lastStatus = "辅助操作没有在 3 秒内看到实验页；会话已取消"
        }, FIRST_FRAME_TIMEOUT_MS)
    }

    fun markFirstFrameObserved(sessionId: String) {
        if (watchedSessionId == sessionId) watchedSessionId = null
    }

    fun cancelWatchdog(sessionId: String) {
        if (watchedSessionId == sessionId) watchedSessionId = null
    }

    internal fun publishDailyCompletion(completion: DailyNoteCompletion) {
        dailyCompletion = completion
    }

    fun consumeDailyCompletion(requestId: String): DailyNoteCompletion? {
        val current = dailyCompletion ?: return null
        if (System.currentTimeMillis() - current.createdAtMs > DAILY_RESULT_TTL_MS) {
            dailyCompletion = null
            return null
        }
        if (current.requestId != requestId) return null
        dailyCompletion = null
        return current
    }

    private const val FIRST_FRAME_TIMEOUT_MS = 3_000L
    private const val DAILY_RESULT_TTL_MS = 60_000L
}

class JidanAccessibilityService : AccessibilityService() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var receipts: AccessibilityReceiptStore
    private lateinit var dailyReceipts: DailyNoteReceiptStore
    private var receiptsHealthy = false
    private var dailyReceiptsHealthy = false
    private var sessionId: String? = null
    private var plan: UiActionPlan? = null
    private var nextStep = 0
    private var preEffectReobserveRemaining = 1
    private var executing = false
    private var terminal = false
    private var boundWindowId: Int? = null
    private var currentPrepared: PreparedAccessibilityAttempt? = null
    private var currentPreparedTask: AccessibilityTaskKind? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        receipts = AccessibilityReceiptStore(this)
        dailyReceipts = DailyNoteReceiptStore(this)
        receiptsHealthy = receipts.verify()
        dailyReceiptsHealthy = dailyReceipts.verify()
        val recovered = if (receiptsHealthy) {
            runCatching { receipts.recoverDanglingAttempt() }
                .onFailure { receiptsHealthy = false }
                .getOrDefault(false)
        } else {
            false
        }
        val dailyRecovered = if (dailyReceiptsHealthy) {
            runCatching { dailyReceipts.recoverDanglingAttempt() }
                .onFailure { dailyReceiptsHealthy = false }
                .getOrDefault(false)
        } else {
            false
        }
        serviceInfo = serviceInfo.apply {
            flags = flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
            packageNames = arrayOf(
                ExecutionLaneResolver.SANDBOX_PACKAGE,
                ExecutionLaneResolver.DAILY_PACKAGE,
            )
        }
        AccessibilityServiceBridge.onConnected()
        when {
            !receiptsHealthy -> AccessibilityServiceBridge.update("辅助操作回执链损坏，执行器已停用")
            !dailyReceiptsHealthy -> AccessibilityServiceBridge.update("日常动作回执链损坏，日常执行器已停用")
            recovered || dailyRecovered -> AccessibilityServiceBridge.update("发现中断动作，结果记为未知且没有重试")
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val packageName = event?.packageName?.toString() ?: return
        val active = LabSessionRegistry.activeSession() ?: return
        if (packageName != active.targetSpec.packageName) return
        handler.post { advanceIfPossible() }
    }

    override fun onInterrupt() {
        recoverCurrentAttemptIfNeeded()
        sessionId?.let(AccessibilityServiceBridge::cancelWatchdog)
        LabSessionRegistry.clearActive()
        resetExecutionState(terminalState = true)
        AccessibilityServiceBridge.update("辅助操作被系统中断；当前实验已清除")
    }

    override fun onDestroy() {
        recoverCurrentAttemptIfNeeded()
        sessionId?.let(AccessibilityServiceBridge::cancelWatchdog)
        LabSessionRegistry.clearActive()
        handler.removeCallbacksAndMessages(null)
        resetExecutionState(terminalState = true)
        AccessibilityServiceBridge.onDisconnected()
        super.onDestroy()
    }

    private fun advanceIfPossible() {
        val active = LabSessionRegistry.activeSession()
        if (active == null) {
            if (sessionId != null && !terminal) {
                resetExecutionState(terminalState = true)
                AccessibilityServiceBridge.update("实验会话已过期，旧动作不会继续")
            }
            return
        }
        if (sessionId != active.id) {
            sessionId = active.id
            plan = null
            nextStep = 0
            preEffectReobserveRemaining = 1
            executing = false
            terminal = false
            boundWindowId = null
            currentPrepared = null
            currentPreparedTask = null
        }
        if (executing || terminal) return
        if (!receiptStoreHealthy(active.taskKind)) {
            finish(active.id, "回执链不可用，实验没有执行")
            return
        }
        val root = rootInActiveWindow
        if (root == null) {
            reobserveBeforeEffectOrStop(active.id, "当前页面无法读取，实验已停止")
            return
        }
        if (root.packageName?.toString() != active.targetSpec.packageName) {
            finish(active.id, "窗口已经离开实验页，旧动作不会继续")
            return
        }
        if (!sessionTokenMatches(root, active)) {
            finish(active.id, "实验页启动令牌不匹配，旧动作不会继续")
            return
        }
        AccessibilityServiceBridge.markFirstFrameObserved(active.id)

        val trust = AccessibilityExecutionPolicy.decide(this, root.packageName.toString())
        if (
            trust.lane != active.targetSpec.lane ||
            trust.identity == null ||
            trust.identity != active.targetIdentity
        ) {
            finish(active.id, "目标身份已经变化：${trust.reason}")
            return
        }
        val before = runCatching { AccessibilitySnapshotter.capture(root) }.getOrElse {
            reobserveBeforeEffectOrStop(active.id, "页面树无法读取，实验已停止")
            return
        }
        val expectedWindow = boundWindowId
        if (expectedWindow == null) {
            boundWindowId = before.windowId
        } else if (before.windowId != expectedWindow) {
            stopWithPreEffectReceiptIfPossible(active, before, "窗口身份已经变化，实验已停止")
            return
        }

        val currentPlan = plan ?: runCatching {
            when (active.taskKind) {
                AccessibilityTaskKind.SANDBOX_LAB -> AccessibilityBrain.planSandbox(
                    sessionId = active.id,
                    observation = before,
                    targetIdentity = active.targetIdentity,
                    references = active.valueReferences,
                )
                AccessibilityTaskKind.DAILY_NOTE -> DailyNoteBrain.plan(active, before)
            }
        }.getOrElse {
            finish(active.id, "页面结构不完整，实验已停止")
            return
        }.also { created -> plan = created }
        if (currentPlan.targetIdentitySha256 != active.targetIdentity.digestSha256) {
            finish(active.id, "计划绑定的目标身份已经变化")
            return
        }
        val expectedProvider = when (active.taskKind) {
            AccessibilityTaskKind.SANDBOX_LAB -> HandProviderIds.BUILTIN_ACCESSIBILITY
            AccessibilityTaskKind.DAILY_NOTE -> HandProviderIds.DAILY_ACCESSIBILITY
        }
        val expectedRegistration = when (active.taskKind) {
            AccessibilityTaskKind.SANDBOX_LAB ->
                HandProviderIds.BUILTIN_ACCESSIBILITY_REGISTRATION_SHA256
            AccessibilityTaskKind.DAILY_NOTE ->
                HandProviderIds.DAILY_ACCESSIBILITY_REGISTRATION_SHA256
        }
        if (currentPlan.handProviderId != expectedProvider) {
            finish(active.id, "计划绑定的执行底座已经变化")
            return
        }
        if (
            currentPlan.handProviderRegistrationSha256 != expectedRegistration
        ) {
            finish(active.id, "执行底座的注册定义已经变化")
            return
        }

        if (nextStep >= currentPlan.steps.size || nextStep >= currentPlan.maxSteps) {
            finish(active.id, "实验完成：5 个动作全部核验")
            return
        }

        val step = currentPlan.steps[nextStep]
        val semanticMatches = before.nodes.filter { snapshot ->
            snapshot.packageName == step.selector.packageName &&
                snapshot.viewId == step.selector.viewId
        }
        val nodeMatches = root.findAccessibilityNodeInfosByViewId(step.selector.viewId)
        if (
            semanticMatches.size != 1 ||
            !selectorMatches(step.selector, semanticMatches.single()) ||
            nodeMatches.size != 1 ||
            !selectorMatches(step.selector, nodeMatches.single())
        ) {
            if (preEffectReobserveRemaining > 0) {
                preEffectReobserveRemaining -= 1
                postForSession(active.id, REOBSERVE_DELAY_MS) { advanceIfPossible() }
            } else {
                recordFailedBeforeEffect(
                    active = active,
                    currentPlan = currentPlan,
                    step = step,
                    beforeSha256 = before.evidenceSha256,
                    message = "目标不唯一、角色不符或已经消失，实验已停止",
                )
            }
            return
        }

        val prepared = runCatching {
            prepareReceipt(active, before.windowId, currentPlan, step, before.evidenceSha256)
        }.getOrElse {
            markReceiptStoreUnhealthy(active.taskKind)
            finish(active.id, "动作意图没有写入回执，所以实验没有执行")
            return
        }
        currentPrepared = prepared
        currentPreparedTask = active.taskKind

        executing = true
        val performResult = runCatching {
            perform(step, nodeMatches.single(), active.id)
        }.getOrElse {
            PerformResult(executorAttempted = true, osAccepted = false)
        }
        if (!performResult.executorAttempted) {
            completeAndStopBeforeEffect(
                active = active,
                currentPlan = currentPlan,
                step = step,
                beforeSha256 = before.evidenceSha256,
                prepared = prepared,
            )
            return
        }

        postForSession(active.id, VERIFY_DELAY_MS) {
            verifyTransition(
                active = active,
                currentPlan = currentPlan,
                step = step,
                beforeSha256 = before.evidenceSha256,
                prepared = prepared,
                osAccepted = performResult.osAccepted,
            )
        }
    }

    private fun perform(
        step: PlannedUiAction,
        node: AccessibilityNodeInfo,
        activeSessionId: String,
    ): PerformResult = when (step.kind) {
        UiActionKind.SET_TEXT -> {
            val reference = step.ephemeralValueRef
                ?: return PerformResult(executorAttempted = false, osAccepted = null)
            val value = LabSessionRegistry.resolveAndConsume(
                sessionId = activeSessionId,
                reference = reference,
                actionId = step.id,
                selectorViewId = step.selector.viewId,
                sensitivity = step.sensitivity,
            ) ?: return PerformResult(executorAttempted = false, osAccepted = null)
            val arguments = Bundle().apply {
                putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    value,
                )
            }
            PerformResult(
                executorAttempted = true,
                osAccepted = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments),
            )
        }
        UiActionKind.CLICK -> {
            val target = clickableNode(node)
                ?: return PerformResult(executorAttempted = false, osAccepted = null)
            PerformResult(
                executorAttempted = true,
                osAccepted = target.performAction(AccessibilityNodeInfo.ACTION_CLICK),
            )
        }
    }

    private fun clickableNode(start: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var candidate: AccessibilityNodeInfo? = start
        repeat(MAX_ANCESTOR_DEPTH + 1) {
            val current = candidate ?: return null
            if (current.isClickable) return current
            candidate = current.parent
        }
        return null
    }

    private fun verifyTransition(
        active: LabSession,
        currentPlan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        prepared: PreparedAccessibilityAttempt,
        osAccepted: Boolean?,
    ) {
        if (sessionId != active.id) return
        val currentSession = LabSessionRegistry.activeSession()
        val root = rootInActiveWindow
        val packageAndWindowMatch =
            currentSession?.id == active.id &&
                root != null &&
                root.packageName?.toString() == active.targetSpec.packageName &&
                root.windowId == boundWindowId &&
                sessionTokenMatches(root, active)
        val identityStillMatches = if (packageAndWindowMatch) {
            AccessibilityExecutionPolicy.decide(this, active.targetSpec.packageName).identity ==
                active.targetIdentity
        } else {
            false
        }
        val after = if (packageAndWindowMatch && identityStillMatches) {
            runCatching { AccessibilitySnapshotter.capture(root) }.getOrNull()
        } else {
            null
        }
        val markerNode = if (packageAndWindowMatch && identityStillMatches) {
            root.findAccessibilityNodeInfosByViewId(step.postconditionViewId).singleOrNull()
        } else {
            null
        }
        val marker = markerNode?.contentDescription?.toString()?.substringAfterLast('|')
            ?: markerNode?.text?.toString()
        val verified =
            osAccepted == true &&
                after != null &&
                after.evidenceSha256 != beforeSha256 &&
                marker == step.postconditionMarker
        val receiptHash = runCatching {
            completeReceipt(
                active = active,
                prepared = prepared,
                windowId = boundWindowId ?: -1,
                plan = currentPlan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = after?.evidenceSha256.orEmpty(),
                executorAttempted = true,
                osAccepted = osAccepted,
                postconditionVerified = verified,
            )
        }.getOrNull()
        if (receiptHash == null) {
            markReceiptStoreUnhealthy(active.taskKind)
            finish(active.id, "动作可能已经发生，但结果回执写入失败；没有重试")
            return
        }
        currentPrepared = null
        currentPreparedTask = null
        if (!verified) {
            finish(active.id, "动作已经尝试，但结果无法确认；没有重试")
            return
        }
        nextStep += 1
        preEffectReobserveRemaining = 1
        executing = false
        AccessibilityServiceBridge.update("已核验 ${nextStep}/${currentPlan.steps.size} 个动作")
        if (
            active.taskKind == AccessibilityTaskKind.DAILY_NOTE &&
            step.id == "save_daily_note" &&
            nextStep >= currentPlan.steps.size
        ) {
            val navigationAccepted = performGlobalAction(GLOBAL_ACTION_BACK)
            AccessibilityServiceBridge.publishDailyCompletion(
                DailyNoteCompletion(
                    requestId = requireNotNull(active.requestId),
                    noteText = requireNotNull(active.dailyNoteText),
                    noteSha256 = requireNotNull(active.payloadSha256),
                    receiptHash = receiptHash,
                    navigationAccepted = navigationAccepted,
                    createdAtMs = System.currentTimeMillis(),
                ),
            )
            finish(
                active.id,
                if (navigationAccepted) "日常待办已核验保存，正在返回鸡蛋" else "日常待办已核验保存，请手动返回鸡蛋",
            )
        } else if (nextStep >= currentPlan.steps.size) {
            finish(active.id, "实验完成：5 个动作全部核验")
        } else {
            postForSession(active.id, NEXT_STEP_DELAY_MS) { advanceIfPossible() }
        }
    }

    private fun completeAndStopBeforeEffect(
        active: LabSession,
        currentPlan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        prepared: PreparedAccessibilityAttempt,
    ) {
        val written = runCatching {
            completeReceipt(
                active = active,
                prepared = prepared,
                windowId = boundWindowId ?: -1,
                plan = currentPlan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = beforeSha256,
                executorAttempted = false,
                osAccepted = null,
                postconditionVerified = false,
            )
        }.isSuccess
        if (written) {
            currentPrepared = null
            currentPreparedTask = null
        }
        if (!written) markReceiptStoreUnhealthy(active.taskKind)
        finish(active.id, "动作没有交给系统，实验已停止且没有重试")
    }

    private fun recordFailedBeforeEffect(
        active: LabSession,
        currentPlan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        message: String,
    ) {
        val written = runCatching {
            failedBeforeEffectReceipt(
                active,
                boundWindowId ?: -1,
                currentPlan,
                step,
                beforeSha256,
            )
        }.isSuccess
        if (!written) markReceiptStoreUnhealthy(active.taskKind)
        finish(active.id, message)
    }

    private fun stopWithPreEffectReceiptIfPossible(
        active: LabSession,
        before: UiObservation,
        message: String,
    ) {
        val currentPlan = plan
        val step = currentPlan?.steps?.getOrNull(nextStep)
        if (currentPlan != null && step != null) {
            recordFailedBeforeEffect(active, currentPlan, step, before.evidenceSha256, message)
        } else {
            finish(active.id, message)
        }
    }

    private fun reobserveBeforeEffectOrStop(activeSessionId: String, message: String) {
        if (preEffectReobserveRemaining > 0) {
            preEffectReobserveRemaining -= 1
            postForSession(activeSessionId, REOBSERVE_DELAY_MS) { advanceIfPossible() }
        } else {
            finish(activeSessionId, message)
        }
    }

    private fun selectorMatches(selector: UiNodeSelector, snapshot: UiNodeSnapshot): Boolean =
        snapshot.path == selector.expectedPath &&
            snapshot.className == selector.expectedClassName &&
            snapshot.clickable == selector.expectedClickable &&
            snapshot.editable == selector.expectedEditable &&
            snapshot.password == selector.expectedPassword

    private fun selectorMatches(selector: UiNodeSelector, node: AccessibilityNodeInfo): Boolean =
        node.packageName?.toString() == selector.packageName &&
            node.viewIdResourceName == selector.viewId &&
            node.className?.toString() == selector.expectedClassName &&
            node.isClickable == selector.expectedClickable &&
            node.isEditable == selector.expectedEditable &&
            node.isPassword == selector.expectedPassword

    private fun receiptStoreHealthy(taskKind: AccessibilityTaskKind): Boolean = when (taskKind) {
        AccessibilityTaskKind.SANDBOX_LAB -> receiptsHealthy
        AccessibilityTaskKind.DAILY_NOTE -> dailyReceiptsHealthy
    }

    private fun markReceiptStoreUnhealthy(taskKind: AccessibilityTaskKind) {
        when (taskKind) {
            AccessibilityTaskKind.SANDBOX_LAB -> receiptsHealthy = false
            AccessibilityTaskKind.DAILY_NOTE -> dailyReceiptsHealthy = false
        }
    }

    private fun prepareReceipt(
        active: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): PreparedAccessibilityAttempt = when (active.taskKind) {
        AccessibilityTaskKind.SANDBOX_LAB -> receipts.prepare(
            sessionId = active.id,
            targetIdentity = active.targetIdentity,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
        )
        AccessibilityTaskKind.DAILY_NOTE -> dailyReceipts.prepare(
            session = active,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
        )
    }

    private fun completeReceipt(
        active: LabSession,
        prepared: PreparedAccessibilityAttempt,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
        afterSha256: String,
        executorAttempted: Boolean,
        osAccepted: Boolean?,
        postconditionVerified: Boolean,
    ): String = when (active.taskKind) {
        AccessibilityTaskKind.SANDBOX_LAB -> receipts.complete(
            prepared = prepared,
            sessionId = active.id,
            targetIdentity = active.targetIdentity,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
            afterSha256 = afterSha256,
            executorAttempted = executorAttempted,
            osAccepted = osAccepted,
            postconditionVerified = postconditionVerified,
        )
        AccessibilityTaskKind.DAILY_NOTE -> dailyReceipts.complete(
            prepared = prepared,
            session = active,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
            afterSha256 = afterSha256,
            executorAttempted = executorAttempted,
            osAccepted = osAccepted,
            postconditionVerified = postconditionVerified,
        )
    }

    private fun failedBeforeEffectReceipt(
        active: LabSession,
        windowId: Int,
        plan: UiActionPlan,
        step: PlannedUiAction,
        beforeSha256: String,
    ): String = when (active.taskKind) {
        AccessibilityTaskKind.SANDBOX_LAB -> receipts.failedBeforeEffect(
            sessionId = active.id,
            targetIdentity = active.targetIdentity,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
        )
        AccessibilityTaskKind.DAILY_NOTE -> dailyReceipts.failedBeforeEffect(
            session = active,
            windowId = windowId,
            plan = plan,
            step = step,
            beforeSha256 = beforeSha256,
        )
    }

    private fun sessionTokenMatches(root: AccessibilityNodeInfo, active: LabSession): Boolean {
        val status = root.findAccessibilityNodeInfosByViewId(active.targetSpec.statusViewId)
            .singleOrNull() ?: return false
        val marker = status.contentDescription?.toString() ?: return false
        return marker.startsWith("${active.targetSpec.sessionMarkerPrefix}${sha256(active.launchNonce)}|")
    }

    private fun postForSession(activeSessionId: String, delayMs: Long, block: () -> Unit) {
        handler.postDelayed({
            if (sessionId == activeSessionId) block()
        }, delayMs)
    }

    private fun finish(activeSessionId: String, message: String) {
        if (sessionId != activeSessionId) return
        terminal = true
        executing = false
        AccessibilityServiceBridge.cancelWatchdog(activeSessionId)
        LabSessionRegistry.clear(activeSessionId)
        AccessibilityServiceBridge.update(message)
    }

    private fun resetExecutionState(terminalState: Boolean) {
        sessionId = null
        plan = null
        nextStep = 0
        preEffectReobserveRemaining = 1
        executing = false
        terminal = terminalState
        boundWindowId = null
        currentPrepared = null
        currentPreparedTask = null
    }

    private fun recoverCurrentAttemptIfNeeded() {
        if (currentPrepared == null || !::receipts.isInitialized) return
        val taskKind = currentPreparedTask ?: return
        val recovered = runCatching {
            when (taskKind) {
                AccessibilityTaskKind.SANDBOX_LAB -> receipts.recoverDanglingAttempt()
                AccessibilityTaskKind.DAILY_NOTE -> dailyReceipts.recoverDanglingAttempt()
            }
        }
            .onFailure { markReceiptStoreUnhealthy(taskKind) }
            .getOrDefault(false)
        if (recovered) {
            currentPrepared = null
            currentPreparedTask = null
        }
    }

    private data class PerformResult(
        val executorAttempted: Boolean,
        val osAccepted: Boolean?,
    )

    companion object {
        private const val MAX_ANCESTOR_DEPTH = 4
        private const val REOBSERVE_DELAY_MS = 250L
        private const val VERIFY_DELAY_MS = 420L
        private const val NEXT_STEP_DELAY_MS = 180L
    }
}
