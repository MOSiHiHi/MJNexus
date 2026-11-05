"""Add any file to the learning vault: store it under a tree node, catalog it, extract searchable text.

Usage (from the repository root):
  python3 -I learning/tools/ingest.py FILE... --node ai/02-prompting --purpose study \
      [--tags "prompt,few-shot"] [--source URL] [--note "why I added this"]
  python3 -I learning/tools/ingest.py --inbox --node ai/01-llm-basics --purpose reference
      (takes everything in learning/inbox/)
  python3 -I learning/tools/ingest.py --list [--node ai/02-prompting]

--purpose: study | example | exercise | reference | work  (work = output of a real task)

Every file is kept byte-for-byte (any format, including binaries). The catalog
(learning/catalog/catalog.jsonl) records hash, type, size, node, purpose and where
its extracted text lives, so people and agents can search and reuse it.
Text is extracted automatically for text/code, PDF, Office (docx/xlsx/pptx) and
image metadata; other binaries are catalogued with `file`'s description only.
"""
import argparse, hashlib, json, mimetypes, os, re, shutil, subprocess, sys, zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # learning/
CATALOG = os.path.join(ROOT, "catalog", "catalog.jsonl")
TEXT_DIR = os.path.join(ROOT, "catalog", "text")
MAX_BYTES = 50 * 1024 * 1024   # GitHub rejects files over 100 MB and warns above 50 MB
TEXT_LIMIT = 400_000           # characters of extracted text kept per file
PURPOSES = ("study", "example", "exercise", "reference", "work")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def describe(path):
    try:
        return subprocess.run(["file", "-b", path], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def as_text(path):
    raw = open(path, "rb").read(TEXT_LIMIT * 4)
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")[:TEXT_LIMIT]
    except UnicodeDecodeError:
        return None


def office_text(path):
    parts = {"word/document.xml"}, ("ppt/slides/",), ("xl/sharedStrings.xml",)
    out = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name in parts[0] or name.startswith(parts[1]) or name in parts[2]:
                xml = z.read(name).decode("utf-8", "replace")
                out.append(re.sub(r"<[^>]+>", " ", xml))
    return re.sub(r"\s+", " ", " ".join(out))[:TEXT_LIMIT] or None


def extract(path, mime, desc):
    """Return (text or None, extra metadata dict, method name)."""
    meta = {}
    if mime == "application/pdf" or desc.startswith("PDF"):
        r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=300)
        return (r.stdout[:TEXT_LIMIT] or None), meta, "pdftotext"
    if path.lower().endswith((".docx", ".pptx", ".xlsx")) and zipfile.is_zipfile(path):
        return office_text(path), meta, "office-xml"
    if (mime or "").startswith("image/") or "image data" in desc:
        # `file` guesses loosely (random bytes can look like Targa), so only trust images Pillow can open
        try:
            from PIL import Image
            with Image.open(path) as im:
                meta.update(width=im.width, height=im.height, image_mode=im.mode)
            # images are described later by a person or an agent that can see them
            meta["needs_description"] = True
            return None, meta, "image-metadata"
        except Exception:
            if mime.startswith("image/svg"):
                return as_text(path), meta, "utf-8"
    text = as_text(path)
    if text is not None:
        return text, meta, "utf-8"
    return None, meta, "binary-catalogued"


def load_catalog():
    if not os.path.exists(CATALOG):
        return []
    return [json.loads(l) for l in open(CATALOG, encoding="utf-8") if l.strip()]


def ingest(path, args, known):
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        print(f"SKIP {path}: {size/1e6:.0f} MB > 50 MB. Keep it in Google Drive (or Git LFS) and add a "
              f"reference file with the link instead.", file=sys.stderr)
        return None
    digest = sha256(path)
    if digest in known:
        print(f"DUPLICATE {path}: already catalogued as {known[digest]['stored_path']}")
        return None
    name = os.path.basename(path)
    mime = mimetypes.guess_type(name)[0] or ""
    desc = describe(path)
    node_dir = os.path.join(ROOT, args.node, "resources")
    os.makedirs(node_dir, exist_ok=True)
    stored = os.path.join(node_dir, f"{digest[:8]}-{name}")
    (shutil.move if args.move else shutil.copy2)(path, stored)
    text, meta, method = extract(stored, mime, desc)
    text_path = None
    if text:
        os.makedirs(TEXT_DIR, exist_ok=True)
        text_path = os.path.join(TEXT_DIR, f"{digest}.txt")
        open(text_path, "w", encoding="utf-8").write(text)
    entry = {
        "id": digest[:12], "sha256": digest, "name": name, "node": args.node, "purpose": args.purpose,
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
        "source": args.source or "", "note": args.note or "",
        "mime": mime, "file_description": desc, "size_bytes": size,
        "stored_path": os.path.relpath(stored, os.path.dirname(ROOT)),
        "text_path": os.path.relpath(text_path, os.path.dirname(ROOT)) if text_path else None,
        "extraction": method, **meta,
        "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    with open(CATALOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"OK {entry['id']} {name} -> {entry['stored_path']} ({method})")
    return entry


def main():
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="*")
    p.add_argument("--node")
    p.add_argument("--purpose", choices=PURPOSES)
    p.add_argument("--tags"); p.add_argument("--source"); p.add_argument("--note")
    p.add_argument("--inbox", action="store_true", help="ingest everything in learning/inbox/")
    p.add_argument("--move", action="store_true", help="move instead of copy (default for --inbox)")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    cat = load_catalog()
    if args.list:
        for e in cat:
            if not args.node or e["node"] == args.node:
                print(f"{e['id']}  {e['node']:<24} {e['purpose']:<9} {e['name']}  [{e['extraction']}]")
        return
    if not args.node or not args.purpose:
        p.error("--node and --purpose are required to add files")
    if not os.path.isdir(os.path.join(ROOT, args.node)):
        p.error(f"unknown node {args.node!r}; create its folder (with a README.md) first")
    files = list(args.files)
    if args.inbox:
        args.move = True
        inbox = os.path.join(ROOT, "inbox")
        files += [os.path.join(inbox, f) for f in sorted(os.listdir(inbox)) if not f.startswith(".")]
    known = {e["sha256"]: e for e in cat}
    for f in files:
        if os.path.isfile(f):
            e = ingest(f, args, known)
            if e:
                known[e["sha256"]] = e


main()
