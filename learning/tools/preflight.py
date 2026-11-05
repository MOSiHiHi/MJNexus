"""Pre-flight checks before any large run (fetch, link check, batch labelling).

Usage (repo root):  python3 -I learning/tools/preflight.py
Prints one line per check and exits non-zero if a required check fails.
GitHub MCP status cannot be checked from a script; the run prompt checks it with ToolSearch.
"""
import json, os, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
failed = []


def check(name, ok, detail, required=True):
    print(("OK  " if ok else ("FAIL" if required else "WARN")), name, "-", detail)
    if not ok and required:
        failed.append(name)


def git_remote():
    r = subprocess.run(["git", "ls-remote", "origin", "claude/help-request-o13xuz"],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    check("git remote", r.returncode == 0 and bool(r.stdout.strip()), (r.stdout or r.stderr).strip()[:120])


def apify_budget():
    try:
        with urllib.request.urlopen("https://api.apify.com/v2/users/me/limits", timeout=30) as r:
            d = json.load(r)["data"]
        used = d["current"]["monthlyUsageUsd"]
        cap = d["limits"]["maxMonthlyUsageUsd"]
        check("apify budget", used < cap, f"used {used:.2f} of {cap} USD this cycle")
    except Exception as e:
        check("apify budget", False, str(e)[:120])


def instagram():
    try:
        with urllib.request.urlopen("https://www.instagram.com/", timeout=30) as r:
            check("instagram reachable", r.status == 200, f"HTTP {r.status}", required=False)
    except Exception as e:
        check("instagram reachable", False, str(e)[:120], required=False)


def no_untracked_junk():
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    check("clean worktree", not lines, f"{len(lines)} pending entries" if lines else "clean", required=False)


if __name__ == "__main__":
    git_remote()
    apify_budget()
    instagram()
    no_untracked_junk()
    if failed:
        print("PREFLIGHT FAILED:", ", ".join(failed))
        sys.exit(1)
    print("PREFLIGHT OK")
