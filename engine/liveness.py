"""Drop jobs whose posting has closed.

Aggregators (Adzuna, Jooble, Google for Jobs) keep listing jobs for days after the employer takes them down. Before a
job is listed or tailored, its apply link is opened and the job is dropped only on a clear sign it's gone:
  - the page answers 404 / 410
  - the page says so ("no longer available", "position has been filled", "job has expired", ...)
  - the posting's own schema.org validThrough date has passed
  - the link to a specific job now lands on a general careers / search page
Anything unclear (blocked, timeout, login wall) counts as still open. Results are cached in data/liveness.json:
closed jobs stay closed, open ones are checked again after a day.
"""
import html as htmllib
import json
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urljoin, urlparse

import requests

import pagefetch

VERSION = 3  # bump when the rules change, so earlier answers are re-checked
CLOSED_RX = re.compile("|".join([
    r"no longer (?:available|accepting|active|open|posted|listed)",
    r"(?:position|role|job|vacancy|opening|requisition) (?:has been|was|is) (?:filled|closed|removed|expired|cancell?ed)",
    r"(?:job|posting|position|listing|vacancy|ad|advert) (?:has )?(?:expired|closed)",
    r"this (?:job|position|posting|role|listing) (?:is )?(?:closed|expired|unavailable|not available)",
    r"(?:job|position|posting|page) (?:you(?:'re| are) looking for|you requested) (?:is|was|has|does|could|cannot|can't|no longer)[^.]{0,40}(?:available|exist|found|removed|filled|expired)",
    r"(?:we )?(?:could ?n[o']t|can ?no?t|cannot|unable to) find (?:this|that|the) (?:job|position|posting|page)",
    r"applications? (?:are |is )?(?:now )?closed",
    r"(?:no longer|not) accepting applications",
    r"job not found|posting not found|page not found",
    r"offre (?:n'est plus disponible|expirée|pourvue)",
]), re.I)

CAREERS_HOME = re.compile(r"^/?(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:careers?|jobs?|search|job-search|opportunities|en|fr)?/?$", re.I)
# query parameters that don't change which page you're on (tracking), and ones that mean "that job isn't here"
IGNORED_QUERY = re.compile(r"^(utm_.*|gh_src|gh_jid|source|src|ref|referrer|lang|locale|error|from_.*)$", re.I)
ERROR_QUERY = {"error": {"true", "1", "notfound", "not_found", "job_not_found"}}
AGGREGATOR_DETAILS = re.compile(r"(^|\.)adzuna\.[a-z.]+$", re.I)
LAND_LINK = re.compile(r'href="([^"]*/land/ad/\d+[^"]*)"', re.I)
_host_locks = defaultdict(lambda: threading.Semaphore(2))  # at most 2 requests at a time per site, so nobody rate-limits us
JOB_ID = re.compile(r"\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-|/jobs?/[^/?#]{6,}|/(?:ad|land|job|posting|req|requisition|details?)/", re.I)


def _request(url):
    host = urlparse(url).netloc.lower()
    with _host_locks[host]:
        for attempt in range(2):
            r = requests.get(url, headers={"User-Agent": pagefetch.UA, "Accept-Language": "en-CA,en;q=0.9"},
                             timeout=15, allow_redirects=False)
            if r.status_code in (403, 429) and attempt == 0:
                time.sleep(3)  # busy or rate-limited: one polite retry
                continue
            time.sleep(0.4)
            return r


def _get(url):
    """Follow redirects one hop at a time (only to public addresses). Returns (final_url, status, html) or None."""
    try:
        for _ in range(8):
            if not pagefetch._public(url):
                return None
            r = _request(url)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                url = urljoin(url, r.headers["Location"])
                continue
            return url, r.status_code, r.text[:400000] if r.status_code == 200 else ""
    except requests.RequestException:
        return None
    return None


