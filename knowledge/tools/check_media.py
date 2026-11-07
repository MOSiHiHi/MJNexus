#!/usr/bin/env python3
"""Validate the media-layer records in knowledge/data/video/<item_id>.json against the ontology.

Checks: required fields, enum values (category, risk, info, resource type and role), learning nodes,
and that each item id exists in the saves table. Prints one line per problem and a total.
Usage: python3 -I knowledge/tools/check_media.py [item_id ...]
"""
import csv, glob, json, os, sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VIDEO = os.path.join(ROOT, "knowledge", "data", "video")
REQUIRED = ["item_id", "url", "creator", "on_screen", "summary_fa", "key_points_fa", "resources", "claims",
            "category", "nodes", "risk", "extracted_by", "extracted_at"]


def main(ids):
    onto = yaml.safe_load(open(os.path.join(ROOT, "knowledge", "ontology.yaml"), encoding="utf-8"))
    enums = onto["enums"]
    nodes = {l.split("\t")[0].strip() for l in open(os.path.join(ROOT, "knowledge", "data", "llm", "nodes.txt"), encoding="utf-8")
             if l.strip() and not l.startswith("#")}
    saved = {r["id"] for r in csv.DictReader(open(os.path.join(ROOT, "learning", "sources", "instagram-export", "table.tsv"),
                                                   encoding="utf-8"), delimiter="\t")}
    paths = [os.path.join(VIDEO, f"{i}.json") for i in ids] if ids else sorted(glob.glob(os.path.join(VIDEO, "[0-9]*.json")))
    errors = 0

    def bad(path, msg):
        nonlocal errors
        errors += 1
        print(f"{os.path.basename(path)}: {msg}")

    for p in paths:
        try:
            v = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            bad(p, f"unreadable: {e}")
            continue
        for f in REQUIRED:
            if f not in v:
                bad(p, f"missing {f}")
        if v.get("item_id") not in saved:
            bad(p, f"unknown item_id {v.get('item_id')}")
        if v.get("category") not in enums["radar_category"]:
            bad(p, f"category {v.get('category')!r} not in radar_category")
        for r in v.get("risk") or []:
            if r not in enums["risk_flag"]:
                bad(p, f"risk {r!r} not in risk_flag")
        if v.get("info") not in (None, "low", "medium", "high"):
            bad(p, f"info {v.get('info')!r}")
        for n in v.get("nodes") or []:
            if n not in nodes:
                bad(p, f"node {n!r} not in nodes.txt")
        for r in v.get("resources") or []:
            if not r.get("name"):
                bad(p, "resource without name")
            if r.get("type") and r["type"] not in enums["resource_type"]:
                bad(p, f"resource type {r['type']!r}")
            if r.get("role") not in ("main", "context"):
                bad(p, f"resource role {r.get('role')!r}")
    print(f"checked {len(paths)} records, {errors} errors")
    return errors


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1:]) else 0)
