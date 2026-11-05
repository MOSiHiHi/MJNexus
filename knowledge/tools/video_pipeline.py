#!/usr/bin/env python3
"""Video layer for saved reels: fetch, download, transcribe, keyframes.

Steps
  fetch    Apify official reel scraper (one run, capped cost) -> minimal metadata + direct video/audio URLs.
           Media is downloaded right away (CDN links expire within hours) into MEDIA (outside the repo).
  prepare  For downloaded reels: local Whisper transcript + keyframe contact sheet.
           Writes knowledge/data/video/todo.tsv for the extraction step.
  status   Counts per stage.

Extraction (reading sheet + transcript + caption and writing knowledge/data/video/<id>.json)
is done by Claude in a session or routine; see .claude/skills/tool-radar/SKILL.md.

Auth: the environment's Apify credential is attached by the proxy, or APIFY_TOKEN if set.
Usage:
  python3 -I knowledge/tools/video_pipeline.py fetch --limit 50 --max-usd 0.25
  python3 -I knowledge/tools/video_pipeline.py prepare --limit 50
  python3 -I knowledge/tools/video_pipeline.py status
"""
import argparse, csv, json, os, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPORT = os.path.join(ROOT, "learning", "sources", "instagram-export")
VIDEO = os.path.join(ROOT, "knowledge", "data", "video")
META = os.path.join(VIDEO, "meta")
MEDIA = os.environ.get("KG_MEDIA", os.path.expanduser("~/kg-media"))
WHISPER_PY = os.environ.get("WHISPER_PY", os.path.expanduser("~/.whisper-venv/bin/python"))
ACTOR = "apify~instagram-reel-scraper"
PRICE_PER_REEL = 0.0026  # free-plan price of the base 'reel' event; actor start adds ~0.001 per run

API = "https://api.apify.com/v2/"
HEADERS = {"Content-Type": "application/json"}
if os.environ.get("APIFY_TOKEN"):
    HEADERS["Authorization"] = "Bearer " + os.environ["APIFY_TOKEN"]


def api(path, body=None, tries=6):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, HEADERS)
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            transient = not isinstance(e, urllib.error.HTTPError) or e.code in (429, 500, 502, 503, 504)
            if not transient or body is not None or i == tries - 1:  # never retry the paid run start
                raise
            time.sleep(15 * (i + 1))


def reels():
    rows = csv.DictReader(open(os.path.join(EXPORT, "table.tsv"), encoding="utf-8"), delimiter="\t")
    return [r for r in rows if "/reel/" in r["url"]]


def shortcode(url):
    return url.rstrip("/").split("/")[-1]


def stage(item_id):
    if os.path.exists(os.path.join(VIDEO, f"{item_id}.json")):
        return "extracted"
    d = os.path.join(MEDIA, item_id)
    if os.path.exists(os.path.join(d, "sheet.jpg")) and os.path.exists(os.path.join(d, "transcript.json")):
        return "prepared"
    if os.path.exists(os.path.join(d, "video.mp4")):
        return "downloaded"
    if os.path.exists(os.path.join(META, f"{item_id}.json")):
        return "fetched"
    return "new"


