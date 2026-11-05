"""Small, step-by-step probe of public Instagram profiles (no login).

Usage: python3 -I probe.py MODE OUTDIR DELAY_SEC user1 user2 ...
MODE: http (plain page fetch) | browser (headless Chromium + screenshot)
Stops at the first sign of login wall, challenge or rate limit.
Every result is appended to OUTDIR/results.jsonl as soon as it is known.
"""
import html, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

mode, outdir, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
users = sys.argv[4:]
os.makedirs(outdir, exist_ok=True)
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
STOP = {"login_wall", "challenge", "rate_limited", "network_blocked"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def meta(page_html, prop):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), page_html)
    return html.unescape(m.group(1)) if m else None


def classify(url, text):
    low = text.lower()
    if "/accounts/login" in url:
        return "login_wall"
    if "/challenge" in url or "captcha" in low:
        return "challenge"
    if "please wait a few minutes" in low:
        return "rate_limited"
    if "this account is private" in low:
        return "private"
    if "sorry, this page isn't available" in low:
        return "not_found"
    return "ok"


def parse(page_html):
    desc = meta(page_html, "og:description") or meta(page_html, "description")
    rec = {"og_title": meta(page_html, "og:title"), "og_description": desc}
    if desc:
        m = re.match(r"\s*([\d.,KMkm]+) Followers, ([\d.,KMkm]+) Following, ([\d.,KMkm]+) Posts", desc)
        if m:
            rec.update(followers=m.group(1), following=m.group(2), posts=m.group(3))
    rec["post_links"] = sorted(set(re.findall(r'href="(/(?:[\w.]+/)?(?:p|reel)/[\w-]+/)"', page_html)))
    return rec


def http_probe(u):
    url = f"https://www.instagram.com/{u}/"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            return {"http_status": r.status, "final_url": r.url, "status": classify(r.url, body), **parse(body)}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "status": "rate_limited" if e.code == 429 else f"http_{e.code}"}
    except Exception as e:  # proxy denial etc.
        return {"status": "network_blocked", "error": str(e)[:200]}


def browser_probe(u, page):
    url = f"https://www.instagram.com/{u}/"
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
    except Exception as e:
        return {"status": "network_blocked", "error": str(e)[:200]}
    body = page.content()
    visible = page.inner_text("body")[:4000]
    shot = os.path.join(outdir, f"{u}.png")
    page.screenshot(path=shot)
    links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    rec = {"http_status": resp.status if resp else None, "final_url": page.url,
           "status": classify(page.url, visible), "screenshot": shot,
           "external_links": sorted({l for l in links if "instagram.com" not in l}),
           "visible_text": visible, **parse(body)}
    rec["post_links"] = sorted({l for l in links if re.search(r"/(p|reel)/", l)}) or rec["post_links"]
    return rec


def main():
    pw = browser = page = None
    if mode == "browser":
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page(user_agent=UA, viewport={"width": 1280, "height": 1600}, locale="en-US")
    try:
        for i, u in enumerate(users):
            if i:
                time.sleep(delay)
            t0 = now()
            rec = http_probe(u) if mode == "http" else browser_probe(u, page)
            rec = {"username": u, "mode": mode, "observed_at": t0, **rec}
            with open(os.path.join(outdir, "results.jsonl"), "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(u, rec["status"], rec.get("followers"), len(rec.get("post_links") or []), flush=True)
            if rec["status"] in STOP:
                print("STOP:", rec["status"], flush=True)
                break
    finally:
        if browser:
            browser.close()
            pw.stop()


main()
