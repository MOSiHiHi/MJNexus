"""Join model labels with observed profile data and derive link facts automatically.

Usage (from instagram-index/):  python3 -I tools/enrich.py analysis/labels-*.tsv
Writes analysis/enriched.tsv and analysis/report.md (labelled profiles only).
Observed columns come from index/profiles.tsv; `what/kind/topics` are model
inferences from the bio, name and category, and are marked as such.
"""
import csv, sys
from urllib.parse import urlparse

AGGREGATORS = ("linktr.ee", "linkin.bio", "lnk.bio", "bio.site", "sprout.link", "tap.bio", "bio.to",
               "beacons.ai", "hoo.be", "linktw.in", "visitlink.bio", "simplybio.io", "clicklinkin.bio",
               "i.mtr.bio", "bit.ly", "tinyurl.com", "empli.fi", "linkin.bio", "msha.ke", "taplink.cc")
TYPES = [  # (label, domain substrings)
    ("یوتیوب", ("youtube.com", "youtu.be")),
    ("پادکست", ("podcasts.apple", "spotify.com", "castbox", "podtrac", "anchor.fm", "podbean")),
    ("خبرنامه", ("substack.com", "beehiiv", "newsletter", "convertkit")),
    ("تلگرام", ("t.me", "telegram")),
    ("حمایت/پرداخت", ("patreon.com", "stripe.com", "gumroad", "buymeacoffee", "ko-fi", "zarinp")),
    ("گیت‌هاب", ("github.com",)),
    ("دیسکورد", ("discord",)),
    ("جامعه/دوره", ("skool.com", "udemy", "coursera", "maven.com")),
    ("فروشگاه", ("store", "shop", "steampowered", "makeship", "bookshop")),
]


def dom(u):
    d = urlparse(u if "://" in u else "http://" + u).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def facts(links):
    ds = [dom(u) for u in links]
    main = next((u for u, d in zip(links, ds) if d and not d.endswith(AGGREGATORS)), "")
    types = [t for t, keys in TYPES if any(k in d for d in ds for k in keys)]
    if main and not any(k in dom(main) for _, keys in TYPES for k in keys):
        types.insert(0, "وب‌سایت")
    if any(d.endswith(AGGREGATORS) for d in ds):
        types.append("صفحهٔ لینک‌ها")
    return main, types


def is_fa(text):
    return any("؀" <= ch <= "ۿ" for ch in text)


labels = {}
for path in sys.argv[1:]:
    for r in csv.DictReader(open(path), delimiter="\t"):
        labels[r["username"]] = r
prof = {r["username"]: r for r in csv.DictReader(open("index/profiles.tsv"), delimiter="\t")}

rows = []
for u, lab in labels.items():
    p = prof[u]
    links = p["external_links"].split()
    main, types = facts(links)
    rows.append({
        "rank": p["rank"], "username": u, "profile_url": p["profile_url"], "full_name": p["full_name"],
        "followers": p["followers"], "lang": "فارسی" if is_fa(p["biography"] + p["full_name"]) else "غیرفارسی",
        "what": lab["what"], "kind": lab["kind"], "topics": lab["topics"],
        "main_link": main, "link_types": "، ".join(types), "all_links": " ".join(links),
        "biography": p["biography"], "observed_at": p["observed_at"],
    })
rows.sort(key=lambda r: int(r["rank"]))

cols = list(rows[0].keys())
with open("analysis/enriched.tsv", "w") as f:
    f.write("\t".join(cols) + "\n")
    for r in rows:
        f.write("\t".join(str(r[c]).replace("\t", " ") for c in cols) + "\n")

md = ["# نمایهٔ تحلیل‌شده", "",
      "ستون‌های «چیست»، «نوع» و «موضوع» **برداشت مدل** از نام، بیو و دستهٔ پروفایل است؛ "
      "بقیه مشاهده‌شده یا از لینک‌ها استخراج شده‌اند.", "",
      "| # | حساب | چیست | نوع | موضوع | منبع اصلی بیرونی | انواع ارجاع |", "|---|---|---|---|---|---|---|"]
for r in rows:
    md.append(f"| {r['rank']} | [{r['username']}]({r['profile_url']}) | {r['what']} | {r['kind']} | {r['topics']} | "
              f"{r['main_link'] or '—'} | {r['link_types'] or '—'} |")
open("analysis/report.md", "w").write("\n".join(md) + "\n")
print(len(rows), "rows")
