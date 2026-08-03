package dev.jidan.shell

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.provider.Settings

sealed interface DispatchResult {
    data class Dispatched(val message: String) : DispatchResult
    data class TargetUnavailable(val message: String) : DispatchResult
    data class Blocked(val message: String) : DispatchResult
}

class FrontDoorLauncher(private val activity: Activity) {
    fun dispatch(proposal: ActionProposal): DispatchResult = when (proposal.action) {
        ShellAction.OPEN_ALIPAY -> openPackage(ALIPAY_PACKAGE, "支付宝")
        ShellAction.OPEN_SYSTEM_SETTINGS -> startExplicitSystemSettings()
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
    }
}
