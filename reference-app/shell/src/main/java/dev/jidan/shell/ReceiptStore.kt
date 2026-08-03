package dev.jidan.shell

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

class ReceiptStore(context: Context) {
    private val file = File(context.filesDir, "jidan-shell-receipts.jsonl")

    @Synchronized
    fun append(proposal: ActionProposal, status: String): String {
        require(status in ALLOWED_STATUSES) { "unsupported receipt status" }
        val records = readRecords()
        check(verifyRecords(records)) { "local receipt chain is invalid" }
        val previous = records.lastOrNull()?.getString("hash") ?: GENESIS
        val timestamp = System.currentTimeMillis()
        val body = canonicalBody(
            timestamp = timestamp,
            actionId = proposal.action.id,
            actionDigest = proposal.digest,
            status = status,
            previousHash = previous,
        )
        val hash = ActionProposal.sha256(body)
        val record = JSONObject()
            .put("timestampMs", timestamp)
            .put("actionId", proposal.action.id)
            .put("actionDigest", proposal.digest)
            .put("status", status)
            .put("previousHash", previous)
            .put("paymentAttemptedByJidan", false)
            .put("paid", false)
            .put("committed", false)
            .put("verified", false)
            .put("hash", hash)
        file.parentFile?.mkdirs()
        FileOutputStream(file, true).use { stream ->
            stream.write((record.toString() + "\n").toByteArray(Charsets.UTF_8))
            stream.flush()
            stream.fd.sync()
        }
        return hash
    }

    @Synchronized
    fun verify(): Boolean = runCatching { verifyRecords(readRecords()) }.getOrDefault(false)

    private fun readRecords(): List<JSONObject> {
        if (!file.isFile) return emptyList()
        return file.readLines(Charsets.UTF_8)
            .filter { line -> line.isNotBlank() }
            .map(::JSONObject)
    }

    private fun verifyRecords(records: List<JSONObject>): Boolean {
        var previous = GENESIS
        for (record in records) {
            if (record.getString("previousHash") != previous) return false
            if (record.optBoolean("paymentAttemptedByJidan", true)) return false
            if (record.optBoolean("paid", true)) return false
            if (record.optBoolean("committed", true)) return false
            if (record.optBoolean("verified", true)) return false
            val expected = ActionProposal.sha256(
                canonicalBody(
                    timestamp = record.getLong("timestampMs"),
                    actionId = record.getString("actionId"),
                    actionDigest = record.getString("actionDigest"),
                    status = record.getString("status"),
                    previousHash = previous,
                ),
            )
            val actual = record.getString("hash")
            if (expected != actual) return false
            previous = actual
        }
        return true
    }

    private fun canonicalBody(
        timestamp: Long,
        actionId: String,
        actionDigest: String,
        status: String,
        previousHash: String,
    ): String = listOf(
        timestamp.toString(),
        actionId,
        actionDigest,
        status,
        previousHash,
    ).joinToString("\n")

    companion object {
        private const val GENESIS =
            "0000000000000000000000000000000000000000000000000000000000000000"
        private val ALLOWED_STATUSES = setOf(
            "handoff_dispatched",
            "target_unavailable",
            "blocked_by_os",
        )
    }
}
