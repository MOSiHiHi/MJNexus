#!/usr/bin/env python3
"""Media layer for saved reels and image posts: fetch, download, transcribe, keyframes, contact sheets.

Steps
  fetch    Apify official scrapers (one run, capped cost): reel scraper for reels, post scraper for posts.
           Minimal metadata + direct media URLs; media is downloaded right away (CDN links expire within hours)
           into MEDIA (outside the repo). Items are taken in priority order: low evidence first.
  prepare  Reels and video posts: local Whisper transcript + keyframe contact sheet.
           Image posts and carousels: a contact sheet of the images (no transcript).
           Writes knowledge/data/video/todo.tsv for the extraction step.
  status   Counts per stage and kind.

Extraction (reading sheet + transcript + caption and writing knowledge/data/video/<id>.json)
is done by Claude in a session or routine; see .claude/skills/tool-radar/SKILL.md.

Auth: the environment's Apify credential is attached by the proxy, or APIFY_TOKEN if set.
Usage:
  python3 -I knowledge/tools/video_pipeline.py fetch --kind reel --limit 50 --max-usd 0.25
  python3 -I knowledge/tools/video_pipeline.py fetch --kind post --limit 50 --max-usd 0.25
  python3 -I knowledge/tools/video_pipeline.py prepare --limit 50
  python3 -I knowledge/tools/video_pipeline.py status
"""
import argparse, csv, glob, json, os, sqlite3, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPORT = os.path.join(ROOT, "learning", "sources", "instagram-export")
VIDEO = os.path.join(ROOT, "knowledge", "data", "video")
META = os.path.join(VIDEO, "meta")
MEDIA = os.environ.get("KG_MEDIA", os.path.expanduser("~/kg-media"))
WHISPER_PY = os.environ.get("WHISPER_PY", os.path.expanduser("~/.whisper-venv/bin/python"))
ACTORS = {"reel": "apify~instagram-reel-scraper", "post": "apify~instagram-post-scraper"}
PRICE = {"reel": 0.0026, "post": 0.0017}  # free-plan price per result event; each run also has a small start fee
START_FEE = 0.005
DB = os.path.join(ROOT, "knowledge", "kg.sqlite")
INFO_ORDER = {"low": 0, "": 1, "medium": 2, "high": 3}  # process the items the caption explains least first

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


def kind_of(url):
    return "reel" if "/reel/" in url else "post" if "/p/" in url else ""


def saves(kind="all", max_info="high"):
    """Saved reels and posts in priority order: low evidence first, then newest first.
    max_info drops items whose caption already explains them better than this level."""
    rows = [r for r in csv.DictReader(open(os.path.join(EXPORT, "table.tsv"), encoding="utf-8"), delimiter="\t")
            if kind_of(r["url"]) and kind in ("all", kind_of(r["url"]))]
    info = {}
    if os.path.exists(DB):
        info = dict(sqlite3.connect(DB).execute("SELECT id, coalesce(info_level, '') FROM item").fetchall())
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: INFO_ORDER.get(info.get(r["id"], ""), 1))
    return [r for r in rows if INFO_ORDER.get(info.get(r["id"], ""), 1) <= INFO_ORDER[max_info]]


def reels():
    return saves("reel")


def shortcode(url):
    return url.rstrip("/").split("/")[-1]


def stage(item_id):
    if os.path.exists(os.path.join(VIDEO, f"{item_id}.json")):
        return "extracted"
    d = os.path.join(MEDIA, item_id)
    has_video = os.path.exists(os.path.join(d, "video.mp4"))
    if os.path.exists(os.path.join(d, "sheet.jpg")) and (os.path.exists(os.path.join(d, "transcript.json")) or not has_video):
        return "prepared"
    if has_video or glob.glob(os.path.join(d, "img_*.jpg")):
        return "downloaded"
    if os.path.exists(os.path.join(META, f"{item_id}.json")):
        return "fetched"
    return "new"


