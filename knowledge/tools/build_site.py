#!/usr/bin/env python3
"""Build the static radar site in site/ from the dashboard page and its datasets.

The page body is knowledge/dashboard/index.html (the same file the claude.ai dashboard runs);
site/assets/dash-lite.js stands in for the dashboard runtime. Run export_dashboard.py first.

Output: site/index.html and site/data/*.json. Serve locally with:
  python3 -m http.server -d site 8000
Usage: python3 -I knowledge/tools/build_site.py
"""
import datetime, html, json, os, shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGE = os.path.join(ROOT, "knowledge", "dashboard", "index.html")
DATA = os.path.join(ROOT, "knowledge", "data", "dashboard")
SITE = os.path.join(ROOT, "site")
REPO = "https://github.com/MOSiHiHi/MJNexus"
DATASETS = ["kpis", "categories", "licenses", "info_levels", "resource_items", "items",
            "graph_nodes", "graph_edges", "ontology_nodes", "ontology_edges"]

SHELL = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>رادار ابزار و مخزن دانش · MJNexus</title>
<meta name="description" content="Tool radar and knowledge graph built from {items} saved Instagram posts: {resources} tools, repos, models and resources, linked to their accounts, official sites and Wikipedia.">
<meta name="dash-data" content="data/">
<link rel="stylesheet" href="assets/theme.css">
<script src="assets/vendor/d3-7.9.0.min.js"></script>
<script src="assets/dash-lite.js"></script>
</head>
<body>
<header class="site-head">
  <strong>MJNexus · رادار ابزار و مخزن دانش</strong>
  <span>{items} ذخیره · {resources} منبع · به‌روزرسانی {generated}</span>
  <span class="grow"></span>
  <a href="{repo}">کد و داده در GitHub</a>
  <a href="{repo}/blob/Hyp/knowledge/README.md">روش ساخت</a>
  <a href="{repo}/blob/Hyp/docs/radar-research.md">مقایسه با رادارهای دیگر</a>
</header>
{page}
</body>
</html>
"""


def main():
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    for name in DATASETS:
        shutil.copyfile(os.path.join(DATA, f"{name}.json"), os.path.join(SITE, "data", f"{name}.json"))
    kpis = json.load(open(os.path.join(DATA, "kpis.json"), encoding="utf-8"))[0]
    page = open(PAGE, encoding="utf-8").read()
    out = SHELL.format(items=f"{kpis['items']:,}", resources=f"{kpis['resources']:,}",
                       generated=html.escape(kpis.get("generated") or datetime.date.today().isoformat()),
                       repo=REPO, page=page)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(out)
    size = sum(os.path.getsize(os.path.join(SITE, "data", f)) for f in os.listdir(os.path.join(SITE, "data")))
    print("site/index.html written;", len(DATASETS), "datasets,", size // 1024, "KB")


if __name__ == "__main__":
    main()
