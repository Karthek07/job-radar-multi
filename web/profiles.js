// Profiles, the no-overlap switch, and "applied before".
// Files (all at the repo root, shared by every profile):
//   profiles.json               { profiles: [{id, name}], exclusive_companies }
//   applications.json           { applications: [{id, company, company_key, title, profile, date, status, job_id, source}] }
//   shared/applied_index.json   written by the engine: the same, plus everything found in each profile's tracker
import { html, useState, useMemo } from "./vendor/preact-htm.js";
import gh from "./backend.js";
import { PIPE, LABEL, clone, lines } from "./ui.js";

// ------------------------------------------------------------------ company names (same rules as engine/profiles.py)

const LEGAL = /\b(inc|ltd|llc|ulc|corp|corporation|co|company|limited|lp|gmbh|plc|canada|usa|us|com|ca)\b/g;
const GENERIC = /\b(the|technologies|technology|tech|labs|group|holdings|solutions|software|systems|services|international|global|digital|hq|io)\b/g;
const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const squash = (s) => s.replace(/\s+/g, " ").trim();

export function canonCompany(name) {
  const n = norm(name);
  if (n.split(" ").includes("amazon")) return "amazon";
  const l = squash(n.replace(LEGAL, " ")) || n;
  return squash(l.replace(GENERIC, " ")) || l;
}

/** Equal, or one name's words start the other's ("faire" / "faire wholesale"); the shorter needs 4+ letters. */
export function sameCompany(a, b) {
  if (!a || !b) return false;
  if (a === b) return true;
  const [s, l] = a.length <= b.length ? [a, b] : [b, a];
  return s.length >= 4 && (l + " ").startsWith(s + " ");
}

// ------------------------------------------------------------------ profiles.json

const ID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
export const rootOf = (id) => (id === "main" ? "" : `profiles/${id}`);

export function cleanProfiles(raw) {
  const out = [];
  const seen = new Set();
  for (const p of raw?.profiles || []) {
    const id = String(p?.id || "").trim().toLowerCase();
    if (!ID_RE.test(id) || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, name: String(p.name || id).trim().slice(0, 40) || id });
  }
  if (!seen.has("main")) out.unshift({ id: "main", name: "Main" });
  out.sort((a, b) => (a.id !== "main") - (b.id !== "main"));
  return { profiles: out, exclusive_companies: !!raw?.exclusive_companies };
}

export async function loadProfiles() {
  try { return cleanProfiles(await gh.shared.json("profiles.json")); }
  catch (e) { if (e.status === 404) return cleanProfiles(null); throw e; }
}

export async function saveProfiles(cfg, message) {
  const clean = cleanProfiles(cfg);
  await gh.shared.putText("profiles.json", JSON.stringify(clean, null, 2) + "\n", message);
  return clean;
}

export function newProfileId(name, cfg) {
  const base = norm(name).replace(/ /g, "-").slice(0, 32) || "profile";
  let id = base === "main" ? "main-2" : base;
  for (let i = 2; cfg.profiles.some((p) => p.id === id); i++) id = `${base}-${i}`;
  return id;
}

// ------------------------------------------------------------------ applications.json

export async function loadApplications() {
  try { const a = await gh.shared.json("applications.json"); return Array.isArray(a?.applications) ? a.applications : []; }
  catch (e) { if (e.status === 404) return []; throw e; }
}

/** Read the newest copy, change it, write it back: safe when the phone and the browser both edit. */
export async function mutateApplications(fn, message = "app: update application history") {
  const cur = await loadApplications();
  const next = fn(clone(cur));
  if (JSON.stringify(next) === JSON.stringify(cur)) return cur;
  await gh.shared.putText("applications.json", JSON.stringify({ applications: next }, null, 1) + "\n", message);
  return next;
}

/** The log entry for one tracked job (id is profile:job so re-applying updates it instead of duplicating). */
export function entryFor(profile, job, status, at) {
  return {
    id: `${profile}:${job.id}`, company: job.company || "", company_key: canonCompany(job.company), title: job.title || "",
    profile, date: new Date(at || Date.now()).toISOString().slice(0, 10), status, job_id: job.id, source: "app",
  };
}

