"""Check the external sources marked † in the wiki pages and record the result.

Usage (repo root):  python3 -I learning/tools/check_links.py
Writes learning/catalog/links.tsv: url, result, http_code, checked_at, where.
Results: ok (2xx/3xx), client-error (4xx), server-error (5xx), blocked (proxy refused), unreachable (other).
Blocked means the egress policy refused the host; it is reported, not bypassed.
"""
import glob, os, re, subprocess, sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEARN = os.path.join(REPO, "learning")
DOMAIN = re.compile(r"(?<![@\w])((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s)\]`,;]*)?", re.I)
EXCLUDE_HOSTS = {"numpy.linalg"}  # Python module names, not web sources


def targets():
    seen = {}
    for p in glob.glob(os.path.join(LEARN, "*/*/README.md")):
        for line in open(p, encoding="utf-8"):
            if "†" not in line:
                continue
            # only the part before the dagger is the source text
            for m in DOMAIN.finditer(line.split("†")[0]):
                host, path = m.group(1).lower(), m.group(2) or ""
                if host.endswith((".md", ".py", ".tsv")) or host in ("e.g", "i.e") or host in EXCLUDE_HOSTS:
                    continue
                url = f"https://{host}{path}"
                seen.setdefault(url, os.path.relpath(p, REPO))
    return seen


def check(url):
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-L", "--max-time", "20",
                        "-A", "Mozilla/5.0 (research-link-check)", url],
                       capture_output=True, text=True)
    code = r.stdout.strip()
    if r.returncode != 0:
        err = r.stderr.lower()
        if "403" in err or "407" in err or "blocked" in err or "tunnel" in err:
            return "blocked", "000"
        return "unreachable", "000"
    c = int(code)
    if 200 <= c < 400:
        return "ok", code
    if 400 <= c < 500:
        return "client-error", code
    return "server-error", code


if __name__ == "__main__":
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for url, where in sorted(targets().items()):
        result, code = check(url)
        rows.append((url, result, code, now, where))
        print(f"{result:<13} {code} {url}", flush=True)
    out = os.path.join(LEARN, "catalog", "links.tsv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("url\tresult\thttp_code\tchecked_at\twhere\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    summary = {}
    for r in rows:
        summary[r[1]] = summary.get(r[1], 0) + 1
    print("SUMMARY", summary, "total", len(rows))
