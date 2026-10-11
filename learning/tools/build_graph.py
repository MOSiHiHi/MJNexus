#!/usr/bin/env python3
"""Build the learning graph.

Structure (public, no personal data):
    python3 -I learning/tools/build_graph.py
        -> learning/graph/graph.json   nodes, domains, edges

With the owner's private records (never commit the outputs):
    python3 -I learning/tools/build_graph.py --records <private.json> --out <dir>
        -> <dir>/learning-graph.json   graph + levels, interests, strengths
        -> <dir>/learning-graph.mmd    Mermaid (GitHub, Notion, Obsidian, mermaid.live …)
        -> <dir>/learning-graph.html   self-contained page, no external files

Edges:
    next   order of nodes inside a domain (tree.md order)
    link   a wiki page links to another node's page (cross-references)
"""
import argparse, glob, html, json, os, re

LEARN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ["ai", "gamedev", "math", "programming-infra", "physics-astronomy", "design-typography",
         "hardware-tech-privacy", "business-marketing", "learning-language-books", "media-entertainment",
         "history-myth", "news-politics", "society-religion", "health-sports", "music-sound", "visual-art",
         "culture-spirituality"]
STEP_COLORS = {0: "#d9dde8", 1: "#f6d58a", 2: "#e9a23b", 3: "#b8650a"}


def structure():
    domains, nodes, edges = [], [], []
    for d in ORDER:
        tree = open(os.path.join(LEARN, d, "tree.md"), encoding="utf-8").read()
        title = re.search(r"^# (.+)", tree, re.M).group(1).split(":")[-1].strip()
        domains.append({"id": d, "title": title})
        folders = sorted(x for x in os.listdir(os.path.join(LEARN, d)) if re.match(r"\d\d-", x))
        prev = None
        for f in folders:
            nid = f"{d}/{f}"
            md = open(os.path.join(LEARN, d, f, "README.md"), encoding="utf-8").read()
            t = re.search(r"^# (.+)", md, re.M).group(1)
            star = "⭐" in t
            t = re.sub(r"^[0-9۰-۹]+\.\s*", "", t.replace("⭐", "").strip())
            nodes.append({"id": nid, "domain": d, "title": t, "star": star})
            if prev:
                edges.append({"from": prev, "to": nid, "kind": "next"})
            prev = nid
    ids = {n["id"] for n in nodes}
    seen = {(e["from"], e["to"]) for e in edges}
    for n in nodes:
        md = open(os.path.join(LEARN, n["id"], "README.md"), encoding="utf-8").read()
        for target in re.findall(r"\]\(([^)#\s]+README\.md)\)", md):
            p = os.path.normpath(os.path.join(LEARN, n["id"], target))
            tid = os.path.relpath(os.path.dirname(p), LEARN).replace(os.sep, "/")
            if tid in ids and tid != n["id"] and (n["id"], tid) not in seen and (tid, n["id"]) not in seen:
                edges.append({"from": n["id"], "to": tid, "kind": "link"})
                seen.add((n["id"], tid))
    return {"version": 1, "domains": domains, "nodes": nodes, "edges": edges}


def merge(g, rec):
    levels = rec.get("levels", {})
    declared = rec.get("interests", {}).get("declared", {})
    for n in g["nodes"]:
        lv = levels.get(n["id"], {})
        n["step"] = int(lv.get("step", 0))
        n["date"] = lv.get("date", "")
    for d in g["domains"]:
        ns = [n for n in g["nodes"] if n["domain"] == d["id"]]
        d["score"] = round(sum(n["step"] for n in ns) / (3 * len(ns)), 3)
        d["interest"] = declared.get(d["id"], 0)
        sig = rec.get("signals", {}).get(d["id"])
        d["signal"] = round(sig["correct"] / sig["total"], 2) if sig and sig.get("total") else None
    g["strengths"] = rec.get("strengths", [])
    g["updated"] = rec.get("updated", "")
    return g


def mermaid(g):
    sid = {n["id"]: f"n{i}" for i, n in enumerate(g["nodes"])}
    out = ["flowchart LR"]
    for d in g["domains"]:
        mark = " ❤" if d.get("interest", 0) > 0 else ""
        out.append(f'  subgraph {d["id"].replace("-", "_")}["{d["title"]}{mark}"]')
        for n in (x for x in g["nodes"] if x["domain"] == d["id"]):
            label = ("⭐ " if n["star"] else "") + n["title"].replace('"', "'")
            out.append(f'    {sid[n["id"]]}["{label}"]:::s{n.get("step", 0)}')
        out.append("  end")
    for e in g["edges"]:
        arrow = "-->" if e["kind"] == "next" else "-.->"
        out.append(f'  {sid[e["from"]]} {arrow} {sid[e["to"]]}')
    for s, c in STEP_COLORS.items():
        out.append(f"  classDef s{s} fill:{c},stroke:#555,color:#111")
    return "\n".join(out) + "\n"


