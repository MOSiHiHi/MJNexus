#!/usr/bin/env python3
"""Link well-known resources and concepts to their canonical web identity.

For each resource or wiki concept that is a known entity, find its Wikidata item, official website,
English and Persian Wikipedia pages. Results go to knowledge/data/entity_links.tsv, which build_db.py reads.

How a match is found (strict on purpose: a wrong link is worse than none)
  repo      Wikidata item whose 'source code repository' (P1324) is the repo URL.
  curated   knowledge/data/entity_curated.tsv: a human-checked Wikipedia title, homepage, or 'none'.
  title     exact English Wikipedia title (after redirects) for the name or '<name> (software)',
            accepted only when the page is not a disambiguation page and its Wikidata
            description fits the resource type (software, model, service, book, ...).

Sources: en.wikipedia.org action API and query.wikidata.org SPARQL (no key needed).
Usage: python3 -I knowledge/tools/link_entities.py [--min-mentions 1]
"""
import argparse, csv, json, os, re, sqlite3, time, urllib.parse, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "knowledge", "data")
DB = os.path.join(ROOT, "knowledge", "kg.sqlite")
OUT = os.path.join(DATA, "entity_links.tsv")
CURATED = os.path.join(DATA, "entity_curated.tsv")
FIELDS = ["id", "name", "qid", "homepage", "wikipedia_en", "wikipedia_fa", "description_en", "method"]
UA = {"User-Agent": "MJNexus-radar/1.0 (personal knowledge model; github.com/MOSiHiHi/MJNexus)"}

# the Wikidata description must contain one of these for a title match to count, per resource type
TYPE_WORDS = {
    "book": r"book|novel|essay|treatise|text|work by",
    "course": r"course|lecture|programme|program|curriculum|website|platform",
    "paper": r"paper|article|publication",
    "dataset": r"dataset|database|corpus|benchmark",
    "model": r"model|neural network|chatbot|transformer|generative|artificial intelligence|\bAI\b|LLM",
    "protocol": r"protocol|standard|specification|format",
    "concept": r".",
}
SOFTWARE = (r"software|application|\bapp\b|program|framework|library|platform|tool|editor|environment|IDE|"
            r"service|website|web site|search engine|browser|operating system|chatbot|assistant|model|"
            r"artificial intelligence|\bAI\b|company|startup|engine|language|database|protocol|game|"
            r"store|marketplace|network|social|video|cloud|API|agent|terminal|shell|command-line")


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:  # rate limits and timeouts: back off and retry
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def sparql(query):
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    return get(url)["results"]["bindings"]


