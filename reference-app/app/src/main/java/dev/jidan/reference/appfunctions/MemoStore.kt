package dev.jidan.reference.appfunctions

import android.content.Context
import androidx.appfunctions.AppFunctionInvalidArgumentException
import java.security.MessageDigest
import org.json.JSONObject

internal class MemoStore(context: Context) {
    private val preferences =
        context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun putMemo(operationId: String, memoId: String, content: String): String = synchronized(lock) {
        validateIdentifier("operationId", operationId)
        validateIdentifier("memoId", memoId)
        val contentCodePoints = content.codePointCount(0, content.length)
        if (content.isEmpty() || contentCodePoints > MAX_CONTENT_LENGTH || content.indexOf('\u0000') >= 0) {
            throw AppFunctionInvalidArgumentException(
                "content must contain 1..$MAX_CONTENT_LENGTH Unicode code points and no NUL",
            )
        }

        val operationPrefix = "operation.${sha256(operationId)}"
        val memoPrefix = "memo.${sha256(memoId)}"
        val payloadDigest = sha256("$operationId\u0000$memoId\u0000$content")
        val previousPayloadDigest = preferences.getString("$operationPrefix.payloadDigest", null)
        val invocationCount = preferences.getLong(KEY_PUT_INVOCATIONS, 0L) + 1L

        if (previousPayloadDigest != null) {
            if (!preferences.edit().putLong(KEY_PUT_INVOCATIONS, invocationCount).commit()) {
                throw IllegalStateException("failed to persist invocation counter")
            }
            if (previousPayloadDigest != payloadDigest) {
                throw AppFunctionInvalidArgumentException(
                    "operationId was already used with a different memoId or content",
                )
            }
            val storedOperationId = preferences.getString("$operationPrefix.operationId", null)
            val storedMemoId = preferences.getString("$operationPrefix.memoId", null)
            val storedContent = preferences.getString("$operationPrefix.content", null)
            val storedRevision = preferences.getLong("$operationPrefix.revision", 0L)
            if (
                storedOperationId != operationId ||
                    storedMemoId != memoId ||
                    storedContent == null ||
                    storedRevision <= 0L
            ) {
                throw IllegalStateException("idempotency ledger is inconsistent")
            }
            return@synchronized buildState(
                status = "replayed",
                operationId = operationId,
                memoId = memoId,
                content = storedContent,
                revision = storedRevision,
            ).toString()
        }

        val previousMemoId = preferences.getString("$memoPrefix.memoId", null)
        if (previousMemoId != null && previousMemoId != memoId) {
            throw IllegalStateException("memo hash collision")
        }
        val revision = preferences.getLong("$memoPrefix.revision", 0L) + 1L
        val physicalMutationCount = preferences.getLong(KEY_PHYSICAL_MUTATIONS, 0L) + 1L
        val memoCount =
            preferences.getLong(KEY_MEMO_COUNT, 0L) + if (previousMemoId == null) 1L else 0L

        val committed =
            preferences.edit()
                .putLong(KEY_PUT_INVOCATIONS, invocationCount)
                .putLong(KEY_PHYSICAL_MUTATIONS, physicalMutationCount)
                .putLong(KEY_MEMO_COUNT, memoCount)
                .putString("$operationPrefix.operationId", operationId)
                .putString("$operationPrefix.payloadDigest", payloadDigest)
                .putString("$operationPrefix.memoId", memoId)
                .putString("$operationPrefix.content", content)
                .putLong("$operationPrefix.revision", revision)
                .putString("$memoPrefix.memoId", memoId)
                .putString("$memoPrefix.content", content)
                .putLong("$memoPrefix.revision", revision)
                .putString("$memoPrefix.lastOperationId", operationId)
                .commit()
        if (!committed) {
            throw IllegalStateException("failed to commit memo mutation")
        }

        buildState(
            status = "applied",
            operationId = operationId,
            memoId = memoId,
            content = content,
            revision = revision,
        ).toString()
    }

    fun getMemoState(memoId: String): String = synchronized(lock) {
        validateIdentifier("memoId", memoId)
        val memoPrefix = "memo.${sha256(memoId)}"
        val storedMemoId = preferences.getString("$memoPrefix.memoId", null)
        if (storedMemoId != null && storedMemoId != memoId) {
            throw IllegalStateException("memo hash collision")
        }
        buildState(
            status = if (storedMemoId == null) "missing" else "present",
            operationId = preferences.getString("$memoPrefix.lastOperationId", "") ?: "",
            memoId = memoId,
            content = preferences.getString("$memoPrefix.content", "") ?: "",
            revision = preferences.getLong("$memoPrefix.revision", 0L),
        ).toString()
    }

    fun getStoreStats(): String = synchronized(lock) {
        JSONObject()
            .put("physicalMutationCount", preferences.getLong(KEY_PHYSICAL_MUTATIONS, 0L))
            .put("putInvocationCount", preferences.getLong(KEY_PUT_INVOCATIONS, 0L))
            .put("memoCount", preferences.getLong(KEY_MEMO_COUNT, 0L))
            .toString()
    }

    private fun buildState(
        status: String,
        operationId: String,
        memoId: String,
        content: String,
        revision: Long,
    ): JSONObject =
        JSONObject()
            .put("status", status)
            .put("operationId", operationId)
            .put("memoId", memoId)
            .put("content", content)
            .put("revision", revision)
            .put("physicalMutationCount", preferences.getLong(KEY_PHYSICAL_MUTATIONS, 0L))
            .put("putInvocationCount", preferences.getLong(KEY_PUT_INVOCATIONS, 0L))
            .put("memoCount", preferences.getLong(KEY_MEMO_COUNT, 0L))

    private fun validateIdentifier(name: String, value: String) {
        if (value.length !in 1..MAX_IDENTIFIER_LENGTH || !IDENTIFIER.matches(value)) {
            throw AppFunctionInvalidArgumentException(
                "$name must match ${IDENTIFIER.pattern} and contain 1..$MAX_IDENTIFIER_LENGTH characters",
            )
        }
    }

    private fun sha256(value: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte) }

    private companion object {
        const val PREFERENCES_NAME = "jidan_reference_memos"
        const val KEY_PUT_INVOCATIONS = "counter.putInvocations"
        const val KEY_PHYSICAL_MUTATIONS = "counter.physicalMutations"
        const val KEY_MEMO_COUNT = "counter.memoCount"
        const val MAX_IDENTIFIER_LENGTH = 128
        const val MAX_CONTENT_LENGTH = 4096
        val IDENTIFIER = Regex("[A-Za-z0-9][A-Za-z0-9._-]*")
        val lock = Any()
    }
}
