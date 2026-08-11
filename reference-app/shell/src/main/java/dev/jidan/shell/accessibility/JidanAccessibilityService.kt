package dev.jidan.shell.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

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

    private const val FIRST_FRAME_TIMEOUT_MS = 3_000L
}

class JidanAccessibilityService : AccessibilityService() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var receipts: AccessibilityReceiptStore
    private var receiptsHealthy = false
    private var sessionId: String? = null
    private var plan: UiActionPlan? = null
    private var nextStep = 0
    private var preEffectReobserveRemaining = 1
    private var executing = false
    private var terminal = false
    private var boundWindowId: Int? = null
    private var currentPrepared: PreparedAccessibilityAttempt? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        receipts = AccessibilityReceiptStore(this)
        receiptsHealthy = receipts.verify()
        val recovered = if (receiptsHealthy) {
            runCatching { receipts.recoverDanglingAttempt() }
                .onFailure { receiptsHealthy = false }
                .getOrDefault(false)
        } else {
            false
        }
        serviceInfo = serviceInfo.apply {
            flags = flags or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
            packageNames = arrayOf(ExecutionLaneResolver.SANDBOX_PACKAGE)
        }
        AccessibilityServiceBridge.onConnected()
        when {
            !receiptsHealthy -> AccessibilityServiceBridge.update("辅助操作回执链损坏，执行器已停用")
            recovered -> AccessibilityServiceBridge.update("发现中断动作，结果记为未知且没有重试")
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val packageName = event?.packageName?.toString() ?: return
        if (packageName != ExecutionLaneResolver.SANDBOX_PACKAGE) return
        if (LabSessionRegistry.activeSession() == null) return
        handler.post { advanceIfPossible() }
    }

    override fun onInterrupt() {
        recoverCurrentAttemptIfNeeded()
        LabSessionRegistry.clearActive()
        resetExecutionState(terminalState = true)
        AccessibilityServiceBridge.update("辅助操作被系统中断；当前实验已清除")
    }

    override fun onDestroy() {
        recoverCurrentAttemptIfNeeded()
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
        }
        if (executing || terminal) return
        if (!receiptsHealthy) {
            finish(active.id, "回执链不可用，实验没有执行")
            return
        }
        val root = rootInActiveWindow
        if (root == null) {
            reobserveBeforeEffectOrStop(active.id, "当前页面无法读取，实验已停止")
            return
        }
        if (root.packageName?.toString() != ExecutionLaneResolver.SANDBOX_PACKAGE) {
            finish(active.id, "窗口已经离开实验页，旧动作不会继续")
            return
        }
        if (!sessionTokenMatches(root, active.launchNonce)) {
            finish(active.id, "实验页启动令牌不匹配，旧动作不会继续")
            return
        }
        AccessibilityServiceBridge.markFirstFrameObserved(active.id)

        val trust = AccessibilityExecutionPolicy.decide(this, root.packageName.toString())
        if (
            trust.lane != ExecutionLane.SANDBOX ||
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
            AccessibilityBrain.planSandbox(
                sessionId = active.id,
                observation = before,
                targetIdentity = active.targetIdentity,
                references = active.valueReferences,
            )
        }.getOrElse {
            finish(active.id, "页面结构不完整，实验已停止")
            return
        }.also { created -> plan = created }
        if (currentPlan.targetIdentitySha256 != active.targetIdentity.digestSha256) {
            finish(active.id, "计划绑定的目标身份已经变化")
            return
        }
        if (currentPlan.handProviderId != HandProviderIds.BUILTIN_ACCESSIBILITY) {
            finish(active.id, "计划绑定的执行底座已经变化")
            return
        }
        if (
            currentPlan.handProviderRegistrationSha256 !=
            HandProviderIds.BUILTIN_ACCESSIBILITY_REGISTRATION_SHA256
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
            receipts.prepare(
                sessionId = active.id,
                targetIdentity = active.targetIdentity,
                windowId = before.windowId,
                plan = currentPlan,
                step = step,
                beforeSha256 = before.evidenceSha256,
            )
        }.getOrElse {
            receiptsHealthy = false
            finish(active.id, "动作意图没有写入回执，所以实验没有执行")
            return
        }
        currentPrepared = prepared

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
                root.packageName?.toString() == ExecutionLaneResolver.SANDBOX_PACKAGE &&
                root.windowId == boundWindowId &&
                sessionTokenMatches(root, active.launchNonce)
        val identityStillMatches = if (packageAndWindowMatch) {
            AccessibilityExecutionPolicy.decide(this, ExecutionLaneResolver.SANDBOX_PACKAGE).identity ==
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
        val receiptWritten = runCatching {
            receipts.complete(
                prepared = prepared,
                sessionId = active.id,
                targetIdentity = active.targetIdentity,
                windowId = boundWindowId ?: -1,
                plan = currentPlan,
                step = step,
                beforeSha256 = beforeSha256,
                afterSha256 = after?.evidenceSha256.orEmpty(),
                executorAttempted = true,
                osAccepted = osAccepted,
                postconditionVerified = verified,
            )
        }.isSuccess
        if (!receiptWritten) {
            receiptsHealthy = false
            finish(active.id, "动作可能已经发生，但结果回执写入失败；没有重试")
            return
        }
        currentPrepared = null
        if (!verified) {
            finish(active.id, "动作已经尝试，但结果无法确认；没有重试")
            return
        }
        nextStep += 1
        preEffectReobserveRemaining = 1
        executing = false
        AccessibilityServiceBridge.update("已核验 ${nextStep}/${currentPlan.steps.size} 个动作")
        if (nextStep >= currentPlan.steps.size) {
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
            receipts.complete(
                prepared = prepared,
                sessionId = active.id,
                targetIdentity = active.targetIdentity,
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
        if (written) currentPrepared = null
        if (!written) receiptsHealthy = false
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
            receipts.failedBeforeEffect(
                sessionId = active.id,
                targetIdentity = active.targetIdentity,
                windowId = boundWindowId ?: -1,
                plan = currentPlan,
                step = step,
                beforeSha256 = beforeSha256,
            )
        }.isSuccess
        if (!written) receiptsHealthy = false
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

    private fun sessionTokenMatches(root: AccessibilityNodeInfo, launchNonce: String): Boolean {
        val statusId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_status"
        val status = root.findAccessibilityNodeInfosByViewId(statusId).singleOrNull() ?: return false
        val marker = status.contentDescription?.toString() ?: return false
        return marker.startsWith("$SESSION_MARKER_PREFIX${sha256(launchNonce)}|")
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
    }

    private fun recoverCurrentAttemptIfNeeded() {
        if (currentPrepared == null || !::receipts.isInitialized) return
        val recovered = runCatching { receipts.recoverDanglingAttempt() }
            .onFailure { receiptsHealthy = false }
            .getOrDefault(false)
        if (recovered) currentPrepared = null
    }

    private data class PerformResult(
        val executorAttempted: Boolean,
        val osAccepted: Boolean?,
    )

    companion object {
        private const val SESSION_MARKER_PREFIX = "jidan_lab_session:"
        private const val MAX_ANCESTOR_DEPTH = 4
        private const val REOBSERVE_DELAY_MS = 250L
        private const val VERIFY_DELAY_MS = 420L
        private const val NEXT_STEP_DELAY_MS = 180L
    }
}
