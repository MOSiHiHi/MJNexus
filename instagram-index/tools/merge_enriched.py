"""Merge the 99-account sample and all classified batches into analysis/enriched-all.tsv,
then compare the independent verifier picks against the classifier and write analysis/report-all.md.

Usage (from instagram-index/):  python3 -I tools/merge_enriched.py
Owner-only columns (my_status, my_rating, my_notes, reviewed_on) are written empty / default.
"""
import csv, glob, os, re, collections
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGG = ("linktr.ee", "linkin.bio", "lnk.bio", "bio.site", "sprout.link", "tap.bio", "bio.to", "beacons.ai",
       "hoo.be", "linktw.in", "visitlink.bio", "simplybio.io", "clicklinkin.bio", "i.mtr.bio", "bit.ly",
       "tinyurl.com", "empli.fi", "msha.ke", "taplink.cc")
TYPES = [("یوتیوب", ("youtube.com", "youtu.be")), ("پادکست", ("podcasts.apple", "spotify.com", "castbox", "podtrac", "anchor.fm", "podbean")),
         ("خبرنامه", ("substack.com", "beehiiv", "newsletter", "convertkit")), ("تلگرام", ("t.me", "telegram")),
         ("حمایت/پرداخت", ("patreon.com", "stripe.com", "gumroad", "buymeacoffee", "ko-fi")), ("گیت‌هاب", ("github.com",)),
         ("دیسکورد", ("discord",)), ("جامعه/دوره", ("skool.com", "udemy", "coursera", "maven.com")),
         ("فروشگاه", ("store", "shop", "steampowered", "makeship", "bookshop"))]
DOMAINS = ["هوش مصنوعی", "بازی‌سازی", "ریاضی", "فیزیک و نجوم", "برنامه‌نویسی و زیرساخت", "طراحی و تایپوگرافی",
           "سخت‌افزار، فناوری و حریم خصوصی", "کسب‌وکار و بازاریابی", "یادگیری، زبان و کتاب", "سرگرمی و رسانهٔ تصویری",
           "تاریخ، اسطوره و رازها", "خبر و سیاست", "فعالیت اجتماعی و دین", "سلامت و ورزش",
           "موسیقی و صدا", "هنر تجسمی", "فرهنگ و معنویت"]


def dom(u):
    d = urlparse(u if "://" in u else "http://" + u).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def facts(links):
    ds = [dom(u) for u in links]
    main = next((u for u, d in zip(links, ds) if d and not d.endswith(AGG)), "")
    types = [t for t, keys in TYPES if any(k in d for d in ds for k in keys)]
    if main and not any(k in dom(main) for _, keys in TYPES for k in keys):
        types.insert(0, "وب‌سایت")
    if any(d.endswith(AGG) for d in ds):
        types.append("صفحهٔ لینک‌ها")
    return main, types


LEVELS = {"عمومی", "مبتدی", "متوسط", "حرفه‌ای", "دانشگاهی", "پژوهشی", "نامشخص"}
LEVEL_FIX = {"": "نامشخص", "—": "نامشخص", "-": "نامشخص", "همه سطوح": "عمومی", "مبتدی تا متوسط": "مبتدی",
             "پیشرفته": "حرفه‌ای"}


def norm_level(v):
    v = (v or "").strip()
    v = LEVEL_FIX.get(v, v)
    return v if v in LEVELS else "نامشخص"


def is_fa(t):
    return any("؀" <= c <= "ۿ" for c in t)


prof = {r["username"]: r for r in csv.DictReader(open(f"{BASE}/index/profiles.tsv", encoding="utf-8"), delimiter="\t")}
sample = {r["username"]: r for r in csv.DictReader(open(f"{BASE}/analysis/enriched.tsv", encoding="utf-8"), delimiter="\t")}
cls = {}
for f in sorted(glob.glob(f"{BASE}/analysis/batch-out/*.tsv")):
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
        if r.get("username") and r["username"] in prof:
            cls[r["username"]] = r
ver = {}
for f in sorted(glob.glob(f"{BASE}/analysis/verify-out/*.tsv")):
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"):
        if r.get("username"):
            ver[r["username"]] = r

