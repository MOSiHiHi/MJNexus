#!/usr/bin/env python3
"""Group saved items into topic clusters, as the raw material for project candidates.

Text per item: English summary, Persian what/use, concepts, main resources (twice) and radar category.
TF-IDF, 120-dimension LSA, k-means (fixed seed, so runs are repeatable).
Output: knowledge/data/clusters.tsv (item_id, cluster) and a printed summary per cluster.
Usage: python3 -I knowledge/tools/cluster_saves.py [k=28]
"""
import collections, csv, json, os, sqlite3, sys
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.cluster import KMeans
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
con = sqlite3.connect(os.path.join(ROOT, 'knowledge', 'kg.sqlite'))
items = con.execute("""SELECT id, creator, kind, saved_at, category, use_kind, info_level, summary_en, what_fa, use_fa, concepts, domain
                       FROM item WHERE category != ''""").fetchall()
res = collections.defaultdict(list)
for src, dst, role in con.execute("SELECT src, dst, role FROM edge WHERE rel='MENTIONS'"):
    res[src[5:]].append((dst[9:], role))
names = dict(con.execute("SELECT rid, name FROM resource").fetchall())
docs = []
for r in items:
    rs = " ".join(names.get(x, x).replace(' ', '_') for x, role in res[r[0]] if role == 'main')
    docs.append(" ".join([r[7] or '', r[8] or '', r[9] or '', " ".join(json.loads(r[10] or '[]')), rs, rs, r[4] or '']))
vec = TfidfVectorizer(token_pattern=r"(?u)\b[^\W\d][\w.+-]{2,}\b", min_df=3, max_df=0.25, sublinear_tf=True, stop_words='english')
X = vec.fit_transform(docs)
Z = normalize(TruncatedSVD(n_components=120, random_state=7).fit_transform(X))
k = int(sys.argv[1]) if len(sys.argv) > 1 else 28
km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(Z)
terms = vec.get_feature_names_out()
out = []
for c in range(k):
    idx = [i for i, l in enumerate(km.labels_) if l == c]
    sub = X[idx].mean(axis=0).A1
    top = [terms[j] for j in sub.argsort()[::-1][:12]]
    cats = collections.Counter(items[i][4] for i in idx).most_common(3)
    uses = collections.Counter(items[i][5] for i in idx).most_common(3)
    info = collections.Counter(items[i][6] for i in idx)
    rc = collections.Counter(names.get(x, x) for i in idx for x, role in res[items[i][0]] if role == 'main').most_common(10)
    acc = collections.Counter(items[i][1] for i in idx).most_common(4)
    dates = sorted(items[i][3] for i in idx)
    ex = [items[i][8][:90] for i in idx[:3]]
    out.append(dict(c=c, n=len(idx), top=top, cats=cats, uses=uses, info=dict(info), res=rc, acc=acc, span=(dates[0], dates[-1]), ex=ex, ids=[items[i][0] for i in idx]))
out.sort(key=lambda d: -d['n'])
with open(os.path.join(ROOT, 'knowledge', 'data', 'clusters.tsv'), 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, delimiter='\t', lineterminator='\n')
    w.writerow(['item_id', 'cluster'])
    for d in sorted(out, key=lambda d: d['c']):
        for i in d['ids']:
            w.writerow([i, d['c']])
for d in out:
    print(f"#{d['c']} n={d['n']} cats={d['cats']} uses={d['uses']} info={d['info']}")
    print("   terms:", ", ".join(d['top']))
    print("   res:", ", ".join(f"{a}({b})" for a, b in d['res']))
    print("   acc:", ", ".join(f"{a}({b})" for a, b in d['acc']))
