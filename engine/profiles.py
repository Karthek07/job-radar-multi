"""Several search profiles in one Job Radar repo, and what ties them together.

Layout
  profiles.json                 which profiles exist + "exclusive_companies" (the no-overlap switch)
  profile/, data/, user/ ...    the first profile ("main"), exactly where a single-profile Job Radar keeps them
  profiles/<id>/profile/ ...    every other profile: the same folders, one level down
  applications.json             every application you made, from any profile (written by the apps; never by the engine)
  shared/applied_index.json     engine-built: per company, every title you applied for (applications.json + trackers)
  shared/company_owners.json    engine-built: which profile each company belongs to (kept stable between runs)

After every search the cross-profile pass below stamps each job in each profile's data/jobs.json with
  company_key     the company name normalised the same way the apps do it
  company_owner   the one profile this company belongs to (used when exclusive_companies is on)
  also_in         other profiles that found jobs at this company too
  applied_before  titles you applied for at this company before (newest first)
The apps hide jobs whose company_owner is another profile when the switch is on, and show applied_before on every job.
"""
import json
import os
import re
from datetime import datetime, timezone

PIPE = ("applied", "interview", "offer", "rejected")
LEGAL = r"\b(inc|ltd|llc|ulc|corp|corporation|co|company|limited|lp|gmbh|plc|canada|usa|us|com|ca)\b"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DEFAULT = {"profiles": [{"id": "main", "name": "Main", "root": ""}], "exclusive_companies": False}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


GENERIC = r"\b(the|technologies|technology|tech|labs|group|holdings|solutions|software|systems|services|international|global|digital|hq|io)\b"


def canon_company(name):
    """'Shopify Inc.', 'shopify' and 'Shopify Technologies' are one company.
    Kept identical in web/profiles.js (canonCompany) and the Android app (Company.key)."""
    n = norm(name)
    if "amazon" in n.split():
        return "amazon"
    n = re.sub(r"\s+", " ", re.sub(LEGAL, " ", n)).strip() or n
    g = re.sub(r"\s+", " ", re.sub(GENERIC, " ", n)).strip()
    return g or n


def same_company(a, b):
    """Two keys are one company when equal, or when one's words start the other's ('faire' / 'faire wholesale').
    The shorter one must be at least 4 letters so 'td' doesn't swallow 'td synnex'. Same rule in the apps."""
    if not a or not b:
        return False
    if a == b:
        return True
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    return len(s) >= 4 and (l + " ").startswith(s + " ")


def group_keys(keys):
    """key -> the shortest key that is the same company, so prefix variants share one owner."""
    out = {}
    roots = []
    for k in sorted(set(keys), key=lambda x: (len(x), x)):
        root = next((r for r in roots if same_company(r, k)), None)
        if root is None:
            roots.append(k)
            root = k
        out[k] = root
    return out


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_profiles(repo):
    """profiles.json, cleaned: unique safe ids, 'main' always first at the repo root."""
    raw = load(os.path.join(repo, "profiles.json"), None) or {}
    out, seen = [], set()
    for p in raw.get("profiles") or []:
        pid = str(p.get("id", "")).strip().lower()
        if not ID_RE.match(pid) or pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "name": (p.get("name") or pid).strip()[:40], "root": "" if pid == "main" else f"profiles/{pid}"})
    if "main" not in seen:
        out.insert(0, dict(DEFAULT["profiles"][0]))
    out.sort(key=lambda p: p["id"] != "main")
    return {"profiles": out, "exclusive_companies": bool(raw.get("exclusive_companies"))}


def root_of(repo, p):
    return os.path.join(repo, p["root"]) if p["root"] else repo


def has_resume(repo, p):
    r = load(os.path.join(root_of(repo, p), "profile", "resume.json"), {})
    return bool(r.get("experience"))


