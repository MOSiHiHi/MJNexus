"""Build learning/catalog/search.tsv: links every account to the learning nodes it belongs to.

Two relations:
  cited   - the account is @-mentioned in that node's README (a curated source)
  domain  - the account's classified domain maps to that domain folder (a broad match)
Run after every enrichment or wiki change:  python3 -I learning/tools/build_search.py
"""
import csv, glob, os, re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEARN = os.path.join(REPO, "learning")
DOMAIN_FOLDER = {
    "هوش مصنوعی": "ai", "بازی‌سازی": "gamedev", "ریاضی": "math",
    "فیزیک و نجوم": "physics-astronomy", "برنامه‌نویسی و زیرساخت": "programming-infra",
    "طراحی و تایپوگرافی": "design-typography", "سخت‌افزار، فناوری و حریم خصوصی": "hardware-tech-privacy",
    "کسب‌وکار و بازاریابی": "business-marketing", "یادگیری، زبان و کتاب": "learning-language-books",
    "سرگرمی و رسانهٔ تصویری": "media-entertainment", "تاریخ، اسطوره و رازها": "history-myth",
    "خبر و سیاست": "news-politics", "فعالیت اجتماعی و دین": "society-religion", "سلامت و ورزش": "health-sports",
}

profiles = {r["username"].lower(): r for r in csv.DictReader(open(os.path.join(REPO, "instagram-index/index/profiles.tsv"), encoding="utf-8"), delimiter="\t")}
rows = []

# relation 1: curated citations inside wiki pages (node = folder of README)
for readme in glob.glob(os.path.join(LEARN, "*/*/README.md")) + glob.glob(os.path.join(LEARN, "*/tree.md")):
    node = os.path.relpath(os.path.dirname(readme), LEARN)
    text = open(readme, encoding="utf-8").read()
    for name in sorted(set(m.group(1).lower() for m in re.finditer(r"@([A-Za-z0-9_.]+)", text))):
        if name in profiles:
            p = profiles[name]
            rows.append((node, name, "cited", p["rank"], p["full_name"], p["followers"], p["profile_url"]))

# relation 2: broad domain match from the enriched analysis (only accounts with a classified domain)
enriched = os.path.join(REPO, "instagram-index/analysis/enriched-all.tsv")
if not os.path.exists(enriched):
    enriched = os.path.join(REPO, "instagram-index/analysis/enriched.tsv")
for r in csv.DictReader(open(enriched, encoding="utf-8"), delimiter="\t"):
    primary = r["domains"].split("؛")[0].strip()
    folder = DOMAIN_FOLDER.get(primary)
    if folder:
        rows.append((folder, r["username"].lower(), "domain", r["rank"], r["full_name"], r["followers"], r["profile_url"]))

out = os.path.join(LEARN, "catalog", "search.tsv")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("node\tusername\trelation\trank\tfull_name\tfollowers\tprofile_url\n")
    for row in sorted(set(rows)):
        f.write("\t".join(str(x).replace("\t", " ") for x in row) + "\n")
print(f"wrote {len(set(rows))} links to {os.path.relpath(out, REPO)}")
