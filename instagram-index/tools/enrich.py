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
# domain labels; the owner's three focus domains come first, nothing is excluded
focus = {r["username"]: r for r in csv.DictReader(open("analysis/focus-sample-100.tsv"), delimiter="\t")}
DOMAIN_ORDER = {d: i for i, d in enumerate(["هوش مصنوعی", "بازی‌سازی", "ریاضی", "فیزیک و نجوم", "برنامه‌نویسی و زیرساخت",
    "طراحی و تایپوگرافی", "سخت‌افزار، فناوری و حریم خصوصی", "کسب‌وکار و بازاریابی", "یادگیری، زبان و کتاب",
    "سرگرمی و رسانهٔ تصویری", "تاریخ، اسطوره و رازها", "خبر و سیاست", "فعالیت اجتماعی و دین", "سلامت و ورزش"])}

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
        "domains": focus.get(u, {}).get("domains", "خارج از حوزه"),
        "value": focus.get(u, {}).get("value", ""),
        "level": focus.get(u, {}).get("level", ""),
        "level_evidence": focus.get(u, {}).get("level_evidence", ""),
        # filled only by the owner after real review/use; never guessed
        "my_status": "بررسی‌نشده", "my_rating": "", "my_notes": "", "reviewed_on": "",
    })
# group by the primary (first-listed) domain so each section is contiguous
rows.sort(key=lambda r: (DOMAIN_ORDER.get(r["domains"].split("؛")[0].strip(), 9), int(r["rank"])))

cols = list(rows[0].keys())
with open("analysis/enriched.tsv", "w") as f:
    f.write("\t".join(cols) + "\n")
    for r in rows:
        f.write("\t".join(str(r[c]).replace("\t", " ") for c in cols) + "\n")

md = ["# نمایهٔ تحلیل‌شده", "",
      "«چیست»، «نوع»، «حوزه»، «ارزش» و «سطح» **برداشت مدل** از نام، بیو و دستهٔ پروفایل است و سطح همراه شاهدش آمده؛ "
      "لینک‌ها از خود پروفایل استخراج شده‌اند. ستون‌های «من» (وضعیت، امتیاز، یادداشت) فقط بعد از بررسی و استفادهٔ واقعی "
      "توسط صاحب نمایه پر می‌شوند و در `analysis/enriched.tsv` قابل ویرایش‌اند.", ""]
current = None
for r in rows:
    head = r["domains"].split("؛")[0].strip()
    if head != current:
        current = head
        md += ["", f"## {head}", ""]
        md += ["| # | حساب | چیست | ارزش | سطح (شاهد) | منبع اصلی بیرونی | انواع ارجاع |", "|---|---|---|---|---|---|---|"]
    if True:
        lvl = r["level"] + (f" ({r['level_evidence']})" if r["level_evidence"] else "")
        md.append(f"| {r['rank']} | [{r['username']}]({r['profile_url']}) | {r['what']} | {r['value']} | {lvl} | "
                  f"{r['main_link'] or '—'} | {r['link_types'] or '—'} |")
open("analysis/report.md", "w").write("\n".join(md) + "\n")
print(len(rows), "rows")
