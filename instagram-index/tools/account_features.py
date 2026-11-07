#!/usr/bin/env python3
"""Derive compact per-account features from raw profile scrapes, so the raw files need not be kept.

Input: raw.jsonl or raw.jsonl.gz files written by apify_profiles.py (one profile per line, with latestPosts).
Output: instagram-index/analysis/account_features.tsv, one row per account (the latest observation wins).

Features
  posts_per_week, reel_share            posting rhythm and format of the recent posts
  median_likes, median_views, engagement_rate (median likes / followers)
  cta_share      share of recent captions that gate content behind "comment X" or "link in bio"
  link_share     share with a URL; github_share with a GitHub, Hugging Face or arXiv link
  persian_share  share written in Persian script
  top_hashtags, top_terms               what the account talks about (terms by TF-IDF)
  domain_guess, radar_guess             closest learning domain and radar category, by similarity to the
                                        owner's saved items in each (score = cosine similarity; empty below 0.03)

Usage: python3 -I instagram-index/tools/account_features.py RAW [RAW ...]
"""
import collections, csv, gzip, json, os, re, sqlite3, statistics, sys
from datetime import datetime

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "instagram-index", "analysis", "account_features.tsv")
DB = os.path.join(ROOT, "knowledge", "kg.sqlite")

CTA = re.compile(r"\bcomment\b|کامنت|link in (my |the )?bio|لینک (در|تو|توی) بیو|\bdm me\b|دایرکت|send you the link|"
                 r"type .{1,20} below|reply with", re.I)
URL = re.compile(r"https?://|www\.", re.I)
TECH = re.compile(r"github\.com|huggingface\.co|arxiv\.org|\bgithub\b", re.I)
PERSIAN = re.compile(r"[؀-ۿ]")
MIN_SIM = 0.03  # below this the guess is left empty
FA_STOP = set("و از به که در این را با برای است یک تا هم می شود شده های ها ای آن او ما من تو شما اگر یا هر بر چه کرد کنید کن "
              "خود نیز اما باید دارد داره هست بود هستند نه رو تو اینجا اون".split())


def records(paths):
    for p in paths:
        opener = gzip.open if p.endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("username") and "latestPosts" in o:
                    yield o


def when(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def share(flags):
    return round(sum(flags) / len(flags), 2) if flags else ""


def main(paths):
    best = {}
    for o in records(paths):
        u = o["username"].lower()
        posts = o.get("latestPosts") or []
        observed = max((p.get("timestamp") or "" for p in posts), default="")
        if u not in best or (len(posts), observed) > (len(best[u].get("latestPosts") or []), best[u]["_obs"]):
            o["_obs"] = observed
            best[u] = o
    print("accounts", len(best), file=sys.stderr)

    # reference documents: the owner's saved items, grouped by learning domain and by radar category
    con = sqlite3.connect(DB)
    by_domain, by_radar = collections.defaultdict(list), collections.defaultdict(list)
    for dom, cat, en, fa in con.execute("SELECT domain, category, summary_en, what_fa FROM item"):
        text = f"{en or ''} {fa or ''}"
        if dom and dom != "نامشخص":
            by_domain[dom].append(text)
        if cat and cat != "other":
            by_radar[cat].append(text)

    accounts = sorted(best)
    docs = []
    for u in accounts:
        caps = [(p.get("caption") or "") for p in best[u].get("latestPosts") or []]
        docs.append(" ".join(caps + [best[u].get("biography") or ""]))
    ref_names = [("domain", d) for d in sorted(by_domain)] + [("radar", c) for c in sorted(by_radar)]
    ref_items = [by_domain[d] for _, d in ref_names if _ == "domain"] + [by_radar[c] for _, c in ref_names if _ == "radar"]
    stop = list(FA_STOP | set(TfidfVectorizer(stop_words="english").get_stop_words()))
    vec = TfidfVectorizer(stop_words=stop, token_pattern=r"(?u)\b[^\W\d_]{3,}\b", max_df=0.3, min_df=3, sublinear_tf=True)
    flat = [t for group in ref_items for t in group]
    X = vec.fit_transform(docs + flat)
    A, items = X[:len(docs)], X[len(docs):]
    # one centroid per class (mean of item vectors), so a class with many saves is not favoured for its size
    cents, k = [], 0
    for group in ref_items:
        cents.append(np.asarray(items[k:k + len(group)].mean(axis=0)))
        k += len(group)
    R = normalize(np.vstack(cents))
    sim = cosine_similarity(A, R)
    terms = vec.get_feature_names_out()
    n_dom = sum(1 for k, _ in ref_names if k == "domain")

    rows = []
    for i, u in enumerate(accounts):
        o = best[u]
        posts = o.get("latestPosts") or []
        caps = [(p.get("caption") or "") for p in posts]
        times = sorted(t for t in (when(p.get("timestamp")) for p in posts) if t)
        span = (times[-1] - times[0]).total_seconds() / 86400 if len(times) > 1 else 0
        likes = [p.get("likesCount") for p in posts if isinstance(p.get("likesCount"), int) and p["likesCount"] >= 0]
        views = [p.get("videoViewCount") for p in posts if isinstance(p.get("videoViewCount"), int)]
        followers = o.get("followersCount") or 0
        tags = collections.Counter(h.lower() for p in posts for h in (p.get("hashtags") or []))
        row = A[i].toarray()[0]
        top_terms = [terms[j] for j in row.argsort()[::-1][:8] if row[j] > 0]
        d_j = sim[i][:n_dom].argmax() if n_dom else None
        r_j = sim[i][n_dom:].argmax() if len(ref_names) > n_dom else None
        if d_j is not None and sim[i][d_j] < MIN_SIM:  # too little text to say
            d_j = None
        if r_j is not None and sim[i][n_dom + r_j] < MIN_SIM:
            r_j = None
        rows.append({
            "username": u,
            "full_name": (o.get("fullName") or "").replace("\t", " ").replace("\n", " ").strip(),
            "followers": followers,
            "posts_total": o.get("postsCount") or "",
            "verified": "yes" if o.get("verified") else "no",
            "business_category": o.get("businessCategoryName") or "",
            "n_recent": len(posts),
            "recent_from": times[0].date().isoformat() if times else "",
            "recent_to": times[-1].date().isoformat() if times else "",
            "posts_per_week": round((len(times) - 1) / span * 7, 1) if span > 0 else "",
            "reel_share": share([p.get("type") == "Video" for p in posts]),
            "median_likes": int(statistics.median(likes)) if likes else "",
            "median_views": int(statistics.median(views)) if views else "",
            "engagement_rate": round(statistics.median(likes) / followers, 4) if likes and followers else "",
            "cta_share": share([bool(CTA.search(c)) for c in caps]),
            "link_share": share([bool(URL.search(c)) for c in caps]),
            "github_share": share([bool(TECH.search(c)) for c in caps]),
            "persian_share": share([bool(PERSIAN.search(c)) for c in caps if c.strip()]),
            "top_hashtags": " ".join(h for h, _ in tags.most_common(5)),
            "top_terms": " ".join(top_terms),
            "domain_guess": ref_names[d_j][1] if d_j is not None else "",
            "domain_score": round(float(sim[i][d_j]), 3) if d_j is not None else "",
            "radar_guess": ref_names[n_dom + r_j][1] if r_j is not None else "",
            "radar_score": round(float(sim[i][n_dom + r_j]), 3) if r_j is not None else "",
            "observed": o["_obs"][:10],
        })
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT, len(rows), "rows", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
