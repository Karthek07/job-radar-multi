"""Run Job Radar for every profile in profiles.json, then the cross-profile pass.

  python engine/multi.py                  # full run for every profile (what GitHub Actions does)
  python engine/multi.py --requests-only  # only profiles with app requests waiting (quick, after an edit in the app)
  python engine/multi.py --only main      # one profile
  python engine/multi.py --check          # prints run=true/false: is there anything to do at all?
  python engine/multi.py --fixtures F     # offline test, same jobs for every profile
Each profile runs in its own process, so one profile failing never stops the others.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import profiles as P  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--requests-only", action="store_true")
    ap.add_argument("--no-claude", action="store_true")
    ap.add_argument("--fixtures")
    ap.add_argument("--only")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    repo = os.path.abspath(args.repo)
    cfg = P.load_profiles(repo)
    plist = [p for p in cfg["profiles"] if not args.only or p["id"] == args.only]

    if args.check:
        todo = any(P.has_resume(repo, p) or P.pending_requests(repo, p) for p in plist)
        print(f"run={'true' if todo else 'false'}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
                fh.write(f"run={'true' if todo else 'false'}\n")
        return 0

    failed = []
    for p in plist:
        root = P.root_of(repo, p)
        reqs = P.pending_requests(repo, p)
        if args.requests_only and not reqs:
            continue
        if not P.has_resume(repo, p) and not reqs:
            print(f"== {p['name']} ({p['id']}): no resume yet, skipped")
            continue
        cmd = [sys.executable, os.path.join(HERE, "run.py"), "--root", root]
        if args.requests_only:
            cmd.append("--requests-only")
        if args.no_claude:
            cmd.append("--no-claude")
        if args.fixtures:
            cmd += ["--fixtures", os.path.abspath(args.fixtures)]
        t = time.time()
        print(f"== {p['name']} ({p['id']}) in {p['root'] or '.'}", flush=True)
        rc = subprocess.call(cmd)
        print(f"== {p['id']} finished in {int(time.time() - t)}s (exit {rc})", flush=True)
        if rc:
            failed.append(p["id"])

    P.cross_profile_pass(repo, cfg)
    if failed:
        print(f"profiles that failed: {', '.join(failed)}")
    # a failed profile still lets the others' results be saved; fail the job only when nothing worked
    return 1 if failed and len(failed) == len(plist) else 0


if __name__ == "__main__":
    sys.exit(main())