export async function loadEngineIndex() {
  try { return await gh.shared.json("shared/applied_index.json"); } catch { return null; }
}

/** Everything you applied to, from the app log and the engine's index, one entry per application. */
export function mergeApplied(apps, index) {
  const out = [];
  const seen = new Set();
  const push = (e, src) => {
    const key = canonCompany(e.company) || e.company_key || "";
    const t = norm(e.title);
    if (!key || !t) return;
    const sig = `${e.profile || ""}|${e.job_id || ""}|${key}|${t}`;
    const loose = `${e.profile || ""}|${key}|${t}`;
    if (seen.has(sig) || seen.has(loose)) return;
    seen.add(sig); seen.add(loose);
    out.push({ ...e, key, date: String(e.date || "").slice(0, 10), from: src });
  };
  for (const e of apps || []) push(e, "log");
  for (const list of Object.values(index?.companies || {})) for (const e of list) push(e, "index");
  return out.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
}

/** Applications at this job's company, except this very job in this very profile. Newest first. */
export function appliedFor(job, entries, profile) {
  const k1 = canonCompany(job.company);
  const k2 = job.company_key;
  return entries.filter((e) => (sameCompany(e.key, k1) || sameCompany(e.key, k2)) && !(e.profile === profile && e.job_id === job.id));
}

/** Which profile this company belongs to: where you applied most recently (live), else what the engine decided. */
export function ownerOf(job, entries, profile, ids) {
  const k1 = canonCompany(job.company);
  const k2 = job.company_key;
  const hit = entries.find((e) => ids.has(e.profile) && (sameCompany(e.key, k1) || sameCompany(e.key, k2)));
  if (hit) return hit.profile;
  return ids.has(job.company_owner) ? job.company_owner : profile;
}

const month = (d) => { const t = Date.parse(d || ""); return t ? new Date(t).toLocaleDateString([], { month: "short", year: "numeric" }) : ""; };
const who = (names, id) => (id ? names[id] || id : "");

// ------------------------------------------------------------------ small pieces used on job rows and the detail page

export function AppliedTag({ list, names }) {
  if (!list?.length) return null;
  const first = list[0];
  const tip = list.map((e) => `${e.title}${e.profile ? ` (${who(names, e.profile)})` : ""}${e.date ? `, ${month(e.date)}` : ""}${e.status ? `, ${LABEL[e.status] || e.status}` : ""}`).join("\n");
  return html`<span class="tag applied-before" title=${tip}>Applied before: ${first.title}${list.length > 1 ? ` +${list.length - 1}` : ""}</span>`;
}

