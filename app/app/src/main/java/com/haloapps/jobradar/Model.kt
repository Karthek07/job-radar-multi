package com.haloapps.jobradar

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.time.Duration
import java.time.OffsetDateTime

@Serializable
data class Job(
    val id: String,
    val title: String = "",
    val company: String = "",
    val location: String = "",
    val country: String = "",
    val remote: Boolean = false,
    val url: String = "",
    @SerialName("apply_url") val applyUrl: String = "",
    val source: String = "",
    @SerialName("also_on") val alsoOn: List<String> = emptyList(),
    val posted: String = "",
    @SerialName("first_seen") val firstSeen: String = "",
    val score: Int = 0,
    val reasons: List<String> = emptyList(),
    val matched: List<String> = emptyList(),
    val salary: String = "",
    val description: String = "",
    @SerialName("resume_pdf") val resumePdf: String? = null,
    @SerialName("resume_docx") val resumeDocx: String? = null,
    val headline: String? = null,
    val summary: String? = null,
    @SerialName("cover_letter") val coverLetter: String? = null,
    @SerialName("keywords_missing") val keywordsMissing: List<String> = emptyList(),
    @SerialName("keywords_matched") val keywordsMatched: List<String> = emptyList(),
    @SerialName("tailor_method") val tailorMethod: String? = null,
    @SerialName("fit_notes") val fitNotes: String? = null,
    val manual: Boolean = false,
    @SerialName("profile_hash") val profileHash: String? = null,
    val prep: String? = null,
    // written by the cross-profile pass (engine/profiles.py)
    @SerialName("company_key") val companyKey: String = "",
    @SerialName("company_owner") val companyOwner: String = "",
    @SerialName("also_in") val alsoIn: List<String> = emptyList(),
) {
    val link: String get() = applyUrl.ifBlank { url }
    val tailored: Boolean get() = resumePdf != null
    val inCanada: Boolean get() = country == "CA"

    /** "3h", "2d" since posted (or first seen). */
    fun age(): String {
        val t = parse(posted) ?: parse(firstSeen) ?: return ""
        val d = Duration.between(t, OffsetDateTime.now())
        return when {
            d.toHours() < 1 -> "now"
            d.toHours() < 24 -> "${d.toHours()}h"
            else -> "${d.toDays()}d"
        }
    }

    fun ageHours(): Long = parse(posted)?.let { Duration.between(it, OffsetDateTime.now()).toHours() } ?: Long.MAX_VALUE

    private fun parse(s: String): OffsetDateTime? = try {
        if (s.isBlank()) null else OffsetDateTime.parse(s)
    } catch (e: Exception) {
        null
    }
}

@Serializable
data class JobsFile(
    val updated: String = "",
    val count: Int = 0,
    @SerialName("new_this_run") val newThisRun: Int = 0,
    val jobs: List<Job> = emptyList(),
)

object Status {
    const val SAVED = "saved"
    const val APPLIED = "applied"
    const val INTERVIEW = "interview"
    const val OFFER = "offer"
    const val REJECTED = "rejected"
    const val HIDDEN = "hidden"

    /** Statuses that count as "in the pipeline" (shown on the Applied tab). */
    val PIPELINE = listOf(APPLIED, INTERVIEW, OFFER, REJECTED)

    fun label(s: String?) = when (s) {
        SAVED -> "Saved"; APPLIED -> "Applied"; INTERVIEW -> "Interview"; OFFER -> "Offer"
        REJECTED -> "Rejected"; HIDDEN -> "Not interested"; else -> "New"
    }
}

@Serializable
data class StatusEntry(
    val status: String,
    val at: Long = System.currentTimeMillis(),
    val note: String = "",
    val history: List<String> = emptyList(),
    // kept on the status too, so the application history survives the job dropping off the list
    val title: String = "",
    val company: String = "",
)

@Serializable
data class UserState(val statuses: Map<String, StatusEntry> = emptyMap())

// ---------------------------------------------------------------------------- profiles + application history

@Serializable
data class Profile(val id: String, val name: String = "")

