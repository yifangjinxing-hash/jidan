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
    const val SANDBOX_CONTRACT_ID = "jidan.accessibility.sandbox.v0.1.semantic-form.5"
    const val SANDBOX_CONTRACT_METADATA = "dev.jidan.ACCESSIBILITY_LAB_CONTRACT"
    private const val SANDBOX_VERSION_CODE = 1L

    @Suppress("DEPRECATION")
    fun decide(context: Context, targetPackage: String): TargetTrustDecision {
        if (targetPackage != ExecutionLaneResolver.SANDBOX_PACKAGE) {
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
        val contractId = application?.metaData?.getString(SANDBOX_CONTRACT_METADATA).orEmpty()
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
                versionCode == SANDBOX_VERSION_CODE &&
                contractId == SANDBOX_CONTRACT_ID &&
                identity != null
        return TargetTrustDecision(
            lane = ExecutionLaneResolver.resolve(targetPackage, trusted),
            reason = when {
                application == null || packageInfo == null -> "sandbox package identity is unavailable"
                !signaturesMatch -> "sandbox signature mismatch"
                !debuggable -> "sandbox is not an explicit debug fixture"
                hasInternet -> "sandbox unexpectedly has network permission"
                versionCode != SANDBOX_VERSION_CODE -> "sandbox version mismatch"
                contractId != SANDBOX_CONTRACT_ID -> "sandbox semantic contract mismatch"
                identity == null -> "sandbox signing identity is unavailable"
                else -> "same signer, pinned version and semantic contract, debuggable, no-network fixture"
            },
            identity = identity.takeIf { trusted },
        )
    }

    private fun ByteArray.toHex(): String = joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }
}
