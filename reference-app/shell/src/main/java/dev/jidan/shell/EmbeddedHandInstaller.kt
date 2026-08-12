package dev.jidan.shell

import android.app.Activity
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import java.io.File
import java.security.MessageDigest

sealed interface EmbeddedHandInstallResult {
    data object Started : EmbeddedHandInstallResult
    data object SourcePermissionRequested : EmbeddedHandInstallResult
    data object AssetUnavailable : EmbeddedHandInstallResult
    data object AssetInvalid : EmbeddedHandInstallResult
    data object Blocked : EmbeddedHandInstallResult
}

object EmbeddedHandInstaller {
    const val ASSET_PATH = "embedded/mobileanjian-4.2.3.apk"
    const val FILE_NAME = "mobileanjian-4.2.3.apk"
    const val EXPECTED_SIZE_BYTES = 83_933_160L
    const val EXPECTED_SHA256 =
        "2d554d35d3c20de38c2adb6b51bdea2ddcf19e4dcdc6f3c3da52244037bb803d"

    fun request(activity: Activity): EmbeddedHandInstallResult {
        when (prepare(activity)) {
            is Prepared.Valid -> Unit
            Prepared.Unavailable -> return EmbeddedHandInstallResult.AssetUnavailable
            Prepared.Invalid -> return EmbeddedHandInstallResult.AssetInvalid
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !activity.packageManager.canRequestPackageInstalls()
        ) {
            return runCatching {
                activity.startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:${activity.packageName}"),
                    ),
                )
                EmbeddedHandInstallResult.SourcePermissionRequested
            }.getOrDefault(EmbeddedHandInstallResult.Blocked)
        }

        val uri = Uri.Builder()
            .scheme("content")
            .authority("${activity.packageName}.embedded-hand")
            .appendPath(FILE_NAME)
            .build()
        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, APK_MIME)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        val systemHandler = activity.packageManager
            .queryIntentActivities(installIntent, PackageManager.MATCH_DEFAULT_ONLY)
            .firstOrNull { candidate ->
                val flags = candidate.activityInfo.applicationInfo.flags
                flags and (ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0
            }
            ?: return EmbeddedHandInstallResult.Blocked
        installIntent.setClassName(systemHandler.activityInfo.packageName, systemHandler.activityInfo.name)
        return runCatching {
            activity.startActivity(installIntent)
            EmbeddedHandInstallResult.Started
        }.getOrDefault(EmbeddedHandInstallResult.Blocked)
    }

    internal fun cachedFile(activity: android.content.Context): File =
        File(File(activity.noBackupFilesDir, "embedded-hand"), FILE_NAME)

    internal fun isCachedFileValid(activity: android.content.Context): Boolean {
        val file = cachedFile(activity)
        return file.isFile &&
            file.length() == EXPECTED_SIZE_BYTES &&
            sha256(file) == EXPECTED_SHA256
    }

    private fun prepare(activity: Activity): Prepared {
        val destination = cachedFile(activity)
        if (
            destination.isFile &&
            destination.length() == EXPECTED_SIZE_BYTES &&
            sha256(destination) == EXPECTED_SHA256
        ) {
            return Prepared.Valid(destination)
        }
        val directory = destination.parentFile ?: return Prepared.Invalid
        if (!directory.exists() && !directory.mkdirs()) return Prepared.Invalid
        val partial = File(directory, "$FILE_NAME.partial")
        val copied = runCatching {
            activity.assets.open(ASSET_PATH).use { input ->
                partial.outputStream().use { output -> input.copyTo(output) }
            }
        }.isSuccess
        if (!copied) {
            partial.delete()
            return Prepared.Unavailable
        }
        if (partial.length() != EXPECTED_SIZE_BYTES || sha256(partial) != EXPECTED_SHA256) {
            partial.delete()
            return Prepared.Invalid
        }
        if (destination.exists() && !destination.delete()) {
            partial.delete()
            return Prepared.Invalid
        }
        if (!partial.renameTo(destination)) {
            partial.delete()
            return Prepared.Invalid
        }
        return Prepared.Valid(destination)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }

    private sealed interface Prepared {
        data class Valid(val file: File) : Prepared
        data object Unavailable : Prepared
        data object Invalid : Prepared
    }

    private const val APK_MIME = "application/vnd.android.package-archive"
}
