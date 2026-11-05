#!/usr/bin/env python3
"""Export the tool-radar datasets for the web dashboard (JSON arrays of row objects).

Output folder: knowledge/data/dashboard/
  kpis.json            one row of model totals
  categories.json      resources and saved items per radar category
  licenses.json        repos per license
  info_levels.json     saved items per evidence level
  resources.json       one row per resource (single-mention sites left out)
  resource_items.json  saved items behind each resource (for the detail view)
  items.json           every saved post or reel with its account (for account details)
  graph_nodes.json, graph_edges.json        knowledge canvas (domains, concepts, categories, resources, accounts)
  ontology_nodes.json, ontology_edges.json  schema canvas
Usage: python3 -I knowledge/tools/export_dashboard.py
"""
import collections, json, os, sqlite3

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.path.join(ROOT, "knowledge", "kg.sqlite")
OUT = os.path.join(ROOT, "knowledge", "data", "dashboard")

CATEGORY_FA = {
    "coding-agents": "ایجنت‌های کدنویس و IDE", "agent-frameworks": "چارچوب و هماهنگ‌سازی ایجنت",
    "rag-knowledge": "RAG، دانش و اسناد", "models-inference": "مدل‌ها و اجرای مدل",
    "media-generation": "تولید تصویر، ویدیو و صدا", "automation-business": "اتوماسیون و کسب‌وکار",
    "dev-infra-security": "ابزار توسعه، زیرساخت و امنیت", "learning-resources": "منابع یادگیری", "other": "سایر",
}
INFO_FA = {"high": "پرمحتوا", "medium": "متوسط", "low": "کم‌اطلاع", "unknown": "بررسی‌نشده"}