def lit(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"@en'


def wiki_titles(titles):
    """Exact English Wikipedia article titles -> {title: (title, qid, disambiguation)}.

    Looked up through Wikidata sitelinks (the Wikipedia API itself rate-limits shared cloud IPs).
    Redirects are not followed, so a title must be the article's own title."""
    out = {}
    titles = [t for t in titles if t and "\n" not in t]
    for i in range(0, len(titles), 80):
        chunk = titles[i:i + 80]
        rows = sparql(f"""SELECT ?name ?item ?dis WHERE {{ VALUES ?name {{ {" ".join(lit(t) for t in chunk)} }}
            ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?name .
            BIND(EXISTS {{ ?item wdt:P31 wd:Q4167410 }} AS ?dis) }}""")
        for r in rows:
            t = r["name"]["value"]
            out[t] = (t, r["item"]["value"].rsplit("/", 1)[1], r["dis"]["value"] == "true")
        time.sleep(1)
    return out


def describe(qids):
    """Wikidata items -> official website, English description, en/fa Wikipedia pages."""
    info = {}
    qids = sorted(set(q for q in qids if q))
    for i in range(0, len(qids), 60):
        values = " ".join("wd:" + q for q in qids[i:i + 60])
        rows = sparql(f"""SELECT ?item ?site ?rank ?desc ?en ?fa WHERE {{ VALUES ?item {{ {values} }}
            OPTIONAL {{ ?item p:P856 ?st . ?st ps:P856 ?site; wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank) }}
            OPTIONAL {{ ?item schema:description ?desc FILTER(lang(?desc) = "en") }}
            OPTIONAL {{ ?en schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> }}
            OPTIONAL {{ ?fa schema:about ?item; schema:isPartOf <https://fa.wikipedia.org/> }} }}""")
        for r in rows:
            q = r["item"]["value"].rsplit("/", 1)[1]
            cur = info.setdefault(q, {"homepage": "", "description_en": "", "wikipedia_en": "", "wikipedia_fa": "", "sites": set()})
            for key, field in (("desc", "description_en"), ("en", "wikipedia_en"), ("fa", "wikipedia_fa")):
                if key in r and not cur[field]:
                    cur[field] = r[key]["value"]
            if "site" in r:
                cur["sites"].add((r["rank"]["value"].endswith("PreferredRank"), r["site"]["value"]))
        time.sleep(1)
    for cur in info.values():
        cur["homepage"] = pick_site(cur.pop("sites"))
    return info


LOCALE = re.compile(r"/(?:[a-z]{2}-[a-z]{2}|[a-z]{2}_[A-Z]{2}|portugues|ru|de|fr|ja|zh)(?:/|\.html|$)", re.I)


def pick_site(sites):
    """One homepage among several P856 values: preferred rank, then no locale path, then https, then shortest."""
    if not sites:
        return ""
    return sorted(sites, key=lambda s: (not s[0], bool(LOCALE.search(s[1])), not s[1].startswith("https"), len(s[1])))[0][1]


def by_repo(repos):
    """GitHub repos -> Wikidata item through 'source code repository' (P1324)."""
    found = {}
    for i in range(0, len(repos), 80):
        values = " ".join(f"<https://github.com/{r}>" for r in repos[i:i + 80])
        for r in sparql(f"SELECT ?item ?repo WHERE {{ VALUES ?repo {{ {values} }} ?item wdt:P1324 ?repo }}"):
            found[r["repo"]["value"].split("github.com/", 1)[1].lower()] = r["item"]["value"].rsplit("/", 1)[1]
        time.sleep(1)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-mentions", type=int, default=1)
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    res = con.execute("SELECT rid, name, type, repo FROM resource WHERE mentions >= ? ORDER BY mentions DESC",
                      (a.min_mentions,)).fetchall()
    curated = {}
    if os.path.exists(CURATED):
        for r in csv.DictReader(open(CURATED, encoding="utf-8"), delimiter="\t"):
            curated[r["id"]] = r
    links = {}  # id -> (name, qid, method, homepage override)

    # 1. curated rows win
    concept_names = dict(con.execute("SELECT 'concept:' || node, title FROM concept").fetchall())
    for cid, r in curated.items():
        links[cid] = {"name": r["name"] or concept_names.get(cid, ""), "title": r["wikipedia_en"], "qid": r.get("qid", ""),
                      "homepage": r.get("homepage", ""), "method": "curated"}

    # 2. repos through P1324
    repos = {r[3].lower(): r for r in res if r[3]}
    for repo, qid in by_repo(sorted(repos)).items():
        rid, name = repos[repo][0], repos[repo][1]
        links.setdefault(rid, {"name": name, "title": "", "qid": qid, "homepage": "", "method": "repo"})

    # 3. exact Wikipedia titles for named resources (sites are named by their host: skip)
    named = [r for r in res if r[0] not in links and r[2] not in ("repo", "site") and len(r[1]) >= 3]
    asks = {}
    for rid, name, typ, _ in named:
        asks.setdefault(name, []).append((rid, typ))
        if typ in ("tool", "service", "skill", "protocol", "model"):
            asks.setdefault(f"{name} (software)", []).append((rid, typ))
    titles = wiki_titles(sorted(asks))
    pending = {}
    for asked, hits in asks.items():
        t = titles.get(asked)
        if not t or t[2] or not t[1]:
            continue
        for rid, typ in hits:
            # prefer the '(software)' page when both exist
            if rid not in pending or asked.endswith("(software)"):
                pending[rid] = (t[0], t[1], typ)

    # curated titles need their Wikidata item too
    ctitles = wiki_titles(sorted({v["title"] for v in links.values() if v["method"] == "curated" and v["title"] and v["title"] != "none"}))
    for v in links.values():
        if v["method"] == "curated" and not v["qid"] and v["title"] in ctitles and not ctitles[v["title"]][2]:
            v["qid"] = ctitles[v["title"]][1]

    info = describe([v["qid"] for v in links.values()] + [p[1] for p in pending.values()])
    names = {r[0]: r[1] for r in res}
    for rid, (title, qid, typ) in pending.items():
        desc = info.get(qid, {}).get("description_en", "")
        if re.search(TYPE_WORDS.get(typ, SOFTWARE), desc, re.I):
            links[rid] = {"name": names[rid], "title": title, "qid": qid, "homepage": "", "method": "title"}

    rows = []
    for lid, v in links.items():
        if v["title"] == "none":  # curated: known not to be a public entity
            continue
        d = info.get(v["qid"], {})
        homepage = v["homepage"] or d.get("homepage", "")
        if not (v["qid"] or homepage):
            continue
        rows.append({"id": lid, "name": v["name"], "qid": v["qid"], "homepage": homepage,
                     "wikipedia_en": d.get("wikipedia_en", ""), "wikipedia_fa": d.get("wikipedia_fa", ""),
                     "description_en": d.get("description_en", ""), "method": v["method"]})
    rows.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["method"]] = by.get(r["method"], 0) + 1
    print("linked", len(rows), by)


if __name__ == "__main__":
    main()