export function AppliedBlock({ job, list, names, owner, profile, exclusive }) {
  const elsewhere = owner && owner !== profile;
  if (!list.length && !elsewhere && !job.also_in?.length) return null;
  return html`<div class="block applied-block"><h3>${list.length ? `You've applied to ${job.company} before` : `${job.company} in your other profiles`}</h3>
    ${list.length ? html`<ul class="applist">${list.map((e) => html`<li>
      <b>${e.title}</b>
      <span class="hint">${[e.profile ? `${who(names, e.profile)} profile` : "", month(e.date), LABEL[e.status] || e.status].filter(Boolean).join(" · ")}</span></li>`)}</ul>
      <p class="hint">Use a different angle than last time, or mention the earlier application if it went well.</p>` : null}
    ${elsewhere ? html`<p class="hint"><b>${job.company}</b> belongs to your <b>${who(names, owner)}</b> profile${exclusive
      ? ", so this job is hidden from this profile's lists while No overlap is on." : ". Turn on No overlap in Profiles to keep each company in one profile."}</p>`
      : job.also_in?.length ? html`<p class="hint">Also found in: ${job.also_in.map((x) => who(names, x)).join(", ")}.</p>` : null}
  </div>`;
}

export function ProfileSwitcher({ cfg, current, onSwitch, onManage }) {
  if (!cfg) return null;
  return html`<label class="pswitch"><span class="sr">Profile</span>
    <select aria-label="Profile" value=${current} onChange=${(e) => (e.target.value === "__manage" ? (e.target.value = current, onManage()) : onSwitch(e.target.value))}>
      ${cfg.profiles.map((p) => html`<option value=${p.id}>${p.name}</option>`)}
      <option value="__manage">Manage profiles…</option>
    </select></label>`;
}

// ------------------------------------------------------------------ Profiles page

export function ProfilesPage({ cfg, setCfg, current, onSwitch, say }) {
  const [name, setName] = useState("");
  const [from, setFrom] = useState("upload");
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState(null);
  if (!cfg) return html`<div class="page">Loading profiles…</div>`;

  async function save(next, msg) {
    setBusy(true);
    try { const c = await saveProfiles(next, msg); setCfg(c); return c; }
    catch (e) { say(e.message); return null; }
    finally { setBusy(false); }
  }
  async function add() {
    const n = name.trim();
    if (!n) return;
    const id = newProfileId(n, cfg);
    setBusy(true);
    try {
      if (from !== "upload") {
        const src = rootOf(from);
        const p = (f) => (src ? `${src}/${f}` : f);
        const [resume, search] = await Promise.all([gh.shared.json(p("profile/resume.json")), gh.shared.json(p("profile/search.json")).catch(() => null)]);
        await gh.shared.putText(`profiles/${id}/profile/resume.json`, JSON.stringify(resume, null, 2) + "\n", `app: copy resume to ${n}`);
        if (search) {
          const s = clone(search);
          s.queries = []; s.title_terms = { ...(s.title_terms || {}), required: [], weighted: {} }; // new profile = new target roles
          await gh.shared.putText(`profiles/${id}/profile/search.json`, JSON.stringify(s, null, 2) + "\n", `app: search settings for ${n}`);
        }
      }
      const c = await saveProfiles({ ...cfg, profiles: [...cfg.profiles, { id, name: n }] }, `app: add profile ${n}`);
      setCfg(c);
      setName("");
      onSwitch(id, from === "upload" ? "onboard" : "search");
      say(from === "upload" ? `Profile "${n}" created. Upload the resume for it.` : `Profile "${n}" created with the same resume. Now set the job titles it should look for.`);
    } catch (e) { say(e.message); }
    setBusy(false);
  }

  return html`<div class="page form">
    <h2>Profiles</h2>
    <p class="hint">Each profile is its own job search: its own resume, job titles, locations, tracker and tailored resumes. Use one per kind of role you go after (for example Data Analyst and Product Manager). All profiles search on the same schedule.</p>

    <div class="card"><h3>No company overlap</h3>
      <label class="row toggle"><input type="checkbox" checked=${cfg.exclusive_companies} disabled=${busy}
        onChange=${(e) => save({ ...cfg, exclusive_companies: e.target.checked }, `app: no-overlap ${e.target.checked ? "on" : "off"}`).then((c) => c && say(c.exclusive_companies ? "On: each company now shows in one profile only." : "Off: companies can show in several profiles."))} />
        <span><b>Keep every company in one profile</b><br />
        <span class="hint">When a company has matching jobs in several profiles, it stays in one: the profile you applied from (most recent application), else the one where you saved a job there, else the one it matches best. It doesn't move around afterwards. Jobs hidden this way are counted at the top of the job list, and you can still peek at them.</span></span></label></div>

    <div class="card"><h3>Your profiles</h3>
      <ul class="plist">${cfg.profiles.map((p) => html`<li>
        ${renaming === p.id ? html`<input class="input" value=${p.name} autofocus onKeyDown=${(e) => {
          if (e.key === "Enter") save({ ...cfg, profiles: cfg.profiles.map((x) => (x.id === p.id ? { ...x, name: e.target.value.trim() || x.name } : x)) }, "app: rename profile").then(() => setRenaming(null));
          if (e.key === "Escape") setRenaming(null);
        }} />` : html`<b>${p.name}</b>`}
        ${p.id === current ? html`<span class="tag ready">Open now</span>` : null}
        <span class="hint">${p.id === "main" ? "repo root" : `profiles/${p.id}`}</span>
        <span class="spacer"></span>
        ${p.id !== current ? html`<button class="btn small" onClick=${() => onSwitch(p.id)}>Open</button>` : null}
        <button class="btn small" onClick=${() => setRenaming(renaming === p.id ? null : p.id)}>${renaming === p.id ? "Cancel" : "Rename"}</button>
        ${p.id !== "main" ? html`<button class="btn small" disabled=${busy} onClick=${() => {
          if (!confirm(`Remove the profile "${p.name}"? It stops searching. Its files stay in your repo under profiles/${p.id}, so adding a profile with the same name brings it back.`)) return;
          save({ ...cfg, profiles: cfg.profiles.filter((x) => x.id !== p.id) }, `app: remove profile ${p.name}`).then((c) => { if (c && current === p.id) onSwitch("main"); });
        }}>Remove</button>` : null}
      </li>`)}</ul>
      ${renaming ? html`<p class="hint">Press Enter to save the new name.</p>` : null}</div>

    <div class="card"><h3>Add a profile</h3>
      <div class="grid2">
        <div class="field"><label for="pn">Name</label><input id="pn" class="input" placeholder="e.g. Product Manager" value=${name} onInput=${(e) => setName(e.target.value)} /></div>
        <div class="field"><label for="pf">Start from</label>
          <select id="pf" class="input" value=${from} onChange=${(e) => setFrom(e.target.value)}>
            <option value="upload">A different resume (upload next)</option>
            ${cfg.profiles.map((p) => html`<option value=${p.id}>Same resume as ${p.name}</option>`)}
          </select></div></div>
      <div class="row"><button class="btn primary" disabled=${busy || !name.trim()} onClick=${add}>${busy ? "Working…" : "Add profile"}</button></div>
      <p class="hint">Every profile runs its own searches, so each one adds a few minutes to each run and uses its own share of the free job-source keys.</p></div>
  </div>`;
}

// ------------------------------------------------------------------ application history page

function parseRows(text) {
  // "Company, Title, 2025-03-01" or tab-separated (pasted from a spreadsheet); date optional; header rows skipped
  return lines(text).map((l) => l.split(/\t|,(?![^(]*\))/).map((x) => x.trim())).filter((c) => c[0] && c[1] && !/^company$/i.test(c[0]))
    .map(([company, title, date, status]) => {
      const t = Date.parse(date || "");
      const st = /offer/i.test(status || "") ? "offer" : /interview/i.test(status || "") ? "interview" : /reject|declin/i.test(status || "") ? "rejected" : "applied";
      return { company, title, date: t ? new Date(t).toISOString().slice(0, 10) : "", status: st };
    });
}

export function HistoryPage({ entries, cfg, current, say, onChange }) {
  const [q, setQ] = useState("");
  const [v, setV] = useState({ company: "", title: "", date: new Date().toISOString().slice(0, 10), profile: current, status: "applied" });
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const names = Object.fromEntries((cfg?.profiles || []).map((p) => [p.id, p.name]));
  const groups = useMemo(() => {
    const s = q.trim().toLowerCase();
    const list = entries.filter((e) => !s || `${e.company} ${e.title}`.toLowerCase().includes(s));
    const g = [];
    for (const e of list) {
      const hit = g.find((x) => sameCompany(x.key, e.key));
      if (hit) hit.items.push(e); else g.push({ key: e.key, company: e.company || e.key, items: [e] });
    }
    return g.sort((a, b) => (b.items[0].date || "").localeCompare(a.items[0].date || ""));
  }, [entries, q]);

  async function run(fn, msg, done) {
    setBusy(true);
    try { await mutateApplications(fn); onChange(); say(msg); done?.(); } catch (e) { say(e.message); }
    setBusy(false);
  }
  const mk = (r) => ({ id: "m" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), company: r.company.trim(), company_key: canonCompany(r.company),
    title: r.title.trim(), profile: r.profile ?? "", date: r.date || "", status: r.status || "applied", job_id: "", source: "manual" });
  const rows = parseRows(paste);

  return html`<div class="page form">
    <h2>Application history</h2>
    <p class="hint">Every application from every profile. Jobs you mark Applied are added automatically; add the ones you sent before using Job Radar so every job at those companies shows <span class="tag applied-before">Applied before</span>.</p>

    <div class="card"><h3>Add one</h3>
      <div class="grid2">
        <div class="field"><label for="hc">Company</label><input id="hc" class="input" value=${v.company} onInput=${(e) => setV({ ...v, company: e.target.value })} /></div>
        <div class="field"><label for="ht">Job title</label><input id="ht" class="input" value=${v.title} onInput=${(e) => setV({ ...v, title: e.target.value })} /></div>
        <div class="field"><label for="hd">Date applied</label><input id="hd" class="input" type="date" value=${v.date} onInput=${(e) => setV({ ...v, date: e.target.value })} /></div>
        <div class="field"><label for="hp">Profile</label><select id="hp" class="input" value=${v.profile} onChange=${(e) => setV({ ...v, profile: e.target.value })}>
          ${(cfg?.profiles || []).map((p) => html`<option value=${p.id}>${p.name}</option>`)}<option value="">None / outside Job Radar</option></select></div>
        <div class="field"><label for="hs">Status</label><select id="hs" class="input" value=${v.status} onChange=${(e) => setV({ ...v, status: e.target.value })}>
          ${PIPE.map((s) => html`<option value=${s}>${LABEL[s]}</option>`)}</select></div>
      </div>
      <div class="row"><button class="btn primary" disabled=${busy || !v.company.trim() || !v.title.trim()}
        onClick=${() => run((a) => [...a, mk(v)], `Added ${v.title} at ${v.company}.`, () => setV({ ...v, company: "", title: "" }))}>Add</button></div></div>

    <details class="card"><summary><b>Paste a list</b> <span class="hint">from a spreadsheet or notes</span></summary>
      <p class="hint">One per line: <code>Company, Job title, Date</code> (date optional). Columns copied from Excel or Google Sheets work too. They're added to the ${names[v.profile] || "selected"} profile chosen above.</p>
      <textarea class="input" rows="6" placeholder=${"Shopify, Senior Data Analyst, 2026-03-14\nWealthsimple, Product Analyst"} value=${paste} onInput=${(e) => setPaste(e.target.value)}></textarea>
      <div class="row"><button class="btn" disabled=${busy || !rows.length} onClick=${() => run((a) => [...a, ...rows.map((r) => mk({ ...r, profile: v.profile }))], `Added ${rows.length} applications.`, () => setPaste(""))}>
        Add ${rows.length || ""} ${rows.length === 1 ? "application" : "applications"}</button></div></details>

    <div class="card"><div class="row"><h3>${entries.length} applications at ${groups.length} companies</h3><span class="spacer"></span>
      <input class="input" style="max-width:240px" placeholder="Search company or title" aria-label="Search history" value=${q} onInput=${(e) => setQ(e.target.value)} /></div>
      ${groups.length ? html`<div class="history">${groups.map((g) => html`<div class="hgroup"><div class="hco">${g.company}</div>
        ${g.items.map((e) => html`<div class="hrow"><span>${e.title}</span>
          <span class="hint">${[e.profile ? names[e.profile] || e.profile : "outside Job Radar", month(e.date), LABEL[e.status] || e.status].filter(Boolean).join(" · ")}</span>
          ${e.from === "log" ? html`<button class="btn small" aria-label=${`Delete ${e.title} at ${e.company}`} disabled=${busy}
            onClick=${() => run((a) => a.filter((x) => x.id !== e.id), "Removed.")}>Delete</button>` : html`<span class="hint" title="Found in a profile's tracker. Change its status on the job to remove it.">tracker</span>`}
        </div>`)}</div>`)}</div>` : html`<p class="hint">${q ? "Nothing matches." : "No applications yet."}</p>`}</div>
  </div>`;
}
