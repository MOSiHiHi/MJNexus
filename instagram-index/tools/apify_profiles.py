"""Fetch public Instagram profiles through an Apify actor (no Instagram login).

Auth: the environment's API credential for api.apify.com (proxy adds the header),
or APIFY_TOKEN if set.

Usage:
  python3 -I apify_profiles.py ACTOR OUTDIR MAX_USD user1 user2 ...
  ACTOR e.g. apify~instagram-profile-scraper or dami_studio~instagram-profile-scraper
  MAX_USD caps what this run may charge.

Writes OUTDIR/raw.jsonl (actor output as-is) and OUTDIR/results.jsonl
(one normalized line per requested username; missing ones marked unavailable).
Usernames already in results.jsonl are skipped, so re-running resumes.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone

actor, outdir, max_usd = sys.argv[1], sys.argv[2], sys.argv[3]
users = sys.argv[4:]
os.makedirs(outdir, exist_ok=True)
res_path = os.path.join(outdir, "results.jsonl")
done = set()
if os.path.exists(res_path):
    done = {json.loads(l)["username"] for l in open(res_path)}
todo = [u for u in users if u.lower() not in done]
if not todo:
    sys.exit("nothing to do")

API = "https://api.apify.com/v2/"
headers = {"Content-Type": "application/json"}
if os.environ.get("APIFY_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["APIFY_TOKEN"]


def api(path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


started = datetime.now(timezone.utc).isoformat(timespec="seconds")
run_id = os.environ.get("APIFY_RUN_ID")  # import an already finished run instead of starting one
if not run_id:
    run_id = api(f"acts/{actor}/runs?maxTotalChargeUsd={max_usd}", {"usernames": todo})["data"]["id"]
    print("run", run_id, flush=True)
while True:
    run = api(f"actor-runs/{run_id}")["data"]
    if run["status"] not in ("READY", "RUNNING"):
        break
    time.sleep(10)
print("status", run["status"], "cost_usd", run.get("usageTotalUsd"), flush=True)
items = api(f"datasets/{run['defaultDatasetId']}/items?clean=true")


def pick(d, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def links(d):
    out = []
    for k in ("externalUrl", "external_url", "website"):
        if d.get(k):
            out.append(d[k])
    for k in ("externalUrls", "bioLinks", "bio_links", "externalLinks"):
        for x in d.get(k) or []:
            u = x.get("url") if isinstance(x, dict) else x
            if u and u not in out:
                out.append(u)
    return out


with open(os.path.join(outdir, "raw.jsonl"), "a") as f:
    for it in items:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")

by_user = {}
for it in items:
    u = (pick(it, "username", "userName") or "").lower()
    if u:
        by_user[u] = it

with open(res_path, "a") as f:
    for u in todo:
        it = by_user.get(u.lower())
        rec = {"username": u.lower(), "profile_url": f"https://www.instagram.com/{u}/",
               "source": f"apify/{actor}", "observed_at": started}
        if not it or it.get("error"):
            rec.update(status="unavailable", error=(it or {}).get("error") or (it or {}).get("errorDescription"))
        else:
            private = pick(it, "private", "isPrivate", "is_private")
            rec.update(
                status="private" if private else "ok",
                full_name=pick(it, "fullName", "full_name", "name"),
                biography=pick(it, "biography", "bio"),
                external_links=links(it),
                followers=pick(it, "followersCount", "followers", "follower_count"),
                following=pick(it, "followsCount", "following", "following_count"),
                posts=pick(it, "postsCount", "posts", "media_count"),
                verified=pick(it, "verified", "isVerified", "is_verified"),
                is_business=pick(it, "isBusinessAccount", "is_business"),
                category=pick(it, "businessCategoryName", "category", "categoryName"),
                profile_pic=pick(it, "profilePicUrlHD", "profilePicUrl", "profile_pic_url"),
            )
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(u, rec["status"], rec.get("followers"), len(rec.get("external_links") or []))
print(f"{len(items)} items returned for {len(todo)} requested")
