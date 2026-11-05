#!/usr/bin/env python3
"""Fetch a short readable summary of each external link found in saved captions.

Uses the public Jina Reader route (the 'web' backend of agent-reach). Public pages only: no
logins, no cookies. Politely paced. Results go to external.tsv in the export folder.
Resumable: URLs already present in external.tsv are skipped.

Usage: python3 -I learning/tools/fetch_external.py [--limit N] [--delay SECONDS]
"""
import argparse, csv, os, re, subprocess, time

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sources", "instagram-export")
OUT = os.path.join(BASE, "external.tsv")
FIELDS = ["url", "host", "status", "title", "summary", "fetched"]


def unique_external():
    seen, out = set(), []
    for row in csv.DictReader(open(os.path.join(BASE, "categorized.tsv"), encoding="utf-8"), delimiter="\t"):
        for u in row["links_in_caption"].split():
            u = u.rstrip(".,);]")
            host = re.sub(r"^https?://(www\.)?", "", u).split("/")[0].lower()
            if not host or "instagram" in host or u in seen:
                continue
            seen.add(u)
            out.append((u, host))
    return out


def done_urls():
    if not os.path.exists(OUT):
        return set()
    return {r["url"] for r in csv.DictReader(open(OUT, encoding="utf-8"), delimiter="\t")}


def fetch(url):
    try:
        res = subprocess.run(["curl", "-sS", "-m", "60", "-A", "learning-vault-bot", f"https://r.jina.ai/{url}"],
                             capture_output=True, text=True, timeout=75)
    except subprocess.TimeoutExpired:
        return "timeout", "", ""
    body = res.stdout
    if res.returncode != 0 or not body.strip():
        return "error", "", ""
    title = (re.search(r"^Title:\s*(.+)$", body, re.M) or [None, ""])[1]
    content = re.sub(r"\s+", " ", re.sub(r"^(Title|URL Source|Published Time|Markdown Content):.*$", "", body, flags=re.M)).strip()
    return "ok", title.strip()[:160], content[:600]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10**9)
    ap.add_argument("--delay", type=float, default=2.0)
    a = ap.parse_args()
    todo = [(u, h) for u, h in unique_external() if u not in done_urls()][: a.limit]
    new = not os.path.exists(OUT)
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        if new:
            w.writeheader()
        for i, (u, h) in enumerate(todo, 1):
            status, title, summary = fetch(u)
            w.writerow({"url": u, "host": h, "status": status, "title": title, "summary": summary,
                        "fetched": time.strftime("%Y-%m-%d")})
            f.flush()
            print(i, len(todo), status, h, flush=True)
            time.sleep(a.delay)


if __name__ == "__main__":
    main()
