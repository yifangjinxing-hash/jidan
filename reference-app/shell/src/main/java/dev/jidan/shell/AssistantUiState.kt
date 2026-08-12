package dev.jidan.shell

/**
 * One visible truth for the assistant surface. A handoff is not completion;
 * only a verified result may use [Tone.SUCCESS].
 */
data class AssistantUiState(
    val phase: Phase,
    val title: String,
    val detail: String = "",
    val tone: Tone,
) {
    enum class Phase {
        IDLE,
        PREPARING_MICROPHONE,
        LISTENING,
        RECOGNIZING,
        EXECUTING,
        VERIFYING,
        HANDED_OFF,
        COMPLETED,
        FAILED,
    }

    enum class Tone { IDLE, LISTENING, WORKING, SUCCESS, FAILURE }

    companion object {
        fun preparingMicrophone() = AssistantUiState(
            phase = Phase.PREPARING_MICROPHONE,
            title = "正在打开麦克风…",
            tone = Tone.WORKING,
        )

        fun listening(heard: String = "") = AssistantUiState(
            phase = Phase.LISTENING,
            title = "正在听",
            detail = heard,
            tone = Tone.LISTENING,
        )

        fun recognizing() = AssistantUiState(
            phase = Phase.RECOGNIZING,
            title = "听完了，正在识别…",
            tone = Tone.WORKING,
        )

        fun executing(action: String) = AssistantUiState(
            phase = Phase.EXECUTING,
            title = "正在做：$action",
            tone = Tone.WORKING,
        )

        fun verifying(action: String) = AssistantUiState(
            phase = Phase.VERIFYING,
            title = "已经开始，正在核对结果",
            detail = action,
            tone = Tone.WORKING,
        )

        fun handedOff(action: String) = AssistantUiState(
            phase = Phase.HANDED_OFF,
            title = "已经返回鸡蛋",
            detail = "$action 已交给安卓；目标页面结果未核对",
            tone = Tone.IDLE,
        )

        fun handoffNotObserved(action: String) = AssistantUiState(
            phase = Phase.HANDED_OFF,
            title = "没有观察到页面切换",
            detail = "安卓已接收 $action；目标页面结果未核对",
            tone = Tone.IDLE,
        )

        fun completed(result: String, detail: String = "") = AssistantUiState(
            phase = Phase.COMPLETED,
            title = "完成：$result",
            detail = detail,
            tone = Tone.SUCCESS,
        )

        fun failed(reason: String, detail: String = "") = AssistantUiState(
            phase = Phase.FAILED,
            title = "没做成：$reason",
            detail = detail,
            tone = Tone.FAILURE,
        )
    }
}
