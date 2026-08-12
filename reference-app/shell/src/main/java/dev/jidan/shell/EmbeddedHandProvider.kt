package dev.jidan.shell

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import java.io.FileNotFoundException

class EmbeddedHandProvider : ContentProvider() {
    override fun onCreate(): Boolean = true

    override fun getType(uri: Uri): String = APK_MIME

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        if (mode != "r" || uri.lastPathSegment != EmbeddedHandInstaller.FILE_NAME) {
            throw FileNotFoundException("Unknown embedded hand")
        }
        val appContext = context ?: throw FileNotFoundException("No context")
        if (!EmbeddedHandInstaller.isCachedFileValid(appContext)) {
            throw FileNotFoundException("Embedded hand failed identity check")
        }
        return ParcelFileDescriptor.open(
            EmbeddedHandInstaller.cachedFile(appContext),
            ParcelFileDescriptor.MODE_READ_ONLY,
        )
    }

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?,
    ): Cursor {
        val columns = projection ?: arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)
        val cursor = MatrixCursor(columns)
        val file = context?.let(EmbeddedHandInstaller::cachedFile)
        cursor.addRow(columns.map { column ->
            when (column) {
                OpenableColumns.DISPLAY_NAME -> EmbeddedHandInstaller.FILE_NAME
                OpenableColumns.SIZE -> file?.length() ?: 0L
                else -> null
            }
        })
        return cursor
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<out String>?,
    ): Int = 0

    companion object {
        private const val APK_MIME = "application/vnd.android.package-archive"
    }
}
