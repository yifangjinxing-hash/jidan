package dev.jidan.shell

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import dev.jidan.shell.accessibility.AccessibilityExecutionPolicy
import dev.jidan.shell.accessibility.AccessibilityServiceBridge
import dev.jidan.shell.accessibility.ExecutionLane
import dev.jidan.shell.accessibility.ExecutionLaneResolver
import dev.jidan.shell.accessibility.LabSessionRegistry
import dev.jidan.shell.accessibility.OwnedTargetRegistry
import java.security.MessageDigest

sealed interface DispatchResult {
    data class Dispatched(val message: String) : DispatchResult
    data class TargetUnavailable(val message: String) : DispatchResult
    data class Blocked(val message: String) : DispatchResult
    data class NeedsAccessibility(val message: String) : DispatchResult
}

class FrontDoorLauncher(private val activity: Activity) {
    fun dispatch(proposal: ActionProposal): DispatchResult = when (proposal.action) {
        ShellAction.OPEN_ALIPAY -> openPackage(ALIPAY_PACKAGE, "支付宝")
        ShellAction.OPEN_MOBILEANJIAN -> openVerifiedMobileAnjianCandidate()
        ShellAction.OPEN_SYSTEM_SETTINGS -> startExplicitSystemSettings()
        ShellAction.OPEN_AUTOMATION_LAB -> openAutomationLab()
        ShellAction.CREATE_DAILY_NOTE -> openDailyNote(proposal)
    }

    private fun openDailyNote(proposal: ActionProposal): DispatchResult {
        val arguments = proposal.arguments as? ActionArguments.DailyNote
            ?: return DispatchResult.Blocked("日常待办参数不完整，鸡蛋没有执行。")
        val spec = OwnedTargetRegistry.daily
        val launchIntent = Intent().apply {
            component = ComponentName(spec.packageName, spec.activityClassName)
            setPackage(spec.packageName)
        }
        if (launchIntent.resolveActivity(activity.packageManager) == null) {
            return DispatchResult.TargetUnavailable(
                "没有找到与鸡蛋匹配的日常小事 App，待办没有保存。",
            )
        }
        val trust = AccessibilityExecutionPolicy.decide(activity, spec.packageName)
        if (trust.lane != ExecutionLane.OWNED_APP) {
            return DispatchResult.Blocked("日常小事 App 身份检查没有通过：${trust.reason}")
        }
        val targetIdentity = trust.identity
            ?: return DispatchResult.Blocked("日常小事 App 没有提供完整身份，待办没有保存。")
        if (!AccessibilityServiceBridge.connected) {
            return DispatchResult.NeedsAccessibility("鸡蛋辅助操作尚未开启，待办还没有保存。")
        }
        if (LabSessionRegistry.activeSession() != null) {
            return DispatchResult.Blocked("另一条动作链仍在运行；鸡蛋没有叠加第二次保存。")
        }
        val session = runCatching {
            LabSessionRegistry.armDaily(
                targetIdentity = targetIdentity,
                requestId = arguments.requestId,
                noteText = arguments.text,
            )
        }.getOrElse {
            return DispatchResult.Blocked("日常会话没有成功建立，待办没有保存。")
        }
        AccessibilityServiceBridge.armFirstFrameWatchdog(session.id)
        launchIntent.putExtra(EXTRA_SESSION_NONCE, session.launchNonce)
        launchIntent.putExtra(EXTRA_DAILY_REQUEST_ID, arguments.requestId)
        return try {
            activity.startActivity(launchIntent)
            DispatchResult.Dispatched("已把日常小事 App 交给内置手；保存结果还要等页面核验。")
        } catch (_: ActivityNotFoundException) {
            AccessibilityServiceBridge.cancelWatchdog(session.id)
            LabSessionRegistry.clear(session.id)
            DispatchResult.TargetUnavailable("日常小事 App 没有打开，待办没有保存。")
        } catch (_: SecurityException) {
            AccessibilityServiceBridge.cancelWatchdog(session.id)
            LabSessionRegistry.clear(session.id)
            DispatchResult.Blocked("日常小事 App 拒绝调用，待办没有保存。")
        }
    }

