package dev.jidan.reference.appfunctions

import androidx.appfunctions.AppFunction
import androidx.appfunctions.AppFunctionService
import androidx.appfunctions.AppFunctionServiceEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@AppFunctionServiceEntryPoint(
    serviceName = "MemoAppFunctionService",
    appFunctionXmlFileName = "jidan_memo_app_functions",
)
abstract class BaseMemoAppFunctionService : AppFunctionService() {
    /**
     * Idempotently creates or updates the controlled test memo.
     *
     * A new [operationId] performs exactly one physical mutation. Repeating the same
     * [operationId], [memoId], and [content] must not mutate data again and returns a replay status.
     * Reusing an operation ID with a different payload is rejected.
     *
     * @param operationId Stable idempotency key for one intended mutation.
     * @param memoId Stable identifier of the memo being created or modified.
     * @param content Exact content to persist and later verify with [getMemoState].
     * @return JSON containing status, persisted state, revision, and mutation counters.
     */
    @AppFunction(isDescribedByKDoc = true)
    suspend fun putMemo(operationId: String, memoId: String, content: String): String =
        withContext(Dispatchers.IO) {
            MemoStore(applicationContext).putMemo(operationId, memoId, content)
        }

    /**
     * Reads the exact persisted memo and global idempotency counters without modifying them.
     *
     * @param memoId Stable memo identifier used by [putMemo].
     * @return JSON containing content, revision, last operation ID, and mutation counters.
     */
    @AppFunction(isDescribedByKDoc = true)
    suspend fun getMemoState(memoId: String): String =
        withContext(Dispatchers.IO) {
            MemoStore(applicationContext).getMemoState(memoId)
        }

    /** Returns global physical-mutation, provider-invocation, and memo counters as JSON. */
    @AppFunction(isDescribedByKDoc = true)
    suspend fun getStoreStats(): String =
        withContext(Dispatchers.IO) {
            MemoStore(applicationContext).getStoreStats()
        }
}