def download(url, path, min_bytes=10000):
    r = subprocess.run(["curl", "-sS", "-L", "-m", "180", "-o", path, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    ok = r.stdout.strip() == "200" and os.path.exists(path) and os.path.getsize(path) > min_bytes
    if not ok and os.path.exists(path):
        os.remove(path)
    return ok


def cmd_fetch(a):
    os.makedirs(META, exist_ok=True)
    wanted = ("new", "fetched") if a.retry_fetched else ("new",)  # 'fetched' = metadata but the media download failed
    todo = [r for r in saves(a.kind, a.max_info) if stage(r["id"]) in wanted][: a.limit]
    if not todo:
        print("nothing to fetch")
        return
    est = len(todo) * PRICE[a.kind] + START_FEE
    if est > a.max_usd:
        sys.exit(f"estimated ${est:.3f} for {len(todo)} {a.kind}s exceeds --max-usd {a.max_usd}; lower --limit")
    by_code = {shortcode(r["url"]): r for r in todo}
    run_id = os.environ.get("APIFY_RUN_ID")
    if not run_id:
        body = {"username": [r["url"] for r in todo], "resultsLimit": 1}
        run_id = api(f"acts/{ACTORS[a.kind]}/runs?maxTotalChargeUsd={a.max_usd}", body)["data"]["id"]
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
        code = it.get("shortCode") or shortcode(it.get("inputUrl", "") or it.get("url", ""))
        row = by_code.get(code)
        if not row:
            continue
        meta = {k: it.get(k) for k in ("shortCode", "ownerUsername", "timestamp", "videoDuration", "caption", "type",
                                       "hashtags", "mentions", "likesCount", "commentsCount", "videoPlayCount", "alt")}
        # comment text is written by third parties: keep only the count (public repository)
        meta["item_id"], meta["url"], meta["run_id"], meta["kind"] = row["id"], row["url"], run_id, a.kind
        json.dump(meta, open(os.path.join(META, f"{row['id']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        d = os.path.join(MEDIA, row["id"])
        os.makedirs(d, exist_ok=True)
        got_media = []
        if it.get("videoUrl") and download(it["videoUrl"], os.path.join(d, "video.mp4")):
            got_media.append("video")
            if it.get("audioUrl"):
                download(it["audioUrl"], os.path.join(d, "audio.m4a"))
        # images: carousel children first, else the post's own image(s)
        urls = [c.get("displayUrl") for c in (it.get("childPosts") or []) if c.get("displayUrl") and not c.get("videoUrl")]
        urls = urls or [u for u in (it.get("images") or []) if isinstance(u, str)] or ([it["displayUrl"]] if it.get("displayUrl") and not it.get("videoUrl") else [])
        for n, u in enumerate(urls[:12], 1):
            if download(u, os.path.join(d, f"img_{n:02d}.jpg"), min_bytes=2000):
                got_media.append(f"img{n}")
        got += 1
        print(row["id"], code, " ".join(got_media) or "NO MEDIA", flush=True)
    print(f"fetched {got} of {len(todo)}")


def cmd_prepare(a):
    todo = [r for r in saves() if stage(r["id"]) == "downloaded"][: a.limit]
    lines = []
    for r in todo:
        d = os.path.join(MEDIA, r["id"])
        if not os.path.exists(os.path.join(d, "video.mp4")):  # image post or carousel: one sheet of its images
            imgs = sorted(glob.glob(os.path.join(d, "img_*.jpg")))
            cols = 1 if len(imgs) == 1 else 2 if len(imgs) <= 4 else 3
            rows_n = -(-len(imgs) // cols)
            inputs = sum((["-i", p] for p in imgs), [])
            filt = "".join(f"[{i}:v]scale=w=540:h=676:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                           f"pad=540:676:-1:-1:color=white,format=yuvj420p[v{i}];" for i in range(len(imgs)))
            if len(imgs) == 1:
                filt += "[v0]copy[out]"
            else:
                layout = "|".join(f"{(i % cols) * 546}_{(i // cols) * 682}" for i in range(len(imgs)))
                filt += "".join(f"[v{i}]" for i in range(len(imgs))) + f"xstack=inputs={len(imgs)}:layout={layout}:fill=white[out]"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[out]", "-frames:v", "1",
                            os.path.join(d, "sheet.jpg")])
            if os.path.exists(os.path.join(d, "sheet.jpg")):
                lines.append([r["id"], r["url"], os.path.join(d, "sheet.jpg"), ""])
                print(r["id"], "prepared (images:", len(imgs), ")", flush=True)
            continue
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
    for kind in ("reel", "post"):
        c = {}
        for r in saves(kind):
            s = stage(r["id"])
            c[s] = c.get(s, 0) + 1
        print(f"{kind}s:", sum(c.values()), c)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--kind", choices=["reel", "post"], default="reel")
    f.add_argument("--max-info", choices=["low", "medium", "high"], default="high",
                   help="only items whose caption evidence is at most this level")
    f.add_argument("--retry-fetched", action="store_true", help="also retry items whose media download failed earlier")
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
