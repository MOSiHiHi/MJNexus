"""Collect public profile data via the official Instagram Graph API (Business Discovery).

Only Business/Creator public accounts are returned; personal or private accounts
come back as `unavailable` and are skipped.

Env:  IG_ACCESS_TOKEN  (required, from environment secrets; never printed)
      IG_USER_ID       (your professional account's IG user id; `whoami` prints it)
      IG_API_VERSION   (default v23.0)

Usage:
  python3 -I discover.py whoami
  python3 -I discover.py run OUTDIR DELAY_SEC MEDIA_PER_ACCOUNT user1 user2 ...
Results are appended to OUTDIR/results.jsonl; usernames already there are skipped,
so a stopped run can be resumed with the same command.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
VER = os.environ.get("IG_API_VERSION", "v23.0")
BASE = f"https://graph.facebook.com/{VER}/"
RATE_CODES = {4, 17, 32, 613, 80002}
PROFILE = "username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"
MEDIA = "caption,permalink,timestamp,media_type,like_count,comments_count"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def call(path, params):
    q = urllib.parse.urlencode({**params, "access_token": TOKEN})
    try:
        with urllib.request.urlopen(BASE + path + "?" + q, timeout=60) as r:
            return json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e), dict(e.headers)
        except Exception:
            return {"error": {"code": e.code, "message": f"HTTP {e.code}"}}, dict(e.headers)


def usage(headers):
    """Highest usage percentage Meta reports in its rate-limit headers."""
    top = 0
    for k in ("x-app-usage", "x-business-use-case-usage"):
        v = next((headers[h] for h in headers if h.lower() == k), None)
        if not v:
            continue
        def walk(o):
            nonlocal top
            if isinstance(o, dict):
                for kk, vv in o.items():
                    if kk in ("call_count", "total_cputime", "total_time") and isinstance(vv, (int, float)):
                        top = max(top, vv)
                    else:
                        walk(vv)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(json.loads(v))
    return top


def whoami():
    data, _ = call("me/accounts", {"fields": "name,instagram_business_account{id,username}"})
    print(json.dumps(data.get("data", data), ensure_ascii=False, indent=2))


def run(outdir, delay, n_media, users):
    uid = os.environ["IG_USER_ID"]
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "results.jsonl")
    done = set()
    if os.path.exists(out):
        done = {json.loads(l)["username"] for l in open(out)}
    todo = [u for u in users if u not in done]
    print(f"{len(done)} already saved, {len(todo)} to do", flush=True)
    fields = PROFILE + (f",media.limit({n_media}){{{MEDIA}}}" if n_media else "")
    for i, u in enumerate(todo):
        if i:
            time.sleep(delay)
        data, headers = call(uid, {"fields": f"business_discovery.username({u}){{{fields}}}"})
        rec = {"username": u, "observed_at": now(), "source": f"graph-api/{VER}/business_discovery"}
        err = data.get("error")
        if err:
            code = err.get("code")
            if code in RATE_CODES:
                print(f"STOP: rate limit (code {code}) at {u}", flush=True)
                return
            if code == 190:
                print("STOP: access token invalid or expired", flush=True)
                return
            rec.update(status="unavailable", error_code=code, error_subcode=err.get("error_subcode"),
                       error=err.get("message", "")[:200])
        else:
            bd = data.get("business_discovery", {})
            media = (bd.pop("media", None) or {}).get("data", [])
            rec.update(status="ok", profile_url=f"https://www.instagram.com/{u}/", **bd, media=media)
        with open(out, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        pct = usage(headers)
        print(u, rec["status"], rec.get("followers_count"), len(rec.get("media") or []), f"usage={pct}%", flush=True)
        if pct >= 75:
            print(f"STOP: API usage at {pct}%; resume later with the same command", flush=True)
            return


if not TOKEN:
    sys.exit("IG_ACCESS_TOKEN is not set (add it in the environment's secrets/variables)")
if sys.argv[1] == "whoami":
    whoami()
else:
    run(sys.argv[2], float(sys.argv[3]), int(sys.argv[4]), sys.argv[5:])
