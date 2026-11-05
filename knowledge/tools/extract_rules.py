#!/usr/bin/env python3
"""Deterministic extraction: resources that appear as links in saved captions.

GitHub repos, Hugging Face models/datasets/spaces, arXiv papers and other sites.
Output: knowledge/data/rules_mentions.tsv (item_id, rid, type, name, url, via, evidence)
No guessing: only what literally appears in caption text or caption links.
"""
import csv, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPORT = os.path.join(ROOT, "learning", "sources", "instagram-export")
OUT = os.path.join(ROOT, "knowledge", "data", "rules_mentions.tsv")

# Link shorteners and link-in-bio hosts hide the real target: not a resource by themselves.
SHORTENERS = {"lnkd.in", "geni.us", "bit.ly", "t.co", "linktr.ee", "tinyurl.com", "buff.ly", "ow.ly", "link.ego.app",
              "linkin.bio", "beacons.ai", "stan.store", "tr.ee", "rebrand.ly", "shorturl.at", "cutt.ly"}
GH_SKIP = {"sponsors", "orgs", "features", "topics", "marketplace", "settings", "login", "about", "pricing", "trending",
           "collections", "readme", "apps", "enterprise", "search", "explore", "copilot"}
HF_SKIP = {"docs", "blog", "papers", "learn", "pricing", "join", "login", "chat", "models", "tasks"}


def clean_url(u):
    return u.rstrip(".,;:!?)]}\"'…")


def from_text(text):
    """Yield (rid, type, name, url) found in text."""
    for m in re.finditer(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text):
        owner, repo = m.group(1), clean_url(m.group(2))
        repo = re.sub(r"\.git$", "", repo)
        if owner.lower() in GH_SKIP or not repo or repo.lower() in {"issues", "pulls"}:
            continue
        yield f"gh:{owner.lower()}/{repo.lower()}", "repo", f"{owner}/{repo}", f"https://github.com/{owner}/{repo}"
    for m in re.finditer(r"(?:https?://)?huggingface\.co/(?:(datasets|spaces)/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text):
        kind, org, name = m.group(1), m.group(2), clean_url(m.group(3))
        if org.lower() in HF_SKIP:
            continue
        typ = {"datasets": "dataset", "spaces": "tool"}.get(kind, "model")
        prefix = f"{kind}/" if kind else ""
        yield f"hf:{prefix}{org.lower()}/{name.lower()}", typ, f"{org}/{name}", f"https://huggingface.co/{prefix}{org}/{name}"
    for m in re.finditer(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", text):
        yield f"arxiv:{m.group(1)}", "paper", f"arXiv {m.group(1)}", f"https://arxiv.org/abs/{m.group(1)}"


def site_of(url):
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower().rstrip(".")
    if not host or "." not in host or host in SHORTENERS or "instagram" in host:
        return None
    if host in {"github.com", "huggingface.co", "arxiv.org"}:
        return None   # handled precisely above
    return host


def main():
    cat = {r["url"]: r for r in csv.DictReader(open(os.path.join(EXPORT, "catalog.tsv"), encoding="utf-8"), delimiter="\t")}
    rows, seen = [], set()
    for r in csv.DictReader(open(os.path.join(EXPORT, "table.tsv"), encoding="utf-8"), delimiter="\t"):
        caption = cat.get(r["url"], {}).get("caption", "")
        links = r["links_in_caption"].split()
        text = caption + " " + " ".join(links)
        for rid, typ, name, url in from_text(text):
            if (r["id"], rid) not in seen:
                seen.add((r["id"], rid))
                rows.append([r["id"], rid, typ, name, url, "link", url])
        for u in links:
            host = site_of(u)
            if host and (r["id"], f"site:{host}") not in seen:
                seen.add((r["id"], f"site:{host}"))
                rows.append([r["id"], f"site:{host}", "site", host, u if u.startswith("http") else "https://" + u, "link", u])
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["item_id", "rid", "type", "name", "url", "via", "evidence"])
        w.writerows(rows)
    kinds = {}
    for row in rows:
        kinds[row[2]] = kinds.get(row[2], 0) + 1
    print(len(rows), "mentions;", kinds, "; unique resources:", len({r[1] for r in rows}))


if __name__ == "__main__":
    main()
