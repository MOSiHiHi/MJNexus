#!/usr/bin/env python3
"""Build knowledge/kg.sqlite from every source, following knowledge/ontology.yaml.

Sources
  instagram-index/index/profiles.tsv, analysis/enriched-all.tsv     followed accounts
  learning/sources/instagram-export/table.tsv, catalog.tsv, creators  saved items and creators
  learning/graph/graph.json                                          concepts, domains, prerequisites
  knowledge/data/rules_mentions.tsv                                  resources found in links
  knowledge/data/llm/out/*.jsonl                                     language-model extraction
  knowledge/data/video/*.json                                        video layer
  knowledge/data/repos.tsv                                           repo license and activity
  knowledge/data/radar_owner.tsv                                     owner-only ring, notes, verification
  knowledge/data/projects.tsv, project_links.tsv                     owner-only projects

Outputs: knowledge/kg.sqlite, knowledge/data/resources.jsonl, knowledge/data/radar.json
Usage: python3 -I knowledge/tools/build_db.py
"""
import collections, csv, glob, json, os, re, sqlite3, sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
K = os.path.join(ROOT, "knowledge")
DATA = os.path.join(K, "data")
EXPORT = os.path.join(ROOT, "learning", "sources", "instagram-export")
DB = os.path.join(K, "kg.sqlite")
csv.field_size_limit(10**8)

SCHEMA = """
CREATE TABLE account(username TEXT PRIMARY KEY, full_name TEXT, followers INTEGER, followed_by_owner INTEGER,
  category TEXT, domain TEXT, saved_items INTEGER, profile_url TEXT);
CREATE TABLE item(id TEXT PRIMARY KEY, url TEXT, shortcode TEXT, kind TEXT, saved_at TEXT, creator TEXT,
  caption TEXT, summary_en TEXT, summary_fa TEXT, hashtags TEXT, domain TEXT, use_kind TEXT, info_level TEXT,
  cta INTEGER, category TEXT, what_fa TEXT, use_fa TEXT, concepts TEXT, has_video INTEGER);
CREATE TABLE video(item_id TEXT PRIMARY KEY, duration_s REAL, language TEXT, transcript TEXT, summary_fa TEXT,
  key_points_fa TEXT, on_screen TEXT, references_json TEXT, extracted_by TEXT, extracted_at TEXT);
CREATE TABLE resource(rid TEXT PRIMARY KEY, name TEXT, type TEXT, url TEXT, repo TEXT, repo_exists TEXT,
  license TEXT, last_commit TEXT, category TEXT, mentions INTEGER, main_mentions INTEGER, first_seen TEXT,
  last_seen TEXT, risk_flags TEXT, verification TEXT, ring TEXT, notes_fa TEXT, what_fa TEXT);
CREATE TABLE concept(node TEXT PRIMARY KEY, title TEXT, domain TEXT, star INTEGER);
CREATE TABLE domain(slug TEXT PRIMARY KEY, title_fa TEXT);
CREATE TABLE series(id TEXT PRIMARY KEY, creator TEXT, name TEXT);
CREATE TABLE claim(cid TEXT PRIMARY KEY, item_id TEXT, text TEXT, verification TEXT);
CREATE TABLE project(pid TEXT PRIMARY KEY, name TEXT, goal_fa TEXT, status TEXT);
CREATE TABLE edge(src TEXT, rel TEXT, dst TEXT, via TEXT, role TEXT, evidence TEXT);
CREATE INDEX edge_src ON edge(src, rel);
CREATE INDEX edge_dst ON edge(dst, rel);
"""


