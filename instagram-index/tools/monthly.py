"""One monthly step of the free-tier plan: fetch the next batch of ranked profiles
within this cycle's remaining Apify free credit, then rebuild the index and reports.

Usage (from instagram-index/):  python3 -I tools/monthly.py [--dry-run]
Prints a short summary; writes lists/batch-NNN.txt, runs/batch-NNN/, index/profiles.tsv.
"""
import glob, json, os, re, subprocess, sys, urllib.request

PRICE = 0.0026          # apify~instagram-profile-scraper, FREE tier, per profile
BUDGET = 4.5            # keep a buffer under the $5 monthly free credit
ACTOR = "apify~instagram-profile-scraper"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
dry = "--dry-run" in sys.argv

rank = {}
for line in list(open("lists/ranked.tsv"))[1:]:
    r, u, t, _ = line.rstrip("\n").split("\t")
    rank[u] = (int(r), t)


def load_results():
    out = {}
    for f in sorted(glob.glob("runs/*/results.jsonl")):
        if "search-pilot" in f:
            continue
        for l in open(f):
            r = json.loads(l)
            prev = out.get(r["username"])
            # a later full record beats an earlier limited/unavailable one
            if not prev or prev["status"] != "ok":
                out[r["username"]] = r
    return out


def build_outputs(results):
    def c(x):
        return (x or "—").replace("|", "¦").replace("\n", " / ").replace("\t", " ")
    os.makedirs("index", exist_ok=True)
    with open("index/profiles.tsv", "w") as f:
        f.write("rank\ttier\tusername\tstatus\tfull_name\tcategory\tfollowers\tposts\tverified\t"
                "biography\texternal_links\tprofile_url\tobserved_at\tsource\n")
        for u, r in sorted(results.items(), key=lambda kv: rank.get(kv[0], (99999, ""))[0]):
            rk, t = rank.get(u, ("", ""))
            f.write("\t".join(str(v) for v in [
                rk, t, u, r["status"], c(r.get("full_name")), c(r.get("category")), r.get("followers") or "",
                r.get("posts") or "", r.get("verified") or "", c(r.get("biography")),
                " ".join(r.get("external_links") or []), r["profile_url"], r["observed_at"], r["source"]]) + "\n")


def batch_report(n, rows, cost):
    def c(x):
        return (x or "—").replace("|", "¦").replace("\n", " / ")
    rows = sorted(rows, key=lambda x: rank.get(x["username"], (99999,))[0])
    ok = [x for x in rows if x["status"] == "ok"]
    gone = [x["username"] for x in rows if x["status"] == "unavailable"]
    md = [f"# دستهٔ {n} — رتبه {rank[rows[0]['username']][0]} تا {rank[rows[-1]['username']][0]}", "",
          f"منبع: Apify `{ACTOR}`، هزینه {cost:.2f} دلار.", "",
          f"- کامل: **{len(ok)}**", f"- خصوصی: **{sum(1 for x in rows if x['status'] == 'private')}**",
          f"- پیدا نشد: **{len(gone)}** — " + "، ".join(gone), "",
          "| # | حساب | نام | دسته | دنبال‌کننده | بیو | لینک‌های بیرونی |", "|---|---|---|---|---|---|---|"]
    md += [f"| {rank[x['username']][0]} | [{x['username']}]({x['profile_url']}) | {c(x['full_name'])} | "
           f"{c(x['category'])} | {x['followers'] or 0:,} | {c(x['biography'])} | "
           f"{'<br>'.join(x['external_links'][:4]) or '—'} |" for x in ok]
    open(f"runs/batch-{n:03d}/report.md", "w").write("\n".join(md) + "\n")


def apify(path):
    with urllib.request.urlopen("https://api.apify.com/v2/" + path, timeout=60) as r:
        return json.load(r)["data"]


results = load_results()
excluded = {l.split("\t")[0] for l in list(open("lists/excluded_personal.tsv"))[1:]}
remaining = [u for u, _ in sorted(rank.items(), key=lambda kv: kv[1][0])
             if u not in results and u not in excluded]
used = apify("users/me/limits")["current"]["monthlyUsageUsd"]
n_afford = max(0, int((BUDGET - used) / PRICE))
nums = [int(m.group(1)) for f in glob.glob("lists/batch-*.txt") if (m := re.search(r"batch-(\d+)\.txt$", f))]
n = max(nums or [0]) + 1
take = remaining[:n_afford]
print(f"used_this_cycle_usd={used:.2f} affordable={n_afford} remaining={len(remaining)} batch={n} size={len(take)}")
if dry or not take:
    sys.exit(0)

open(f"lists/batch-{n:03d}.txt", "w").write("\n".join(take) + "\n")
cap = round(len(take) * PRICE + 0.05, 2)
subprocess.run([sys.executable, "-I", "tools/apify_profiles.py", ACTOR, f"runs/batch-{n:03d}", str(cap), *take], check=True)
rows = [json.loads(l) for l in open(f"runs/batch-{n:03d}/results.jsonl")]
cost = apify("users/me/limits")["current"]["monthlyUsageUsd"] - used
batch_report(n, rows, cost)
results = load_results()
build_outputs(results)
ok_total = sum(1 for r in results.values() if r["status"] == "ok")
left = len(remaining) - len(take)
print(f"SUMMARY batch={n} requested={len(take)} ok={sum(1 for r in rows if r['status'] == 'ok')} "
      f"private={sum(1 for r in rows if r['status'] == 'private')} "
      f"not_found={sum(1 for r in rows if r['status'] == 'unavailable')} "
      f"limited={sum(1 for r in rows if r['status'] == 'limited')} cost_usd={cost:.2f} "
      f"index_ok_total={ok_total} accounts_left={left}")