def pending_requests(repo, p):
    d = os.path.join(root_of(repo, p), "requests")
    return sorted(f for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []


def _date(v):
    """Anything date-like -> YYYY-MM-DD ('' when unknown)."""
    if isinstance(v, (int, float)) and v > 0:
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, timezone.utc).date().isoformat()
    s = str(v or "")
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def applied_index(repo, cfg, jobs_by_profile):
    """company_key -> [{title, company, profile, date, status, job_id, source}], newest first, no duplicates."""
    idx = {}
    seen = set()

    def add(e):
        key = canon_company(e.get("company", "")) or e.get("company_key", "")
        if not key or not (e.get("title") or "").strip():
            return
        sig = (e.get("profile", ""), e.get("job_id") or "", key, norm(e.get("title", "")))
        loose = (e.get("profile", ""), key, norm(e.get("title", "")))
        if sig in seen or loose in seen:
            return
        seen.update({sig, loose})
        idx.setdefault(key, []).append({k: e.get(k, "") for k in ("title", "company", "profile", "date", "status", "job_id", "source")})

    # 1) the log the apps keep (includes past applications you typed in or imported)
    for e in (load(os.path.join(repo, "applications.json"), {}) or {}).get("applications", []):
        if isinstance(e, dict):
            add({**e, "date": _date(e.get("date"))})
    # 2) every profile's tracker, in case an app wrote the status but not the log (older app versions, offline)
    for p in cfg["profiles"]:
        st = load(os.path.join(root_of(repo, p), "user", "state.json"), {}).get("statuses", {})
        jobs = jobs_by_profile.get(p["id"], {})
        for jid, v in st.items():
            v = v if isinstance(v, dict) else {"status": v}
            j = jobs.get(jid) or v  # newer apps also store title/company on the status itself
            if v.get("status") in PIPE and j.get("title"):
                add({"title": j["title"], "company": j.get("company", ""), "profile": p["id"], "date": _date(v.get("at")),
                     "status": v["status"], "job_id": jid, "source": "tracker"})
    for k in idx:
        idx[k].sort(key=lambda e: e.get("date") or "", reverse=True)
    return idx


def cross_profile_pass(repo, cfg=None):
    """Stamp company_key / company_owner / also_in / applied_before on every profile's jobs; write the shared files."""
    cfg = cfg or load_profiles(repo)
    ids = [p["id"] for p in cfg["profiles"]]
    order = {pid: i for i, pid in enumerate(ids)}
    files, jobs_by_profile = {}, {}
    for p in cfg["profiles"]:
        path = os.path.join(root_of(repo, p), "data", "jobs.json")
        f = load(path, None)
        if f and isinstance(f.get("jobs"), list):
            files[p["id"]] = (path, f)
            jobs_by_profile[p["id"]] = {j["id"]: j for j in f["jobs"] if j.get("id")}
    raw_idx = applied_index(repo, cfg, jobs_by_profile)
    all_keys = set(raw_idx) | {canon_company(j.get("company", "")) for js in jobs_by_profile.values() for j in js.values()}
    grp = group_keys(k for k in all_keys if k)
    idx = {}
    for k, entries in raw_idx.items():
        idx.setdefault(grp[k], []).extend(entries)
    for k in idx:
        idx[k].sort(key=lambda e: e.get("date") or "", reverse=True)

    # who has what: best score per company per profile, and saved claims
    best = {}  # key -> {pid: score}
    saved = {}  # key -> {pid}
    for p in cfg["profiles"]:
        st = load(os.path.join(root_of(repo, p), "user", "state.json"), {}).get("statuses", {})
        for j in jobs_by_profile.get(p["id"], {}).values():
            key = grp.get(canon_company(j.get("company", "")))
            if not key:
                continue
            best.setdefault(key, {})
            best[key][p["id"]] = max(best[key].get(p["id"], 0), j.get("score", 0))
            s = st.get(j["id"])
            if (s.get("status") if isinstance(s, dict) else s) == "saved":
                saved.setdefault(key, set()).add(p["id"])

    owners_path = os.path.join(repo, "shared", "company_owners.json")
    old = load(owners_path, {}).get("owners", {})
    owners = {}
    for key in set(best) | set(idx):
        cands = best.get(key, {})
        applied = [e["profile"] for e in idx.get(key, []) if e.get("profile") in order]
        if applied:  # where you applied (most recently) is where the company lives
            owners[key] = applied[0]
        elif saved.get(key):  # then where you saved one of its jobs
            owners[key] = min(saved[key], key=lambda pid: (-cands.get(pid, 0), order[pid]))
        elif old.get(key) in cands:  # then wherever it was before, so jobs don't jump between profiles
            owners[key] = old[key]
        elif cands:  # new company: the profile it matches best
            owners[key] = min(cands, key=lambda pid: (-cands[pid], order[pid]))

    for pid, (path, f) in files.items():
        for j in f["jobs"]:
            key = grp.get(canon_company(j.get("company", "")), "")
            j["company_key"] = key
            j["company_owner"] = owners.get(key, pid)
            j["also_in"] = sorted((x for x in best.get(key, {}) if x != pid), key=lambda x: order.get(x, 99))
            prior = [e for e in idx.get(key, []) if not (e.get("profile") == pid and e.get("job_id") == j["id"])]
            j["applied_before"] = prior[:6]
        save(path, f)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    names = {p["id"]: p["name"] for p in cfg["profiles"]}
    save(owners_path, {"updated": now, "owners": dict(sorted(owners.items()))})
    save(os.path.join(repo, "shared", "applied_index.json"), {"updated": now, "profiles": names, "companies": dict(sorted(idx.items()))})
    overlap = sum(1 for k, v in best.items() if len(v) > 1)
    print(f"cross-profile: {len(ids)} profiles, {len(best)} companies, {overlap} found in more than one profile, "
          f"{len(idx)} companies applied to before")
    return owners, idx