def tsv(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or re.sub(r"\s+", "-", name.strip().lower())


def site_rid(url):
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower().rstrip(".")
    return f"site:{host}" if host and "." in host else ""


def main():
    onto = yaml.safe_load(open(os.path.join(K, "ontology.yaml"), encoding="utf-8"))
    enums = onto["enums"]
    cats, rings = set(enums["radar_category"]), set(enums["radar_ring"])
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    edges = []

    def edge(src, rel, dst, via="", role="", evidence=""):
        if rel not in onto["relations"]:
            sys.exit(f"relation {rel} is not in the ontology")
        edges.append((src, rel, dst, via, role, (evidence or "")[:300]))

    # --- concepts and domains
    g = json.load(open(os.path.join(ROOT, "learning", "graph", "graph.json"), encoding="utf-8"))
    for d in g["domains"]:
        con.execute("INSERT INTO domain VALUES (?,?)", (d["id"], d["title"]))
    for n in g["nodes"]:
        con.execute("INSERT INTO concept VALUES (?,?,?,?)", (n["id"], n["title"], n["domain"], int(n["star"])))
        edge(f"concept:{n['id']}", "IN_DOMAIN", f"domain:{n['domain']}", "graph")
    for e in g["edges"]:
        rel = "PREREQ_OF" if e["kind"] == "next" else "LINKS_TO"
        edge(f"concept:{e['from']}", rel, f"concept:{e['to']}", "graph")

    # --- accounts
    enriched = {r["username"].lower(): r for r in tsv(os.path.join(ROOT, "instagram-index", "analysis", "enriched-all.tsv"))}
    creators = {r["creator"].lower(): r for r in tsv(os.path.join(EXPORT, "creators.tsv"))}
    accounts = {}
    for r in tsv(os.path.join(ROOT, "instagram-index", "index", "profiles.tsv")):
        u = r["username"].lower()
        if r.get("status") != "ok":
            continue
        dom = (enriched.get(u, {}).get("domains") or enriched.get(u, {}).get("domain") or "").split("؛")[0].strip()
        accounts[u] = [u, r["full_name"], int(r["followers"] or 0), 1, r["category"], dom, 0, r["profile_url"]]
        edge("owner", "FOLLOWS", f"account:{u}", "profiles.tsv")
    for u, r in creators.items():
        if u in accounts:
            accounts[u][6] = int(r["saved_items"])
        else:
            accounts[u] = [u, "", None, 0, "", "", int(r["saved_items"]), r["profile_url"]]
    con.executemany("INSERT INTO account VALUES (?,?,?,?,?,?,?,?)", accounts.values())

    # --- items
    cat = {r["url"]: r for r in tsv(os.path.join(EXPORT, "catalog.tsv"))}
    table = tsv(os.path.join(EXPORT, "table.tsv"))
    llm = {}
    for p in sorted(glob.glob(os.path.join(DATA, "llm", "out", "*.jsonl"))):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                try:
                    o = json.loads(line)
                    llm[o["id"]] = o
                except (json.JSONDecodeError, KeyError):
                    pass
    videos = {}
    for p in glob.glob(os.path.join(DATA, "video", "*.json")):
        v = json.load(open(p, encoding="utf-8"))
        videos[v["item_id"]] = v
    saved_at = {}
    for r in table:
        i = r["id"]
        caption = cat.get(r["url"], {}).get("caption", "")
        o = llm.get(i, {})
        info = o.get("info") or ("low" if not caption.strip() else "")
        kind = "reel" if "/reel/" in r["url"] else "post" if "/p/" in r["url"] else "other"
        saved_at[i] = r["date"]
        con.execute("INSERT INTO item VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            i, r["url"], r["url"].rstrip("/").split("/")[-1], kind, r["date"], r["creator"].lower(), caption,
            r["summary"], r["persian"], cat.get(r["url"], {}).get("hashtags", ""), r["domain"], o.get("use") or "", info,
            int(o["cta"]) if isinstance(o.get("cta"), bool) else None, o.get("category") or "",
            o.get("what_fa") or "", o.get("use_fa") or "", json.dumps(o.get("concepts") or [], ensure_ascii=False),
            int(i in videos)))
        if r["creator"]:
            edge(f"account:{r['creator'].lower()}", "POSTED", f"item:{i}", "export")
        if r["domain"] and r["domain"] != "نامشخص":
            edge(f"item:{i}", "IN_DOMAIN", f"domain:{r['domain']}", "rule")
        if r["node"]:
            edge(f"item:{i}", "ABOUT", f"concept:{r['node']}", "rule")
        for n in o.get("nodes") or []:
            edge(f"item:{i}", "ABOUT", f"concept:{n}", "llm")

    # --- resources and mentions
    res = collections.defaultdict(lambda: {"names": collections.Counter(), "types": collections.Counter(),
                                          "cats": collections.Counter(), "items": set(), "main": set(),
                                          "url": "", "repo": "", "risk": set(), "what": []})
    alias = {}  # name slug -> repo rid, learned from items that give both a name and a repo
    for o in llm.values():
        for r in o.get("resources") or []:
            repo = (r.get("repo") or "").strip().lower()
            if repo and r.get("name"):
                alias.setdefault(slug(r["name"]), f"gh:{repo}")

    def add(item_id, rid, name, typ, via, role, evidence, url="", repo=""):
        d = res[rid]
        d["names"][name] += 1
        d["types"][typ] += 1
        d["items"].add(item_id)
        if role == "main":
            d["main"].add(item_id)
        d["url"] = d["url"] or url
        d["repo"] = d["repo"] or repo
        edge(f"item:{item_id}", "MENTIONS", f"resource:{rid}", via, role, evidence)

    for r in tsv(os.path.join(DATA, "rules_mentions.tsv")):
        repo = r["rid"][3:] if r["rid"].startswith("gh:") else ""
        add(r["item_id"], r["rid"], r["name"], r["type"], "link", "main" if repo else "context", r["evidence"], r["url"], repo)
    for i, o in llm.items():
        for r in o.get("resources") or []:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            repo = (r.get("repo") or "").strip().lower()
            url = (r.get("url") or "").strip()
            if repo:
                rid = f"gh:{repo}"
            elif slug(name) in alias:
                rid = alias[slug(name)]
            elif url and site_rid(url) and r.get("type") in ("site", "service"):
                rid = site_rid(url)
            else:
                rid = f"res:{slug(name)}"
            add(i, rid, name, r.get("type") or "tool", "caption", r.get("role") or "context", name, url,
                repo or (rid[3:] if rid.startswith("gh:") else ""))
            if r.get("role") == "main":
                res[rid]["cats"][o.get("category") or "other"] += 1
                res[rid]["risk"].update(o.get("risk") or [])
                if o.get("what_fa"):
                    res[rid]["what"].append(o["what_fa"])
            else:
                res[rid]["cats"][o.get("category") or "other"] += 0
    for i, v in videos.items():
        for r in v.get("resources") or []:
            repo = (r.get("repo") or "").strip().lower()
            rid = f"gh:{repo}" if repo else alias.get(slug(r["name"]), f"res:{slug(r['name'])}")
            add(i, rid, r["name"], r.get("type") or "tool", r.get("via") or "transcript", r.get("role") or "context",
                r["name"], "", repo)
            if r.get("role") == "main":
                res[rid]["cats"][v.get("category") or "other"] += 1
                res[rid]["risk"].update(v.get("risk") or [])
                if v.get("summary_fa") and not res[rid]["what"]:
                    res[rid]["what"].append(v["summary_fa"])
        con.execute("INSERT INTO video VALUES (?,?,?,?,?,?,?,?,?,?)", (
            i, v.get("duration_s"), v.get("language"), v.get("transcript"), v.get("summary_fa"),
            json.dumps(v.get("key_points_fa") or [], ensure_ascii=False), json.dumps(v.get("on_screen") or [], ensure_ascii=False),
            json.dumps(v.get("references") or [], ensure_ascii=False), v.get("extracted_by"), v.get("extracted_at")))
        for n in v.get("nodes") or []:
            edge(f"item:{i}", "ABOUT", f"concept:{n}", "video")

    # series and claims
    for i, o in list(llm.items()) + [(k, v) for k, v in videos.items()]:
        s = o.get("series")
        creator = next((r["creator"].lower() for r in table if r["id"] == i), "")
        if isinstance(s, dict) and s.get("name"):
            sid = f"{creator}/{slug(s['name'])}"
            con.execute("INSERT OR IGNORE INTO series VALUES (?,?,?)", (sid, creator, s["name"]))
            edge(f"item:{i}", "PART_OF", f"series:{sid}", "caption", "", str(s.get("part") or ""))
        main = [r for r in (o.get("resources") or []) if r.get("role") == "main"]
        for n, text in enumerate(o.get("claims") or [], 1):
            cid = f"{i}-{n}" if i not in videos or o is not videos[i] else f"{i}-v{n}"
            con.execute("INSERT OR IGNORE INTO claim VALUES (?,?,?,?)", (cid, i, text, "unverified"))
            edge(f"item:{i}", "MAKES", f"claim:{cid}", "caption" if o is not videos.get(i) else "video")
            for r in main[:1]:
                rid = (f"gh:{r['repo'].lower()}" if r.get("repo") else alias.get(slug(r["name"]), f"res:{slug(r['name'])}"))
                edge(f"claim:{cid}", "CLAIM_ABOUT", f"resource:{rid}", "caption")

    # repo metadata and owner overrides
    repos = {r["repo"].lower(): r for r in tsv(os.path.join(DATA, "repos.tsv"))}
    owner = {r["rid"]: r for r in tsv(os.path.join(DATA, "radar_owner.tsv"))}
    out = []
    for rid, d in res.items():
        dates = sorted(saved_at[i] for i in d["items"] if saved_at.get(i))
        meta = repos.get(d["repo"], {}) if d["repo"] else {}
        category = (d["cats"].most_common(1)[0][0] if d["cats"] and d["cats"].most_common(1)[0][1] > 0 else "other")
        category = category if category in cats else "other"
        ow = owner.get(rid, {})
        ring = ow.get("ring") if ow.get("ring") in rings else "assess"
        row = {
            "rid": rid, "name": d["names"].most_common(1)[0][0], "type": d["types"].most_common(1)[0][0],
            "url": d["url"] or (f"https://github.com/{d['repo']}" if d["repo"] else ""), "repo": d["repo"],
            "repo_exists": meta.get("exists", ""), "license": meta.get("license", ""),
            "last_commit": meta.get("last_commit", ""), "category": category, "mentions": len(d["items"]),
            "main_mentions": len(d["main"]), "first_seen": dates[0] if dates else "", "last_seen": dates[-1] if dates else "",
            "risk_flags": sorted(d["risk"]), "verification": ow.get("verification") or "unverified", "ring": ring,
            "notes_fa": ow.get("notes_fa", ""), "what_fa": d["what"][0] if d["what"] else "",
        }
        out.append(row)
        con.execute("INSERT INTO resource VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            row["rid"], row["name"], row["type"], row["url"], row["repo"], row["repo_exists"], row["license"],
            row["last_commit"], row["category"], row["mentions"], row["main_mentions"], row["first_seen"],
            row["last_seen"], json.dumps(row["risk_flags"]), row["verification"], row["ring"], row["notes_fa"], row["what_fa"]))

    # owner projects
    for p in tsv(os.path.join(DATA, "projects.tsv")):
        con.execute("INSERT INTO project VALUES (?,?,?,?)", (p["pid"], p["name"], p.get("goal_fa", ""), p.get("status", "")))
    for l in tsv(os.path.join(DATA, "project_links.tsv")):
        rel = "USES" if l["rel"] == "USES" else "NEEDS"
        edge(f"project:{l['pid']}", rel, l["target"], "owner")

    con.executemany("INSERT INTO edge VALUES (?,?,?,?,?,?)", edges)
    con.commit()

    out.sort(key=lambda r: (-r["mentions"], r["name"].lower()))
    with open(os.path.join(DATA, "resources.jsonl"), "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    export_radar(con, out)
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("account", "item", "video", "resource", "concept", "series", "claim", "project", "edge")}
    print(json.dumps(counts))
    print("items with model extraction:", len(llm), "| videos:", len(videos))