    private fun openAutomationLab(): DispatchResult {
        val targetPackage = ExecutionLaneResolver.SANDBOX_PACKAGE
        val targetClass = "$targetPackage.MainActivity"
        val launchIntent = Intent().apply {
            component = ComponentName(targetPackage, targetClass)
            setPackage(targetPackage)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (launchIntent.resolveActivity(activity.packageManager) == null) {
            return DispatchResult.TargetUnavailable(
                "没有找到匹配的隔离实验页。请安装与 Shell 签名、版本和实验契约匹配的实验 APK。",
            )
        }
        val trust = AccessibilityExecutionPolicy.decide(activity, targetPackage)
        if (trust.lane != ExecutionLane.SANDBOX) {
            return DispatchResult.Blocked("实验页身份检查没有通过：${trust.reason}")
        }
        val targetIdentity = trust.identity
            ?: return DispatchResult.Blocked("实验页没有提供完整的身份指纹。")
        if (!AccessibilityServiceBridge.connected) {
            return DispatchResult.NeedsAccessibility(
                "安卓的“鸡蛋辅助操作”尚未开启，所以这只手还不能工作。",
            )
        }
        if (LabSessionRegistry.activeSession() != null) {
            return DispatchResult.Blocked("上一轮手脑实验仍在运行；鸡蛋不会叠加第二条动作链。")
        }
        val session = runCatching { LabSessionRegistry.arm(targetIdentity) }.getOrElse {
            return DispatchResult.Blocked("实验会话没有成功建立，鸡蛋没有执行页面动作。")
        }
        AccessibilityServiceBridge.armFirstFrameWatchdog(session.id)
        launchIntent.putExtra(EXTRA_SESSION_NONCE, session.launchNonce)
        return try {
            activity.startActivity(launchIntent)
            DispatchResult.Dispatched(
                "已启动隔离实验 ${session.id.take(8)}。鸡蛋会每次只做一步，并核对页面变化。",
            )
        } catch (_: ActivityNotFoundException) {
            AccessibilityServiceBridge.cancelWatchdog(session.id)
            LabSessionRegistry.clear(session.id)
            DispatchResult.TargetUnavailable("实验页没有打开，鸡蛋没有执行任何界面动作。")
        } catch (_: SecurityException) {
            AccessibilityServiceBridge.cancelWatchdog(session.id)
            LabSessionRegistry.clear(session.id)
            DispatchResult.Blocked("实验页拒绝了调用；同签名保护可能没有生效。")
        }
    }

    fun cancelActiveLab() {
        LabSessionRegistry.clearActive()
    }

    @Suppress("DEPRECATION")
    private fun openVerifiedMobileAnjianCandidate(): DispatchResult {
        val packageInfo = try {
            activity.packageManager.getPackageInfo(
                MOBILEANJIAN_PACKAGE,
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    PackageManager.GET_SIGNING_CERTIFICATES
                } else {
                    PackageManager.GET_SIGNATURES
                },
            )
        } catch (_: PackageManager.NameNotFoundException) {
            return DispatchResult.TargetUnavailable(
                "这台手机没有安装已审计的按键精灵候选版本。鸡蛋没有调用任何自动化能力。",
            )
        }
        val versionCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.longVersionCode
        } else {
            packageInfo.versionCode.toLong()
        }
        val signers = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.signingInfo?.apkContentsSigners.orEmpty()
        } else {
            packageInfo.signatures.orEmpty()
        }
        val signerDigests = signers.map { signature ->
            MessageDigest.getInstance("SHA-256")
                .digest(signature.toByteArray())
                .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
        }
        if (
            versionCode != MOBILEANJIAN_VERSION_CODE ||
            MOBILEANJIAN_CERT_SHA256 !in signerDigests
        ) {
            return DispatchResult.Blocked(
                "按键精灵的版本或签名与已审计样本不一致。鸡蛋没有打开，也没有尝试自动化。",
            )
        }
        return when (val result = openPackage(MOBILEANJIAN_PACKAGE, "按键精灵")) {
            is DispatchResult.Dispatched -> DispatchResult.Dispatched(
                "只打开了按键精灵首页；鸡蛋没有调用它的私有服务、端口、脚本或支付桥。",
            )
            else -> result
        }
    }

    private fun openPackage(packageName: String, label: String): DispatchResult {
        val packageManager = activity.packageManager
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            ?: return DispatchResult.TargetUnavailable(
                "这台手机没有可打开的${label}，所以我没有做任何事。",
            )
        val resolved = launchIntent.resolveActivity(packageManager)
            ?: return DispatchResult.TargetUnavailable(
                "安卓找不到${label}的可打开入口，所以我没有做任何事。",
            )
        if (resolved.packageName != packageName) {
            return DispatchResult.Blocked(
                "安卓返回了意外的应用入口。鸡蛋已经停下，什么也没付款。",
            )
        }

        val explicitIntent = Intent(launchIntent).apply {
            component = ComponentName(resolved.packageName, resolved.className)
            setPackage(packageName)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return try {
            activity.startActivity(explicitIntent)
            DispatchResult.Dispatched(
                "安卓已经接收打开${label}的请求。后面的操作要你自己完成；鸡蛋不知道你是否付款。",
            )
        } catch (_: ActivityNotFoundException) {
            DispatchResult.TargetUnavailable(
                "${label}没有打开，什么也没付款。鸡蛋不会自动重试。",
            )
        } catch (_: SecurityException) {
            DispatchResult.Blocked(
                "安卓阻止了这次打开请求。鸡蛋没有重试，什么也没付款。",
            )
        }
    }

    private fun startExplicitSystemSettings(): DispatchResult = try {
        activity.startActivity(Intent(Settings.ACTION_SETTINGS))
        DispatchResult.Dispatched(
            "安卓已经接收打开系统设置的请求。鸡蛋没有修改任何开关。",
        )
    } catch (_: ActivityNotFoundException) {
        DispatchResult.TargetUnavailable(
            "这台手机没有提供系统设置入口，所以我没有做任何事。",
        )
    } catch (_: SecurityException) {
        DispatchResult.Blocked(
            "安卓阻止了这次请求。鸡蛋没有修改任何设置。",
        )
    }

    companion object {
        const val ALIPAY_PACKAGE = "com.eg.android.AlipayGphone"
        const val MOBILEANJIAN_PACKAGE = "com.cyjh.mobileanjian"
        const val MOBILEANJIAN_VERSION_CODE = 2026000224L
        const val MOBILEANJIAN_CERT_SHA256 =
            "800614aaf2494f4dc1c4d43fff92ee42771d01fc09435d0b8d4b8e54dbd91413"
        private const val EXTRA_SESSION_NONCE =
            "dev.jidan.extra.ACCESSIBILITY_LAB_SESSION_NONCE"
        private const val EXTRA_DAILY_REQUEST_ID = "dev.jidan.extra.DAILY_REQUEST_ID"
    }
}
