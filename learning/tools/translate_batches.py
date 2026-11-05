#!/usr/bin/env python3
"""Batch Persian translation of saved-share summaries.

Subcommands:
  status                 counts of translated / pending items
  next [--size N]        write the next N untranslated items to batches/NNN.tsv (id<TAB>domain<TAB>text)
  merge NNN              read batches/NNN_fa.tsv (id<TAB>persian) and append to translations.tsv

Priority: domains with the most items first, so the AI pages fill in first.
Translations are written by the assistant batch by batch; each batch is committed on its own.
"""
import argparse, csv, os, glob

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sources", "instagram-export")
BATCHES = os.path.join(BASE, "batches")
TRANS = os.path.join(BASE, "translations.tsv")
FIELDS = ["id", "domain", "persian"]


def items():
    rows = list(csv.DictReader(open(os.path.join(BASE, "categorized.tsv"), encoding="utf-8"), delimiter="\t"))
    return [r for r in rows if r["domain"] != "نامشخص" and r["summary"]]


def done_ids():
    if not os.path.exists(TRANS):
        return set()
    return {r["id"] for r in csv.DictReader(open(TRANS, encoding="utf-8"), delimiter="\t")}


def pending():
    done = done_ids()
    rows = [r for r in items() if r["id"] not in done]
    counts = {}
    for r in items():
        counts[r["domain"]] = counts.get(r["domain"], 0) + 1
    rows.sort(key=lambda r: (-counts[r["domain"]], r["domain"], r["id"]))
    return rows


def cmd_status(_):
    allr = items()
    print(f"with domain: {len(allr)}; translated: {len(done_ids())}; pending: {len(pending())}")


def cmd_next(a):
    os.makedirs(BATCHES, exist_ok=True)
    n = len(glob.glob(os.path.join(BATCHES, "[0-9][0-9][0-9].tsv"))) + 1
    batch = pending()[: a.size]
    if not batch:
        print("nothing pending")
        return
    path = os.path.join(BATCHES, f"{n:03d}.tsv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "domain", "text"])
        for r in batch:
            w.writerow([r["id"], r["domain"], r["summary"].replace("\t", " ").replace("\n", " ")])
    print(path, len(batch))


def cmd_merge(a):
    src = os.path.join(BATCHES, f"{a.batch}_fa.tsv")
    rows = list(csv.DictReader(open(src, encoding="utf-8"), delimiter="\t"))
    domain = {r["id"]: r["domain"] for r in items()}
    new = not os.path.exists(TRANS)
    done = done_ids()
    with open(TRANS, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        if new:
            w.writeheader()
        added = 0
        for r in rows:
            if r["id"] in done or r["id"] not in domain:
                continue
            w.writerow({"id": r["id"], "domain": domain[r["id"]], "persian": r["persian"].replace("\t", " ").strip()})
            added += 1
    print("merged", added, "from", src)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(f=cmd_status)
    p = sub.add_parser("next")
    p.add_argument("--size", type=int, default=60)
    p.set_defaults(f=cmd_next)
    m = sub.add_parser("merge")
    m.add_argument("batch")
    m.set_defaults(f=cmd_merge)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
