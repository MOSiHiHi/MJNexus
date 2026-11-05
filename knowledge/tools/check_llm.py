#!/usr/bin/env python3
"""Validate language-model extraction output for one batch.

Usage: python3 -I knowledge/tools/check_llm.py NNN
Checks: every input id present once and in order, valid JSON, enums, node ids,
and that any repo or URL actually appears in the item's caption, links or titles.
"""
import glob, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LLM = os.path.join(ROOT, "knowledge", "data", "llm")
INFO = {"high", "medium", "low"}
USE = {"tool", "tutorial", "news", "idea", "entertainment"}
CAT = {"coding-agents", "agent-frameworks", "rag-knowledge", "models-inference", "media-generation",
       "automation-business", "dev-infra-security", "learning-resources", "other"}
TYPES = {"repo", "tool", "model", "paper", "course", "book", "site", "dataset", "service", "prompt_pack", "skill", "protocol"}
ROLES = {"main", "context"}
RISK = {"uncensored_model", "jailbreak", "offensive_security", "account_automation", "piracy", "unclear_license",
        "paid_lead_magnet", "hype_claim"}


def load_out(batch):
    def part_no(p):
        m = re.search(r"_p(\d+)\.jsonl$", p)
        return int(m.group(1)) if m else 0
    rows, errors = [], []
    for path in sorted(glob.glob(os.path.join(LLM, "out", f"{batch}_p*.jsonl")), key=part_no):
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                errors.append(f"{os.path.basename(path)}:{n}: invalid JSON ({e.msg})")
    return rows, errors


def check(batch):
    src = [json.loads(l) for l in open(os.path.join(LLM, "in", f"{batch}.jsonl"), encoding="utf-8") if l.strip()]
    nodes = {l.strip() for l in open(os.path.join(LLM, "nodes.txt"), encoding="utf-8") if l.strip()}
    out, errors = load_out(batch)
    ids_in = [s["id"] for s in src]
    ids_out = [o.get("id") for o in out]
    if ids_out != ids_in:
        missing = [i for i in ids_in if i not in ids_out]
        extra = [i for i in ids_out if i not in ids_in]
        errors.append(f"ids differ from input: {len(ids_out)} written vs {len(ids_in)} expected; "
                      f"missing {missing[:10]}; unexpected {extra[:10]}; order must match the input")
    text = {s["id"]: (s["caption"] + " " + " ".join(s["links"]) + " " + " ".join(s["external_titles"])).lower() for s in src}
    for o in out:
        i = o.get("id")
        def bad(msg):
            errors.append(f"id {i}: {msg}")
        if o.get("info") not in INFO: bad("info")
        if not isinstance(o.get("cta"), bool): bad("cta must be true/false")
        if o.get("use") not in USE: bad("use")
        if o.get("category") not in CAT: bad("category")
        res = o.get("resources")
        if not isinstance(res, list) or len(res) > 8: bad("resources must be a list of at most 8")
        for r in res or []:
            if not r.get("name"): bad("resource without name")
            if r.get("type") not in TYPES: bad(f"resource type {r.get('type')}")
            if r.get("role") not in ROLES: bad(f"resource role {r.get('role')}")
            repo = (r.get("repo") or "").lower().strip()
            if repo and repo not in text.get(i, ""): bad(f"repo {repo} not found in source")
            url = (r.get("url") or "").lower().strip()
            core = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
            if core and core not in text.get(i, ""): bad(f"url {url} not found in source")
        if not isinstance(o.get("concepts"), list) or len(o.get("concepts", [])) > 5: bad("concepts")
        nd = o.get("nodes")
        if not isinstance(nd, list) or len(nd) > 2 or any(n not in nodes for n in nd): bad(f"nodes {nd}")
        s = o.get("series")
        if s is not None and not (isinstance(s, dict) and "name" in s): bad("series must be null or {name, part}")
        if not isinstance(o.get("claims"), list) or len(o.get("claims", [])) > 3: bad("claims")
        if not isinstance(o.get("risk"), list) or any(x not in RISK for x in o.get("risk", [])): bad("risk")
        for f in ("what_fa", "use_fa"):
            if not isinstance(o.get(f), str) or not o.get(f).strip(): bad(f"{f} empty")
    return errors


if __name__ == "__main__":
    b = sys.argv[1]
    errs = check(b)
    if errs:
        print(f"{len(errs)} problems in batch {b}:")
        print("\n".join(errs[:60]))
        sys.exit(1)
    print(f"OK batch {b}")
