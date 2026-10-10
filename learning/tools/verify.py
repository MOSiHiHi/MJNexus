"""Verify the learning vault against the owner's index and its own rules.

Usage (repo root):  python3 -I learning/tools/verify.py
Exit code 1 if any check fails. Checks:
  1. every @username cited in learning/**/*.md exists in instagram-index/index/profiles.tsv
  2. every relative markdown link points to an existing file
  3. progress.md rows with a non-zero level have evidence (date and shahed)
  4. every file under a resources/ folder has a catalog entry, and every catalog entry exists
  5. analysis owner-only columns (my_*) are still empty
"""
import csv, glob, json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEARN = os.path.join(REPO, "learning")
failures = []


def fail(msg):
    failures.append(msg)
    print("FAIL", msg)


# 1. citations against the index
index_users = {r["username"].lower() for r in csv.DictReader(open(os.path.join(REPO, "instagram-index/index/profiles.tsv"), encoding="utf-8"), delimiter="\t")}
md_files = [p for p in glob.glob(os.path.join(LEARN, "**/*.md"), recursive=True)]
cited = 0
for p in md_files:
    text = open(p, encoding="utf-8").read()
    for m in re.finditer(r"@([A-Za-z0-9_.]+)", text):
        name = m.group(1).rstrip(".").lower()
        if name in ("نام",):
            continue
        cited += 1
        if name not in index_users:
            fail(f"{os.path.relpath(p, REPO)}: @{m.group(1)} not in index")

# 2. relative markdown links
links_checked = 0
for p in md_files:
    text = open(p, encoding="utf-8").read()
    for m in re.finditer(r"\]\((?!https?:)([^)#\s]+)(#[^)]*)?\)", text):
        target = os.path.normpath(os.path.join(os.path.dirname(p), m.group(1)))
        links_checked += 1
        if not os.path.exists(target):
            fail(f"{os.path.relpath(p, REPO)}: broken link {m.group(1)}")

# 3. progress evidence
prog = os.path.join(LEARN, "progress.md")
if os.path.exists(prog):
    for line in open(prog, encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] and cells[0][0] not in "-|#" and cells[1].isdigit() and int(cells[1]) > 0:
            if not cells[2] or cells[2] in ("—", "-") or not cells[3] or cells[3] in ("—", "-"):
                fail(f"progress.md: level {cells[1]} for '{cells[0]}' lacks date or evidence")

# 4. catalog <-> resources
cat_path = os.path.join(LEARN, "catalog", "catalog.jsonl")
catalogued = set()
if os.path.exists(cat_path):
    for l in open(cat_path, encoding="utf-8"):
        if l.strip():
            e = json.loads(l)
            catalogued.add(e["stored_path"])
            if not os.path.exists(os.path.join(REPO, e["stored_path"])):
                fail(f"catalog entry missing on disk: {e['stored_path']}")
for p in glob.glob(os.path.join(LEARN, "**/resources/*"), recursive=True):
    if os.path.basename(p) == ".gitkeep":
        continue
    rel = os.path.relpath(p, REPO)
    if rel not in catalogued:
        fail(f"uncatalogued file: {rel}")

# 5. owner-only columns must stay empty until the owner reviews
for f in glob.glob(os.path.join(REPO, "instagram-index/analysis/enriched*.tsv")):
    rows = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="\t"))
    for col in ("my_status", "my_rating", "my_notes", "reviewed_on"):
        if col in rows[0]:
            # my_status has a default value 'بررسی‌نشده' by design
            filled = [r for r in rows if r[col] and not (col == "my_status" and r[col] == "بررسی‌نشده")]
            if filled:
                fail(f"{os.path.relpath(f, REPO)}: {len(filled)} rows filled in {col} (owner-only)")

nodes = len(glob.glob(os.path.join(LEARN, "*/*/README.md")))
print(f"SUMMARY: wiki pages={nodes}, citations={cited}, links={links_checked}, failures={len(failures)}")
sys.exit(1 if failures else 0)
