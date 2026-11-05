#!/usr/bin/env python3
"""Prepare entity-extraction batches for the language-model step.

Writes knowledge/data/llm/in/NNN.jsonl: one saved item per line with its full caption,
caption links and the titles of fetched external pages. Items without a caption are skipped
(they are marked info_level=low by build_db.py).

Usage: python3 -I knowledge/tools/prepare_llm.py [--size 250]
"""
import argparse, csv, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPORT = os.path.join(ROOT, "learning", "sources", "instagram-export")
OUT = os.path.join(ROOT, "knowledge", "data", "llm", "in")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=250)
    a = ap.parse_args()
    cat = {r["url"]: r for r in csv.DictReader(open(os.path.join(EXPORT, "catalog.tsv"), encoding="utf-8"), delimiter="\t")}
    ext = {r["url"]: r for r in csv.DictReader(open(os.path.join(EXPORT, "external.tsv"), encoding="utf-8"), delimiter="\t")}
    rows = []
    for r in csv.DictReader(open(os.path.join(EXPORT, "table.tsv"), encoding="utf-8"), delimiter="\t"):
        caption = cat.get(r["url"], {}).get("caption", "").strip()
        if not caption:
            continue
        links = r["links_in_caption"].split()
        rows.append({
            "id": r["id"], "creator": r["creator"], "url": r["url"],
            "caption": caption, "links": links,
            "external_titles": [ext[u]["title"] for u in links if u in ext and ext[u]["title"]],
        })
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    for i in range(0, len(rows), a.size):
        path = os.path.join(OUT, f"{i // a.size + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows[i:i + a.size]:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(path, len(rows[i:i + a.size]))
    print("items with caption:", len(rows))


if __name__ == "__main__":
    main()