def short(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def rows(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    con = sqlite3.connect(DB)
    os.makedirs(OUT, exist_ok=True)
    keep = "NOT (type = 'site' AND mentions < 2)"
    res = rows(con, f"""SELECT rid, name, type, category, mentions, main_mentions, coalesce(nullif(license,''), '') AS license,
                               coalesce(nullif(last_commit,''), '') AS last_commit, ring, verification, risk_flags AS risk,
                               coalesce(what_fa, '') AS what_fa, coalesce(url, '') AS url, coalesce(repo, '') AS repo,
                               first_seen, last_seen
                        FROM resource WHERE {keep} ORDER BY main_mentions DESC, mentions DESC, name""")
    for r in res:
        r["category_fa"] = CATEGORY_FA.get(r["category"], r["category"])
        r["risk"] = ", ".join(json.loads(r["risk"] or "[]"))
        r["what_fa"] = short(r["what_fa"], 140)
        for k in ("verification", "first_seen", "last_seen"):  # not shown on the page
            r.pop(k, None)
    rids = {r["rid"] for r in res}
    items = [r for r in rows(con, """SELECT substr(e.dst, 10) AS rid, i.id AS item_id, i.url, i.creator, i.saved_at,
                                            coalesce(nullif(i.what_fa,''), substr(i.summary_fa, 1, 160), '') AS what_fa,
                                            coalesce(nullif(i.info_level,''), 'unknown') AS info, e.role, e.via
                                     FROM edge e JOIN item i ON e.src = 'item:' || i.id
                                     WHERE e.rel = 'MENTIONS'
                                     ORDER BY i.saved_at DESC, e.role = 'main' DESC""") if r["rid"] in rids]
    seen = set()  # one row per (resource, item): an item can mention a resource through several routes
    items = [r for r in items if (r["rid"], r["item_id"]) not in seen and not seen.add((r["rid"], r["item_id"]))]
    for r in items:
        r["role_fa"] = {"main": "اصلی", "context": "زمینه"}.get(r["role"], r["role"] or "")
        r["info_fa"] = INFO_FA.get(r["info"], r["info"])
        r["what_fa"] = short(r["what_fa"], 120)
        for k in ("info", "role", "via"):  # Persian labels are what the page shows
            r.pop(k, None)
    all_items = rows(con, """SELECT id AS item_id, creator, url, kind, saved_at,
                                     coalesce(nullif(what_fa,''), substr(summary_fa, 1, 160), '') AS what_fa,
                                     coalesce(nullif(info_level,''), 'unknown') AS info
                              FROM item ORDER BY saved_at DESC, id DESC""")
    for r in all_items:
        r["what_fa"] = short(r["what_fa"], 120)
        r["info_fa"] = INFO_FA.get(r.pop("info"), "")
    cats = rows(con, f"""SELECT category, count(*) AS resources, sum(main_mentions) AS main_mentions
                         FROM resource WHERE {keep} GROUP BY category ORDER BY resources DESC""")
    for c in cats:
        c["category_fa"] = CATEGORY_FA.get(c["category"], c["category"])
    lic = rows(con, f"""SELECT coalesce(nullif(license,''), 'none found') AS license, count(*) AS repos
                        FROM resource WHERE repo != '' AND repo_exists = 'yes' GROUP BY 1 ORDER BY repos DESC""")
    info = rows(con, """SELECT coalesce(nullif(info_level,''), 'unknown') AS level, count(*) AS items FROM item
                        GROUP BY 1 ORDER BY CASE level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END""")
    for r in info:
        r["level_fa"] = INFO_FA.get(r["level"], r["level"])
    one = lambda sql: con.execute(sql).fetchone()[0]
    kpis = [{
        "items": one("SELECT count(*) FROM item"),
        "resources": len(res),
        "repos": one(f"SELECT count(*) FROM resource WHERE repo != '' AND repo_exists = 'yes' AND {keep}"),
        "low_info": one("SELECT count(*) FROM item WHERE info_level = 'low'"),
        "videos": one("SELECT count(*) FROM video"),
        "claims": one("SELECT count(*) FROM claim"),
        "generated": __import__("datetime").date.today().isoformat(),
    }]
    for name, data in [("kpis", kpis), ("categories", cats), ("licenses", lic), ("info_levels", info),
                       ("resources", res), ("resource_items", items), ("items", all_items)]:
        path = os.path.join(OUT, f"{name}.json")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(name, len(data), "rows", os.path.getsize(path), "bytes")





# ---------------------------------------------------------------- canvas datasets
ENTITY_TABLE = {"Account": "account", "Item": "item", "Video": "video", "Resource": "resource", "Concept": "concept",
                "Domain": "domain", "Series": "series", "Claim": "claim", "Project": "project"}


def export_graph():
    """graph_nodes / graph_edges for the knowledge canvas, ontology_nodes / ontology_edges for the schema canvas."""
    import yaml
    con = sqlite3.connect(DB)
    blank = {"type": "", "category_fa": "", "license": "", "last_commit": "", "ring": "", "risk": "", "what_fa": "",
             "url": "", "mentions": 0, "main_mentions": 0, "items": 0, "sub": "", "first_seen": "", "homepage": "",
             "qid": "", "wikipedia_en": "", "wikipedia_fa": "", "description_en": "", "followers": 0, "followed": ""}
    nodes, edges = [], []
    titles = dict(con.execute("SELECT slug, title_fa FROM domain").fetchall())
    about = dict(con.execute("SELECT substr(dst, 9), count(DISTINCT src) FROM edge WHERE rel='ABOUT' GROUP BY 1").fetchall())
    for slug, title in titles.items():
        nodes.append(blank | {"id": "d:" + slug, "kind": "domain", "label": title, "group": slug, "size": 0, "sub": "حوزه"})
    for node, title, dom, star, qid, wen, wfa, desc in con.execute(
            "SELECT node, title, domain, star, qid, wikipedia_en, wikipedia_fa, description_en FROM concept"):
        nodes.append(blank | {"id": "c:" + node, "kind": "concept", "label": title, "group": dom, "size": about.get(node, 0),
                              "items": about.get(node, 0), "sub": titles.get(dom, dom) + (" · گرهٔ حیاتی" if star else ""),
                              "qid": qid or "", "wikipedia_en": wen or "", "wikipedia_fa": wfa or "", "description_en": desc or "",
                              "url": wfa or wen or ""})
        edges.append({"source": "c:" + node, "target": "d:" + dom, "kind": "in_domain", "weight": 1})
    for src, rel, dst in con.execute("SELECT src, rel, dst FROM edge WHERE rel IN ('PREREQ_OF','LINKS_TO')"):
        edges.append({"source": "c:" + src[8:], "target": "c:" + dst[8:], "kind": "prereq" if rel == "PREREQ_OF" else "link", "weight": 1})
    res = rows(con, """SELECT rid, name, type, category, mentions, main_mentions, coalesce(license,'') AS license,
                              coalesce(last_commit,'') AS last_commit, ring, risk_flags, coalesce(what_fa,'') AS what_fa,
                              coalesce(url,'') AS url, first_seen, homepage, qid, wikipedia_en, wikipedia_fa, description_en
                       FROM resource
                       WHERE main_mentions >= 1 AND NOT (type = 'site' AND mentions < 2)""")
    cats = collections.Counter(r["category"] for r in res)
    for c, n in cats.items():
        nodes.append(blank | {"id": "k:" + c, "kind": "category", "label": CATEGORY_FA.get(c, c), "group": c, "size": n,
                              "items": n, "sub": "دستهٔ رادار"})
    keep = set()
    for r in res:
        rid = "r:" + r["rid"]
        keep.add(r["rid"])
        nodes.append(blank | {"id": rid, "kind": "resource", "label": r["name"], "group": r["category"], "size": r["mentions"],
                              "type": r["type"], "category_fa": CATEGORY_FA.get(r["category"], r["category"]),
                              "license": r["license"], "last_commit": r["last_commit"], "ring": r["ring"],
                              "risk": ", ".join(json.loads(r["risk_flags"] or "[]")), "what_fa": short(r["what_fa"], 160),
                              "url": r["url"], "mentions": r["mentions"], "main_mentions": r["main_mentions"],
                              "items": r["mentions"], "sub": CATEGORY_FA.get(r["category"], r["category"]),
                              "first_seen": r["first_seen"] or "", "homepage": r["homepage"] or "", "qid": r["qid"] or "",
                              "wikipedia_en": r["wikipedia_en"] or "", "wikipedia_fa": r["wikipedia_fa"] or "",
                              "description_en": r["description_en"] or ""})
        edges.append({"source": rid, "target": "k:" + r["category"], "kind": "in_category", "weight": 1})
    # resource -> concept through the saved items that are about the concept (top 3 per resource)
    pairs = collections.defaultdict(list)
    for res_id, concept, n in con.execute("""SELECT substr(m.dst, 10), substr(a.dst, 9), count(*) FROM edge m
                                             JOIN edge a ON a.src = m.src AND a.rel = 'ABOUT'
                                             WHERE m.rel = 'MENTIONS' GROUP BY 1, 2"""):
        if res_id in keep:
            pairs[res_id].append((n, concept))
    for res_id, lst in pairs.items():
        for n, concept in sorted(lst, reverse=True)[:3]:
            edges.append({"source": "r:" + res_id, "target": "c:" + concept, "kind": "about", "weight": n})
    # accounts whose saved posts mention a resource on the canvas: account -> resource, weighted by posts
    posted = collections.Counter()
    for creator, res_id, _item in con.execute("""SELECT DISTINCT i.creator, substr(e.dst, 10), i.id FROM edge e
                                         JOIN item i ON e.src = 'item:' || i.id WHERE e.rel = 'MENTIONS'""").fetchall():
        if creator and res_id in keep:
            posted[(creator, res_id)] += 1
    accts = {a for a, _ in posted}
    for u, full, followers, followed, cat, saved, profile in con.execute(
            "SELECT username, full_name, followers, followed_by_owner, category, saved_items, profile_url FROM account"):
        if u not in accts:
            continue
        nodes.append(blank | {"id": "a:" + u, "kind": "account", "label": u, "group": "account", "size": saved or 0,
                              "items": saved or 0, "mentions": saved or 0, "url": profile or f"https://www.instagram.com/{u}/",
                              "sub": (full or "").strip() or "حساب اینستاگرام", "followers": followers or 0,
                              "followed": "yes" if followed else "no", "category_fa": "" if cat in (None, "—") else cat})
    for (u, res_id), n in posted.items():
        edges.append({"source": "a:" + u, "target": "r:" + res_id, "kind": "posted", "weight": n})
    onto = yaml.safe_load(open(os.path.join(ROOT, "knowledge", "ontology.yaml"), encoding="utf-8"))
    rel_n = dict(con.execute("SELECT rel, count(*) FROM edge GROUP BY rel").fetchall())
    onodes = [{"id": "o:Owner", "label": "Owner", "sub": "صاحب مدل (شما)", "count": 1}]
    for name, e in onto["entities"].items():
        n = con.execute(f"SELECT count(*) FROM {ENTITY_TABLE[name]}").fetchone()[0]
        onodes.append({"id": "o:" + name, "label": name, "sub": e.get("description_fa", ""), "count": n})
    oedges = []
    for rel, spec in onto["relations"].items():
        for f in (spec["from"] if isinstance(spec["from"], list) else [spec["from"]]):
            oedges.append({"source": "o:" + f, "target": "o:" + spec["to"], "rel": rel, "count": rel_n.get(rel, 0),
                           "owner_only": bool(spec.get("owner_only")), "planned": spec.get("status") == "planned"})
    for name, e in onto["entities"].items():  # a layer keyed by the item id (the video layer) hangs off Item
        if name != "Item" and str(e.get("key", "")).startswith("item id"):
            n = con.execute(f"SELECT count(*) FROM {ENTITY_TABLE[name]}").fetchone()[0]
            oedges.append({"source": "o:Item", "target": "o:" + name, "rel": "HAS_LAYER", "count": n,
                           "owner_only": False, "planned": False})
    for name, data in [("graph_nodes", nodes), ("graph_edges", edges), ("ontology_nodes", onodes), ("ontology_edges", oedges)]:
        path = os.path.join(OUT, f"{name}.json")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(name, len(data), "rows", os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
    export_graph()