@Serializable
data class ProfilesFile(
    val profiles: List<Profile> = listOf(Profile("main", "Main")),
    @SerialName("exclusive_companies") val exclusiveCompanies: Boolean = false,
) {
    /** Same cleanup as engine/profiles.py: safe unique ids, "main" always present and first. */
    fun clean(): ProfilesFile {
        val seen = mutableSetOf<String>()
        val out = profiles.mapNotNull { p ->
            val id = p.id.trim().lowercase()
            if (!Regex("^[a-z0-9][a-z0-9-]{0,39}$").matches(id) || !seen.add(id)) null
            else Profile(id, p.name.trim().take(40).ifBlank { id })
        }.toMutableList()
        if ("main" !in seen) out.add(0, Profile("main", "Main"))
        return copy(profiles = out.sortedBy { it.id != "main" })
    }

    fun name(id: String?): String = profiles.firstOrNull { it.id == id }?.name ?: (id ?: "")
}

fun rootOf(id: String) = if (id == "main") "" else "profiles/$id"

@Serializable
data class JobApplication(
    val id: String = "",
    val company: String = "",
    @SerialName("company_key") val companyKey: String = "",
    val title: String = "",
    val profile: String = "",
    val date: String = "",
    val status: String = Status.APPLIED,
    @SerialName("job_id") val jobId: String = "",
    val source: String = "",
)

@Serializable
data class ApplicationsFile(val applications: List<JobApplication> = emptyList())

@Serializable
data class AppliedIndex(val companies: Map<String, List<JobApplication>> = emptyMap())

/** One application, from the app log ([fromLog]) or found by the engine in a profile's tracker. */
data class Applied(val key: String, val a: JobApplication, val fromLog: Boolean)

/** Company names compared the same way as engine/profiles.py and web/profiles.js. */
object Company {
    private val LEGAL = Regex("\\b(inc|ltd|llc|ulc|corp|corporation|co|company|limited|lp|gmbh|plc|canada|usa|us|com|ca)\\b")
    private val GENERIC = Regex("\\b(the|technologies|technology|tech|labs|group|holdings|solutions|software|systems|services|international|global|digital|hq|io)\\b")
    private val NON = Regex("[^a-z0-9]+")
    private val WS = Regex("\\s+")

    fun norm(s: String?) = (s ?: "").lowercase().replace(NON, " ").trim()

    fun key(name: String?): String {
        val n = norm(name)
        if ("amazon" in n.split(" ")) return "amazon"
        val l = n.replace(LEGAL, " ").replace(WS, " ").trim().ifBlank { n }
        return l.replace(GENERIC, " ").replace(WS, " ").trim().ifBlank { l }
    }

    /** Equal, or one name's words start the other's ("faire" / "faire wholesale"); the shorter needs 4+ letters. */
    fun same(a: String?, b: String?): Boolean {
        if (a.isNullOrBlank() || b.isNullOrBlank()) return false
        if (a == b) return true
        val (s, l) = if (a.length <= b.length) a to b else b to a
        return s.length >= 4 && "$l ".startsWith("$s ")
    }

    /** Everything you applied to, newest first, one entry per application. */
    fun merge(log: List<JobApplication>, index: AppliedIndex?): List<Applied> {
        val seen = mutableSetOf<String>()
        val out = mutableListOf<Applied>()
        fun add(a: JobApplication, fromLog: Boolean) {
            val k = key(a.company).ifBlank { a.companyKey }
            val t = norm(a.title)
            if (k.isBlank() || t.isBlank()) return
            val sig = "${a.profile}|${a.jobId}|$k|$t"
            val loose = "${a.profile}|$k|$t"
            if (sig in seen || loose in seen) return
            seen += sig; seen += loose
            out += Applied(k, a.copy(date = a.date.take(10)), fromLog)
        }
        log.forEach { add(it, true) }
        index?.companies?.values?.forEach { list -> list.forEach { add(it, false) } }
        return out.sortedByDescending { it.a.date }
    }
}
