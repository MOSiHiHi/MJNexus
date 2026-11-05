#!/usr/bin/env python3
"""Ask the tool radar from the command line (used in chat and in Claude Code).

  python3 -I knowledge/tools/radar.py find <words>           resources and items matching words
  python3 -I knowledge/tools/radar.py top [--category C] [--n 20]
  python3 -I knowledge/tools/radar.py resource <rid or name>  everything linked to one resource
  python3 -I knowledge/tools/radar.py item <id>               one saved item with its links and video layer
  python3 -I knowledge/tools/radar.py licenses                repos grouped by license
  python3 -I knowledge/tools/radar.py stats
Read-only. The database is rebuilt by build_db.py.
"""
import json, os, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kg.sqlite")


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def show(rows, cols):
    for r in rows:
        print(" | ".join(str(r[c] if r[c] is not None else "") for c in cols))


def find(words):
    c = con()
    q = "%" + " ".join(words).lower() + "%"
    print("# resources")
    show(c.execute("""SELECT rid, name, type, category, mentions, license FROM resource
                      WHERE lower(name) LIKE ? OR lower(rid) LIKE ? OR lower(what_fa) LIKE ?
                      ORDER BY mentions DESC LIMIT 25""", (q, q, q)), ["rid", "name", "type", "category", "mentions", "license"])
    print("# items")
    show(c.execute("""SELECT id, creator, saved_at, info_level, coalesce(nullif(what_fa,''), substr(summary_fa,1,90)) AS what, url
                      FROM item WHERE lower(caption) LIKE ? OR lower(summary_fa) LIKE ? OR lower(what_fa) LIKE ?
                      ORDER BY saved_at DESC LIMIT 25""", (q, q, q)), ["id", "creator", "saved_at", "info_level", "what", "url"])


def top(args):
    cat = args[args.index("--category") + 1] if "--category" in args else None
    n = int(args[args.index("--n") + 1]) if "--n" in args else 20
    sql = "SELECT rid, name, type, category, mentions, main_mentions, license, last_commit, ring FROM resource WHERE type != 'site'"
    params = []
    if cat:
        sql += " AND category = ?"
        params.append(cat)
    sql += " ORDER BY main_mentions DESC, mentions DESC LIMIT ?"
    params.append(n)
    show(con().execute(sql, params), ["rid", "name", "type", "category", "mentions", "main_mentions", "license", "last_commit", "ring"])


def resource(key):
    c = con()
    r = c.execute("SELECT * FROM resource WHERE rid = ? OR lower(name) = lower(?) ORDER BY mentions DESC LIMIT 1", (key, key)).fetchone()
    if not r:
        sys.exit("not found; try: radar.py find " + key)
    print(json.dumps(dict(r), ensure_ascii=False, indent=1))
    print("# items")
    show(c.execute("""SELECT i.id, e.role, e.via, i.saved_at, i.creator, coalesce(nullif(i.what_fa,''), substr(i.summary_fa,1,90)) AS what, i.url
                      FROM edge e JOIN item i ON e.src = 'item:' || i.id
                      WHERE e.rel = 'MENTIONS' AND e.dst = ? ORDER BY i.saved_at DESC""", ("resource:" + r["rid"],)),
         ["id", "role", "via", "saved_at", "creator", "what", "url"])
    print("# claims")
    show(c.execute("""SELECT cl.cid, cl.text, cl.verification FROM edge e JOIN claim cl ON e.src = 'claim:' || cl.cid
                      WHERE e.rel = 'CLAIM_ABOUT' AND e.dst = ?""", ("resource:" + r["rid"],)), ["cid", "text", "verification"])


def item(i):
    c = con()
    r = c.execute("SELECT * FROM item WHERE id = ?", (i.zfill(4),)).fetchone()
    if not r:
        sys.exit("no such item")
    d = dict(r)
    d["caption"] = (d["caption"] or "")[:600]
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("# links")
    show(c.execute("SELECT rel, dst, via, role FROM edge WHERE src = ?", ("item:" + d["id"],)), ["rel", "dst", "via", "role"])
    v = c.execute("SELECT * FROM video WHERE item_id = ?", (d["id"],)).fetchone()
    if v:
        print("# video")
        print(json.dumps(dict(v), ensure_ascii=False, indent=1))


def licenses():
    show(con().execute("""SELECT coalesce(nullif(license,''),'(none found)') AS license, count(*) AS repos
                          FROM resource WHERE repo != '' GROUP BY 1 ORDER BY 2 DESC"""), ["license", "repos"])


def stats():
    c = con()
    for t in ("account", "item", "video", "resource", "concept", "claim", "series", "project", "edge"):
        print(t, c.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    print("# info levels")
    show(c.execute("SELECT coalesce(nullif(info_level,''),'unknown') AS level, count(*) AS n FROM item GROUP BY 1 ORDER BY 2 DESC"), ["level", "n"])
    print("# categories (resources)")
    show(c.execute("SELECT category, count(*) AS n FROM resource GROUP BY 1 ORDER BY 2 DESC"), ["category", "n"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, rest = sys.argv[1], sys.argv[2:]
    {"find": lambda: find(rest), "top": lambda: top(rest), "resource": lambda: resource(" ".join(rest)),
     "item": lambda: item(rest[0]), "licenses": licenses, "stats": stats}.get(cmd, lambda: sys.exit(__doc__))()
