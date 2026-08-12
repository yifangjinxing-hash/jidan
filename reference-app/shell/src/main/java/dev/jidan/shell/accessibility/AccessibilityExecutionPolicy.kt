package dev.jidan.shell.accessibility

import android.Manifest
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

data class TargetTrustDecision(
    val lane: ExecutionLane,
    val reason: String,
    val identity: TargetIdentity? = null,
)

object AccessibilityExecutionPolicy {
    const val SANDBOX_CONTRACT_ID = OwnedTargetRegistry.SANDBOX_CONTRACT_ID
    const val DAILY_CONTRACT_ID = OwnedTargetRegistry.DAILY_CONTRACT_ID
    const val SANDBOX_CONTRACT_METADATA = OwnedTargetRegistry.CONTRACT_METADATA

    @Suppress("DEPRECATION")
    fun decide(context: Context, targetPackage: String): TargetTrustDecision {
        val spec = OwnedTargetRegistry.find(targetPackage)
        if (spec == null) {
            return TargetTrustDecision(ExecutionLane.SHADOW, "external packages are observation-only")
        }
        val packageManager = context.packageManager
        val signaturesMatch = packageManager.checkSignatures(
            context.packageName,
            targetPackage,
        ) == PackageManager.SIGNATURE_MATCH
        val application = runCatching {
            packageManager.getApplicationInfo(targetPackage, PackageManager.GET_META_DATA)
        }.getOrNull()
        val packageInfo = runCatching {
            val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                PackageManager.GET_SIGNING_CERTIFICATES
            } else {
                PackageManager.GET_SIGNATURES
            }
            packageManager.getPackageInfo(targetPackage, flags)
        }.getOrNull()
        val versionCode = packageInfo?.let {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) it.longVersionCode else it.versionCode.toLong()
        }
        val signingCertificateSha256 = packageInfo?.let { info ->
            val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.signingInfo?.apkContentsSigners
            } else {
                info.signatures
            }
            signatures
                ?.map { signature ->
                    MessageDigest.getInstance("SHA-256")
                        .digest(signature.toByteArray())
                        .toHex()
                }
                ?.sorted()
                ?.joinToString(":")
        }.orEmpty()
        val debuggable = application?.flags?.and(ApplicationInfo.FLAG_DEBUGGABLE) != 0
        val hasInternet = packageManager.checkPermission(
            Manifest.permission.INTERNET,
            targetPackage,
        ) == PackageManager.PERMISSION_GRANTED
        val contractId = application?.metaData?.getString(OwnedTargetRegistry.CONTRACT_METADATA).orEmpty()
        val identity = if (
            application != null &&
            versionCode != null &&
            signingCertificateSha256.isNotBlank()
        ) {
            TargetIdentity(
                packageName = targetPackage,
                versionCode = versionCode,
                uid = application.uid,
                signingCertificateSha256 = signingCertificateSha256,
                contractId = contractId,
            )
        } else {
            null
        }
        val trusted =
            signaturesMatch &&
                debuggable &&
                !hasInternet &&
                versionCode == spec.versionCode &&
                contractId == spec.contractId &&
                identity != null
        return TargetTrustDecision(
            lane = ExecutionLaneResolver.resolveOwnedTarget(targetPackage, trusted),
            reason = when {
                application == null || packageInfo == null -> "owned target identity is unavailable"
                !signaturesMatch -> "owned target signature mismatch"
                !debuggable -> "owned target is not an explicit debug fixture"
                hasInternet -> "owned target unexpectedly has network permission"
                versionCode != spec.versionCode -> "owned target version mismatch"
                contractId != spec.contractId -> "owned target semantic contract mismatch"
                identity == null -> "owned target signing identity is unavailable"
                else -> "same signer, pinned version and semantic contract, debuggable, no-network fixture"
            },
            identity = identity.takeIf { trusted },
        )
    }

    private fun ByteArray.toHex(): String = joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }
}