def download(url, path):
    r = subprocess.run(["curl", "-sS", "-L", "-m", "180", "-o", path, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    return r.stdout.strip() == "200" and os.path.getsize(path) > 10000


def cmd_fetch(a):
    os.makedirs(META, exist_ok=True)
    todo = [r for r in reels() if stage(r["id"]) == "new"][: a.limit]
    if not todo:
        print("nothing to fetch")
        return
    est = len(todo) * PRICE_PER_REEL + 0.001
    if est > a.max_usd:
        sys.exit(f"estimated ${est:.3f} for {len(todo)} reels exceeds --max-usd {a.max_usd}; lower --limit")
    by_code = {shortcode(r["url"]): r for r in todo}
    run_id = os.environ.get("APIFY_RUN_ID")
    if not run_id:
        body = {"username": [r["url"] for r in todo], "resultsLimit": 1}
        run_id = api(f"acts/{ACTOR}/runs?maxTotalChargeUsd={a.max_usd}", body)["data"]["id"]
        print("run", run_id, flush=True)
    while True:
        run = api(f"actor-runs/{run_id}")["data"]
        if run["status"] not in ("READY", "RUNNING"):
            break
        time.sleep(10)
    print("status", run["status"], "cost_usd", run.get("usageTotalUsd"), flush=True)
    items = api(f"datasets/{run['defaultDatasetId']}/items?clean=true")
    got = 0
    for it in items:
        code = it.get("shortCode") or shortcode(it.get("inputUrl", ""))
        row = by_code.get(code)
        if not row:
            continue
        meta = {k: it.get(k) for k in ("shortCode", "ownerUsername", "timestamp", "videoDuration", "caption",
                                       "hashtags", "mentions", "likesCount", "commentsCount", "videoPlayCount")}
        meta["firstComment"] = it.get("firstComment")
        meta["item_id"], meta["url"], meta["run_id"] = row["id"], row["url"], run_id
        json.dump(meta, open(os.path.join(META, f"{row['id']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        d = os.path.join(MEDIA, row["id"])
        os.makedirs(d, exist_ok=True)
        ok_v = it.get("videoUrl") and download(it["videoUrl"], os.path.join(d, "video.mp4"))
        if it.get("audioUrl"):
            download(it["audioUrl"], os.path.join(d, "audio.m4a"))
        got += 1
        print(row["id"], code, "video" if ok_v else "NO VIDEO", flush=True)
    print(f"fetched {got} of {len(todo)}")


def cmd_prepare(a):
    todo = [r for r in reels() if stage(r["id"]) == "downloaded"][: a.limit]
    lines = []
    for r in todo:
        d = os.path.join(MEDIA, r["id"])
        audio = os.path.join(d, "audio.m4a") if os.path.exists(os.path.join(d, "audio.m4a")) else os.path.join(d, "video.mp4")
        t = subprocess.run([WHISPER_PY, "-I", os.path.join(ROOT, "knowledge", "tools", "transcribe.py"), audio,
                            os.path.join(d, "transcript.json"), a.model], capture_output=True, text=True)
        if t.returncode != 0:
            print(r["id"], "transcribe failed:", t.stderr.strip()[-200:])
            continue
        frames = os.path.join(d, "frames")
        os.makedirs(frames, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, "video.mp4"),
                        "-vf", "select='gt(scene,0.25)',scale=540:-2", "-vsync", "vfr", "-frames:v", "12",
                        os.path.join(frames, "s_%02d.jpg")])
        n = len([f for f in os.listdir(frames) if f.startswith("s_")])
        if n < 4:  # little motion: fall back to one frame every 4 seconds
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, "video.mp4"),
                            "-vf", "fps=1/4,scale=540:-2", "-frames:v", "12", os.path.join(frames, "s_%02d.jpg")])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(frames, "s_%02d.jpg"),
                        "-vf", "tile=4x3:padding=6:color=white", "-frames:v", "1", os.path.join(d, "sheet.jpg")])
        lines.append([r["id"], r["url"], os.path.join(d, "sheet.jpg"), os.path.join(d, "transcript.json")])
        print(r["id"], "prepared", flush=True)
    path = os.path.join(VIDEO, "todo.tsv")
    old = []
    if os.path.exists(path):
        old = [l.rstrip("\n").split("\t") for l in open(path, encoding="utf-8")][1:]
    keep = {l[0]: l for l in old + lines if stage(l[0]) != "extracted"}
    with open(path, "w", encoding="utf-8") as f:
        f.write("item_id\turl\tsheet\ttranscript\n")
        for l in keep.values():
            f.write("\t".join(l) + "\n")
    print(f"prepared {len(lines)}; waiting for extraction: {len(keep)}")


def cmd_status(_):
    c = {}
    for r in reels():
        s = stage(r["id"])
        c[s] = c.get(s, 0) + 1
    print("reels:", sum(c.values()), c)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=50)
    f.add_argument("--max-usd", type=float, default=0.25)
    f.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("prepare")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--model", default="small")
    p.set_defaults(fn=cmd_prepare)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