rows, problems = [], []
for u, p in prof.items():
    if u in sample:
        row = dict(sample[u])
        row["level"] = norm_level(row.get("level"))
        rows.append(row)
        continue
    if u not in cls:
        continue
    c = cls[u]
    primary = c["domains"].split("؛")[0].strip()
    if primary not in DOMAINS:
        problems.append(f"{u}: unknown domain {c['domains']!r}")
    links = p["external_links"].split()
    main, types = facts(links)
    rows.append({
        "rank": p["rank"], "username": u, "profile_url": p["profile_url"], "full_name": p["full_name"],
        "followers": p["followers"], "lang": "فارسی" if is_fa(p["biography"] + p["full_name"]) else "غیرفارسی",
        "what": c["what"], "kind": c["kind"], "topics": "", "main_link": main, "link_types": "، ".join(types),
        "all_links": " ".join(links), "biography": p["biography"], "observed_at": p["observed_at"],
        "domains": c["domains"], "value": c["value"], "level": norm_level(c["level"]), "level_evidence": c["level_evidence"],
        "my_status": "بررسی‌نشده", "my_rating": "", "my_notes": "", "reviewed_on": "",
    })
import csv as _csv
ov_path = f"{BASE}/analysis/overrides.tsv"
if os.path.exists(ov_path):
    ov = {r["username"]: r["domains"] for r in _csv.DictReader(open(ov_path, encoding="utf-8"), delimiter="\t")}
    for r in rows:
        if r["username"] in ov:
            r["domains"] = ov[r["username"]]
    missing = set(ov) - {r["username"] for r in rows}
    if missing:
        problems.append(f"overrides for unknown accounts: {sorted(missing)}")
rows.sort(key=lambda r: int(r["rank"]) if str(r["rank"]).isdigit() else 10**9)
cols = list(rows[0].keys())
with open(f"{BASE}/analysis/enriched-all.tsv", "w", encoding="utf-8") as f:
    f.write("\t".join(cols) + "\n")
    for r in rows:
        f.write("\t".join(str(r[c]).replace("\t", " ").replace("\n", " ") for c in cols) + "\n")

# verifier agreement (only on the classified batch rows, not the 99-sample)
agree, total, dis = 0, 0, []
for u, v in ver.items():
    if u in cls:
        total += 1
        a = cls[u]["domains"].split("؛")[0].strip()
        b = v["domain"].split("؛")[0].strip()
        if a == b:
            agree += 1
        else:
            dis.append((u, a, b))
per_dom = collections.Counter(r["domains"].split("؛")[0].strip() for r in rows)
per_value = collections.Counter(r["value"] for r in rows)
per_level = collections.Counter(r["level"] for r in rows)

md = ["# گزارش نهایی: همهٔ حساب‌های برچسب‌خورده", "",
      f"- کل حساب‌های برچسب‌خورده: **{len(rows)}** (شامل نمونهٔ ۹۹تایی)",
      f"- حساب‌های بدون برچسب: **{len(prof) - len(rows)}**",
      f"- تأیید مستقل (۱۰٪): **{agree} از {total}** هم‌نظر ({(100*agree/total if total else 0):.0f}٪)"
      + (f"؛ اختلاف‌ها: {len(dis)}" if total else ""), "",
      "## توزیع حوزه (حوزهٔ اصلی)", "", "| حوزه | تعداد |", "|---|---|"]
md += [f"| {d} | {per_dom.get(d, 0)} |" for d in DOMAINS]
md += ["", "## ارزش", "", "| ارزش | تعداد |", "|---|---|"] + [f"| {k} | {v} |" for k, v in per_value.most_common()]
md += ["", "## سطح (برداشت مدل با شاهد)", "", "| سطح | تعداد |", "|---|---|"] + [f"| {k} | {v} |" for k, v in per_level.most_common()]
md += ["", "## اختلاف‌های تأیید (برای بررسی صاحب نمایه)", ""]
md += [f"- @{u}: طبقه‌بند «{a}» در برابر تأیید‌کننده «{b}»" for u, a, b in dis] or ["- بدون اختلاف"]
if problems:
    md += ["", "## مشکلات داده", ""] + [f"- {p}" for p in problems]
open(f"{BASE}/analysis/report-all.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
print(f"rows={len(rows)} classified={len(cls)} verified={total} agree={agree} disagree={len(dis)} problems={len(problems)}")