def export_radar(con, resources):
    """Compact JSON for the web dashboard: real resources only (sites with one mention are skipped)."""
    keep = [r for r in resources if not (r["type"] == "site" and r["mentions"] < 2)]
    items = {}
    for rid in [r["rid"] for r in keep]:
        rows = con.execute("""SELECT i.id, i.url, i.creator, i.saved_at, i.what_fa, i.info_level, e.role
                              FROM edge e JOIN item i ON e.src = 'item:' || i.id
                              WHERE e.rel='MENTIONS' AND e.dst=? ORDER BY e.role='main' DESC, i.saved_at DESC LIMIT 8""",
                           (f"resource:{rid}",)).fetchall()
        items[rid] = [dict(zip(["id", "url", "creator", "saved_at", "what_fa", "info", "role"], r)) for r in rows]
    by_cat = collections.Counter(r["category"] for r in keep)
    info = dict(con.execute("SELECT coalesce(nullif(info_level,''),'unknown'), count(*) FROM item GROUP BY 1").fetchall())
    radar = {
        "generated": __import__("datetime").date.today().isoformat(),
        "totals": {"items": con.execute("SELECT count(*) FROM item").fetchone()[0],
                   "resources": len(keep), "repos": sum(1 for r in keep if r["repo"]),
                   "videos": con.execute("SELECT count(*) FROM video").fetchone()[0]},
        "info_levels": info,
        "categories": dict(by_cat.most_common()),
        "resources": [{k: r[k] for k in ("rid", "name", "type", "url", "repo", "license", "last_commit", "category",
                                         "mentions", "main_mentions", "first_seen", "last_seen", "risk_flags",
                                         "verification", "ring", "what_fa")} | {"items": items[r["rid"]]} for r in keep],
    }
    json.dump(radar, open(os.path.join(DATA, "radar.json"), "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
