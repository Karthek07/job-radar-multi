package com.haloapps.jobradar

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private fun month(d: String): String = try {
    LocalDate.parse(d.take(10)).format(DateTimeFormatter.ofPattern("MMM yyyy", Locale.getDefault()))
} catch (e: Exception) {
    ""
}

/** On the job page: earlier applications at this company, and which profile the company belongs to. */
@Composable
fun AppliedBeforeSection(vm: MainVM, job: Job) {
    val list = vm.appliedFor(job)
    val owner = vm.ownerOf(job)
    val elsewhere = owner != vm.profile
    if (list.isEmpty() && !elsewhere && job.alsoIn.isEmpty()) return
    Card(
        Modifier.fillMaxWidth().padding(top = 16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                if (list.isNotEmpty()) "You've applied to ${job.company} before" else "${job.company} in your other profiles",
                style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onTertiaryContainer,
            )
            list.forEach { e ->
                Text(e.a.title, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onTertiaryContainer)
                Text(
                    listOf(if (e.a.profile.isBlank()) "" else "${vm.profiles.name(e.a.profile)} profile", month(e.a.date), Status.label(e.a.status))
                        .filter { it.isNotBlank() }.joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
            }
            val note = when {
                elsewhere && vm.exclusive -> "${job.company} belongs to your ${vm.profiles.name(owner)} profile, so this job is hidden from this profile's list while No overlap is on."
                elsewhere -> "${job.company} belongs to your ${vm.profiles.name(owner)} profile. Turn on No overlap in Profiles to keep each company in one profile."
                job.alsoIn.isNotEmpty() -> "Also found in: ${job.alsoIn.joinToString { vm.profiles.name(it) }}."
                else -> ""
            }
            if (note.isNotBlank()) Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onTertiaryContainer,
                modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun Header(title: String, onBack: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(4.dp)) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
    }
    HorizontalDivider()
}

@Composable
fun ProfilesScreen(vm: MainVM, modifier: Modifier, onBack: () -> Unit, onEditSearch: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var copyFrom by remember { mutableStateOf<String?>(null) }
    var renaming by remember { mutableStateOf<Profile?>(null) }
    var removing by remember { mutableStateOf<Profile?>(null) }

    Column(modifier.fillMaxSize()) {
        Header("Profiles", onBack)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Hint("Each profile is its own job search: its own resume, job titles, tracker and tailored resumes. All profiles search on the same schedule.")

            Group("No company overlap") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Keep every company in one profile", Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    Switch(vm.profiles.exclusiveCompanies, { vm.setExclusive(it) }, enabled = !vm.saving)
                }
                Hint("A company with matching jobs in several profiles stays in one: where you applied most recently, else where you saved one of its jobs, else where it matches best. Hidden jobs are counted at the top of the list.")
            }

            Group("Your profiles") {
                vm.profiles.profiles.forEach { p ->
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(p.name + if (p.id == vm.profile) "  ✓" else "", fontWeight = FontWeight.SemiBold)
                            Text(if (p.id == "main") "repo root" else "profiles/${p.id}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (p.id != vm.profile) TextButton(onClick = { vm.switchProfile(p.id); onBack() }) { Text("Open") }
                        TextButton(onClick = { renaming = p }) { Text("Rename") }
                        if (p.id != "main") TextButton(onClick = { removing = p }) { Text("Remove") }
                    }
                    HorizontalDivider()
                }
            }

            Group("Add a profile") {
                Field("Name (e.g. Product Manager)", name, { name = it })
                Text("Start from", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                    FilterChip(copyFrom == null, { copyFrom = null }, { Text("New resume") })
                }
                vm.profiles.profiles.forEach { p ->
                    FilterChip(copyFrom == p.id, { copyFrom = p.id }, { Text("Same resume as ${p.name}") })
                }
                Hint(if (copyFrom == null) "Upload the resume for it from the web app (Profile tab) once it's created."
                else "Next, set the job titles this profile looks for in Search preferences.")
                Button(onClick = {
                    val from = copyFrom
                    vm.addProfile(name, from)
                    name = ""
                    if (from != null) onEditSearch()
                }, enabled = name.isNotBlank() && !vm.saving, modifier = Modifier.fillMaxWidth()) { Text("Add profile") }
            }
            Spacer(Modifier.height(32.dp))
        }
    }

    renaming?.let { p ->
        var n by remember(p.id) { mutableStateOf(p.name) }
        AlertDialog(
            onDismissRequest = { renaming = null },
            title = { Text("Rename profile") },
            text = { OutlinedTextField(n, { n = it }, singleLine = true) },
            confirmButton = { TextButton(onClick = { vm.renameProfile(p.id, n); renaming = null }) { Text("Save") } },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text("Cancel") } },
        )
    }
    removing?.let { p ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text("Remove ${p.name}?") },
            text = { Text("It stops searching. Its files stay in your repo under profiles/${p.id}, so adding a profile with the same name brings it back.") },
            confirmButton = { TextButton(onClick = { vm.removeProfile(p.id); removing = null }) { Text("Remove") } },
            dismissButton = { TextButton(onClick = { removing = null }) { Text("Cancel") } },
        )
    }
}

@Composable
fun HistoryScreen(vm: MainVM, modifier: Modifier, onBack: () -> Unit) {
    var company by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now().toString()) }
    var forProfile by remember { mutableStateOf(vm.profile) }
    var q by remember { mutableStateOf("") }
    val all = vm.applied
    val shown = all.filter { q.isBlank() || "${it.a.company} ${it.a.title}".contains(q.trim(), ignoreCase = true) }

    Column(modifier.fillMaxSize()) {
        Header("Application history", onBack)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Hint("Every application from every profile. Jobs you mark Applied are added automatically. Add the ones you sent before Job Radar so every job at those companies shows \"Applied before\".")
            Group("Add one") {
                Field("Company", company, { company = it })
                Field("Job title", title, { title = it })
                Field("Date applied (YYYY-MM-DD)", date, { date = it })
                Text("Profile", style = MaterialTheme.typography.bodyMedium)
                vm.profiles.profiles.forEach { p -> FilterChip(forProfile == p.id, { forProfile = p.id }, { Text(p.name) }) }
                FilterChip(forProfile == "", { forProfile = "" }, { Text("None / outside Job Radar") })
                Button(onClick = {
                    vm.addApplication(company, title, date.trim().take(10), forProfile)
                    company = ""; title = ""
                }, enabled = company.isNotBlank() && title.isNotBlank(), modifier = Modifier.fillMaxWidth()) { Text("Add") }
            }
            Group("${all.size} applications") {
                OutlinedTextField(q, { q = it }, placeholder = { Text("Search company or title") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                shown.forEach { e ->
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(e.a.company.ifBlank { e.key }, fontWeight = FontWeight.Bold)
                            Text(e.a.title)
                            Text(
                                listOf(if (e.a.profile.isBlank()) "outside Job Radar" else vm.profiles.name(e.a.profile), month(e.a.date), Status.label(e.a.status))
                                    .filter { it.isNotBlank() }.joinToString(" · "),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        if (e.fromLog) OutlinedButton(onClick = { vm.deleteApplication(e.a.id) }) { Text("Delete") }
                        else Text("tracker", style = MaterialTheme.typography.bodySmall, color = Color.Gray, modifier = Modifier.width(56.dp))
                    }
                    HorizontalDivider()
                }
            }
            Spacer(Modifier.height(32.dp))
        }
    }
}