def _valid_through(html):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            jp = pagefetch._jobposting(json.loads(block.strip()))
        except ValueError:
            continue
        if jp and jp.get("validThrough"):
            try:
                d = datetime.fromisoformat(str(jp["validThrough"]).replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


def check(url, now=None):
    """('closed' | 'open' | 'unknown', reason)."""
    now = now or datetime.now(timezone.utc)
    if not url:
        return "unknown", "no link"
    got = _get(url)
    if got is None:
        return "unknown", "couldn't open the link"
    final, status, html = got
    # an aggregator's own copy of the ad stays up after the employer closes the job: follow its Apply link instead
    start_u = urlparse(url)
    if status == 200 and AGGREGATOR_DETAILS.search(urlparse(final).netloc) and "/details/" in urlparse(final).path:
        m = LAND_LINK.search(html)
        if not m:
            # job boards often show automated visitors a different page: their own wording is never proof
            return "unknown", "no apply link on the job board's page"
        board = urlparse(final).netloc.lower()
        url = urljoin(final, htmllib.unescape(m.group(1)))
        start_u = urlparse(url)
        got = _get(url)
        if got is None:
            return "unknown", "couldn't open the employer's link"
        final, status, html = got
        if urlparse(final).netloc.lower() == board:
            return "unknown", "the job board didn't pass us on to the employer"
    end_q = dict(parse_qsl(urlparse(final).query))
    for k, bad in ERROR_QUERY.items():
        if str(end_q.get(k, "")).lower() in bad:
            return "closed", "the employer's job board says the job isn't available"
    if status in (404, 410):
        return "closed", f"the page answers {status}"
    if status != 200:
        return "unknown", f"HTTP {status}"  # 403 / 429 / 5xx: blocked or busy, not proof of anything
    vt = _valid_through(html)
    if vt and vt < now - timedelta(hours=12):
        return "closed", f"posting expired {vt.date().isoformat()}"
    title = " ".join(re.findall(r"<title[^>]*>(.*?)</title>", html, re.S | re.I))[:300]
    body = pagefetch.strip_html(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))[:20000]
    if re.search(r"\b(404|not found|expired|closed)\b", title, re.I) and not vt:
        return "closed", f"page title: {title.strip()[:80]}"
    m = CLOSED_RX.search(body)
    if m and not vt:  # a live posting with structured data wins over a stray phrase elsewhere on the page
        return "closed", f"page says \"{m.group(0)[:60]}\""
    start, end = start_u, urlparse(final)
    meaningful_q = [k for k, _ in parse_qsl(end.query) if not IGNORED_QUERY.match(k)]
    if JOB_ID.search(start.path + "?" + start.query) and CAREERS_HOME.match(end.path) and not meaningful_q and not vt:
        return "closed", "the job link now opens the general careers page"
    return "open", ""


def check_jobs(jobs, tracked, cache, budget=150, now=None, checker=check):
    """jobs: {id: job}. Removes closed jobs that aren't tracked (applied/saved...), flags closed tracked ones.
    Returns (checked, closed_ids)."""
    now = now or datetime.now(timezone.utc)
    closed = []

    def stale(e):
        if not e or e.get("v") != VERSION:  # checked with older rules: check again
            return True
        if e.get("state") == "closed":
            return False
        age = now - datetime.fromisoformat(e["at"])
        return age > (timedelta(hours=20) if e.get("state") == "open" else timedelta(hours=3))

    todo = [j for j in sorted(jobs.values(), key=lambda j: -j.get("score", 0)) if not j.get("manual") and stale(cache.get(j["id"]))][:budget]

    def run(j):
        return j["id"], checker(j.get("apply_url") or j.get("url"), now)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for jid, (state, reason) in pool.map(run, todo):
            cache[jid] = {"state": state, "reason": reason, "at": now.isoformat(), "v": VERSION}
    for jid in list(jobs):
        e = cache.get(jid)
        if e and e.get("state") == "closed":
            if jid in tracked:
                jobs[jid]["closed"] = e.get("reason") or "posting closed"
            else:
                del jobs[jid]
                closed.append(jid)
        else:
            jobs[jid].pop("closed", None)
    # forget checks of jobs long gone
    for jid in [k for k, e in cache.items() if k not in jobs and now - datetime.fromisoformat(e["at"]) > timedelta(days=30)]:
        del cache[jid]
    return len(todo), closed
