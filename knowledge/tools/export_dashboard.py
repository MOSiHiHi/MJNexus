#!/usr/bin/env python3
"""Export the tool-radar datasets for the web dashboard (JSON arrays of row objects).

Output folder: knowledge/data/dashboard/
  kpis.json            one row of model totals
  categories.json      resources and saved items per radar category
  licenses.json        repos per license
  info_levels.json     saved items per evidence level
  resources.json       one row per resource (single-mention sites left out)
  resource_items.json  saved items behind each resource (for the detail view)
Usage: python3 -I knowledge/tools/export_dashboard.py
"""
import json, os, sqlite3

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
                                     WHERE e.rel = 'MENTIONS' ORDER BY i.saved_at DESC""") if r["rid"] in rids]
    for r in items:
        r["role_fa"] = {"main": "اصلی", "context": "زمینه"}.get(r["role"], r["role"] or "")
        r["info_fa"] = INFO_FA.get(r["info"], r["info"])
        r["what_fa"] = short(r["what_fa"], 120)
        for k in ("info", "role", "via"):  # Persian labels are what the page shows
            r.pop(k, None)
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
                       ("resources", res), ("resource_items", items)]:
        path = os.path.join(OUT, f"{name}.json")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(name, len(data), "rows", os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
