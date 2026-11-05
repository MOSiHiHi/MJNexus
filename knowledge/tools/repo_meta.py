#!/usr/bin/env python3
"""GitHub repo metadata through anonymous git reads (no API, no token).

For each gh:<owner>/<repo> resource: does it exist, default branch, last commit date,
license file and a best-effort license name. Resumable: repos already in repos.tsv are skipped.
Stars are not available through git and are left empty.

Usage: python3 -I knowledge/tools/repo_meta.py [--workers 4]
"""
import argparse, csv, glob, json, os, re, shutil, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "knowledge", "data")
OUT = os.path.join(DATA, "repos.tsv")
FIELDS = ["repo", "exists", "default_branch", "last_commit", "license_file", "license", "checked"]

LICENSES = [  # (name, pattern) checked in order on the license text
    ("AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("LGPL", r"GNU LESSER GENERAL PUBLIC LICENSE"),
    ("GPL-3.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 3"),
    ("GPL-2.0", r"GNU GENERAL PUBLIC LICENSE\s+Version 2"),
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("MPL-2.0", r"Mozilla Public License,?\s+(v\. |Version )?2\.0"),
    ("BSD-3-Clause", r"Redistributions in binary form.*?Neither the name"),
    ("BSD-2-Clause", r"Redistributions in binary form"),
    ("MIT", r"Permission is hereby granted, free of charge"),
    ("ISC", r"Permission to use, copy, modify, and/or distribute"),
    ("Unlicense", r"This is free and unencumbered software"),
    ("CC-BY-NC", r"Attribution-NonCommercial"),
    ("CC-BY", r"Creative Commons Attribution"),
    ("Elastic/SSPL/BUSL", r"Server Side Public License|Elastic License|Business Source License"),
]


def repos_wanted():
    want = set()
    path = os.path.join(DATA, "rules_mentions.tsv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"):
            if r["rid"].startswith("gh:"):
                want.add(r["rid"][3:])
    for p in glob.glob(os.path.join(DATA, "llm", "out", "*.jsonl")):
        for line in open(p, encoding="utf-8"):
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            for res in o.get("resources", []):
                repo = (res.get("repo") or "").strip().lower()
                if re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repo):
                    want.add(repo)
    return sorted(want)


def run(args, timeout=120, cwd=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)


def inspect(repo):
    url = f"https://github.com/{repo}"
    row = {"repo": repo, "exists": "no", "default_branch": "", "last_commit": "", "license_file": "", "license": "",
           "checked": time.strftime("%Y-%m-%d")}
    try:
        ls = run(["git", "ls-remote", "--symref", url, "HEAD"], timeout=60)
    except subprocess.TimeoutExpired:
        row["exists"] = "timeout"
        return row
    if ls.returncode != 0:
        return row
    row["exists"] = "yes"
    m = re.search(r"ref: refs/heads/(\S+)\s+HEAD", ls.stdout)
    row["default_branch"] = m.group(1) if m else ""
    tmp = tempfile.mkdtemp(prefix="repo-")
    try:
        c = run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", url, tmp], timeout=180)
        if c.returncode != 0:
            return row
        row["last_commit"] = run(["git", "log", "-1", "--format=%cI"], cwd=tmp).stdout.strip()[:10]
        names = run(["git", "ls-tree", "--name-only", "HEAD"], cwd=tmp).stdout.split()
        lic = next((n for n in names if re.match(r"(?i)^(licen[sc]e|copying)(\.(md|txt|rst))?$", n)), "")
        row["license_file"] = lic
        if lic:
            text = run(["git", "show", f"HEAD:{lic}"], cwd=tmp, timeout=120).stdout[:6000]
            row["license"] = next((name for name, pat in LICENSES if re.search(pat, text, re.I | re.S)), "other")
    except subprocess.TimeoutExpired:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    done = set()
    if os.path.exists(OUT):
        done = {r["repo"] for r in csv.DictReader(open(OUT, encoding="utf-8"), delimiter="\t")}
    todo = [r for r in repos_wanted() if r not in done]
    new = not os.path.exists(OUT)
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        if new:
            w.writeheader()
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for row in ex.map(inspect, todo):
                w.writerow(row)
                f.flush()
                print(row["repo"], row["exists"], row["last_commit"], row["license"], flush=True)
    print("checked", len(todo), "repos; total", len(done) + len(todo))


if __name__ == "__main__":
    main()