def page(g):
    # Domains as columns, nodes as stacked boxes, cross-domain links as curves. Plain SVG, no scripts.
    colw, boxw, boxh, gap, top = 210, 190, 46, 14, 70
    W = 40 + len(g["domains"]) * colw
    colx = lambda ci: W - 20 - boxw - ci * colw  # first domain on the right (RTL)
    pos = {}
    for ci, d in enumerate(g["domains"]):
        for ri, n in enumerate(x for x in g["nodes"] if x["domain"] == d["id"]):
            pos[n["id"]] = (colx(ci), top + ri * (boxh + gap))
    H = top + max(sum(1 for n in g["nodes"] if n["domain"] == d["id"]) for d in g["domains"]) * (boxh + gap) + 30
    e = html.escape
    parts = []
    for ed in g["edges"]:
        x1, y1 = pos[ed["from"]]; x2, y2 = pos[ed["to"]]
        if ed["kind"] == "next":
            parts.append(f'<line x1="{x1+boxw/2}" y1="{y1+boxh}" x2="{x2+boxw/2}" y2="{y2}" stroke="#8b91a8" stroke-width="1.5"/>')
        else:
            sx, ex = (x1 + boxw, x2) if x2 > x1 else (x1, x2 + boxw)
            mx = (sx + ex) / 2
            parts.append(f'<path d="M{sx},{y1+boxh/2} C{mx},{y1+boxh/2} {mx},{y2+boxh/2} {ex},{y2+boxh/2}" fill="none" stroke="#5a6bd8" stroke-width="1.2" stroke-dasharray="4 3" opacity=".7"/>')
    for ci, d in enumerate(g["domains"]):
        x = colx(ci)
        score = d.get("score")
        sub = f'{round(score*100)}٪' if score is not None else ""
        heart = " ❤" if d.get("interest", 0) > 0 else ""
        parts.append(f'<text x="{x+boxw}" y="30" text-anchor="start" font-weight="700" font-size="14" fill="#1b1f3b">{e(d["title"])}{heart}</text>')
        parts.append(f'<text x="{x+boxw}" y="50" text-anchor="start" font-size="12" fill="#5b6283">{sub}</text>')
    for n in g["nodes"]:
        x, y = pos[n["id"]]
        s = n.get("step", 0)
        title = (("⭐ " if n["star"] else "") + n["title"])
        short = title if len(title) <= 25 else title[:24] + "…"
        tip = f'{title} · پله {s}' + (f' · {n["date"]}' if n.get("date") else "")
        parts.append(f'<g><title>{e(tip)}</title><rect x="{x}" y="{y}" width="{boxw}" height="{boxh}" rx="9" fill="{STEP_COLORS[s]}" stroke="#4b5070" stroke-width="{2 if n["star"] else 1}"/>'
                     f'<text x="{x+boxw-10}" y="{y+boxh/2+5}" text-anchor="start" font-size="12.5" fill="{"#fff" if s == 3 else "#111"}">{e(short)}</text></g>')
    legend = " · ".join(f'<span style="display:inline-block;width:12px;height:12px;background:{c};border:1px solid #555;border-radius:3px;vertical-align:middle"></span> پلهٔ {s}' for s, c in STEP_COLORS.items())
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Vazirmatn,Tahoma,sans-serif" direction="rtl">{"".join(parts)}</svg>'
    return f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>گراف یادگیری</title><style>body{{margin:0;background:#f5f6fa;color:#1b1f3b;font-family:Vazirmatn,Tahoma,sans-serif}}header{{padding:16px}}.scroll{{overflow:auto;padding:0 16px 24px}}</style></head>
<body><header><h1 style="margin:0 0 6px">گراف یادگیری</h1><div>{legend} · خط ممتد: ترتیب گره‌ها · خط‌چین: ارجاع بین گره‌ها · به‌روزرسانی: {e(g.get("updated",""))}</div></header>
<div class="scroll">{svg}</div></body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", help="private records JSON (framework/records.md)")
    ap.add_argument("--out", help="output directory for the personal graph (keep it out of the repo)")
    a = ap.parse_args()
    g = structure()
    os.makedirs(os.path.join(LEARN, "graph"), exist_ok=True)
    with open(os.path.join(LEARN, "graph", "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    print(f"structure: {len(g['nodes'])} nodes, {len(g['edges'])} edges "
          f"({sum(e['kind']=='link' for e in g['edges'])} cross-links)")
    if a.records:
        out = a.out or "."
        if os.path.abspath(out).startswith(os.path.dirname(LEARN)):
            raise SystemExit("refusing to write personal graph inside the repository; pass --out outside it")
        rec = json.load(open(a.records, encoding="utf-8"))
        g = merge(g, rec)
        os.makedirs(out, exist_ok=True)
        json.dump(g, open(os.path.join(out, "learning-graph.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(os.path.join(out, "learning-graph.mmd"), "w", encoding="utf-8").write(mermaid(g))
        open(os.path.join(out, "learning-graph.html"), "w", encoding="utf-8").write(page(g))
        print("personal graph written to", out)


if __name__ == "__main__":
    main()
