#!/usr/bin/env python3
"""Turn the saved-share export into categorized pages.

Input : learning/sources/instagram-export/catalog.tsv   (from the export; see its README)
Output: learning/sources/instagram-export/items/<domain>/<n>.md   one page per link
        learning/sources/instagram-export/index.md                domain and kind counts, links to pages
        learning/sources/instagram-export/categorized.tsv         machine-readable table

Categories are keyword rules over caption, hashtags and creator name. They are a first pass:
a row with no clear match goes to 'نامشخص' rather than being guessed.
External-link summaries come from fetch_external.py (separate step, network).
"""
import csv, os, re, collections

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sources", "instagram-export")
DOMAIN_RULES = [
    ("ai", r"\b(ai|llm|llms|claude|claudeai|claudecode|chatgpt|gpt|openai|gemini|agent|agents|agenticai|aiagents|rag|prompt|prompts|cursor|airesearch|ainews|aitools|aicoding|aiengineering|generativeai|localai|vibecoding|machinelearning|artificialintelligence|هوش_مصنوعی|neuralnetwork|opensourceai)\b"),
    ("gamedev", r"\b(gamedev|indiedev|unity|godot|unreal|gaming|pcgaming|retrogaming|gamedesign|gameplay|videogames?)\b"),
    ("math", r"\b(math|mathematics|statistics|calculus|algebra|geometry|probability|linearalgebra|riemann)\b"),
    ("physics-astronomy", r"\b(physics|astronomy|astrophysics|space|nasa|cosmos|quantum|science)\b"),
    ("programming-infra", r"\b(programming|coding|code|github|opensource|developer|developers|developertools|devtools|python|javascript|typescript|softwareengineering|softwareengineer|systemdesign|webdevelopment|linux|learntocode|cybersecurity|security|docker|kubernetes|rust|golang|sql|devops|cloud|api)\b"),
    ("design-typography", r"\b(design|designer|typography|figma|ui|ux|photoshop|illustrator|graphicdesign|uidesign|font|fonts)\b"),
    ("hardware-tech-privacy", r"\b(tech|technews|hardware|pc|gadgets?|privacy|smartphone|laptop|iphone|android|electronics|arduino|raspberrypi)\b"),
    ("business-marketing", r"\b(business|startups?|startup|marketing|productivity|entrepreneur|entrepreneurship|money|finance|investing|trading|saas|sales|income|passiveincome|buildinpublic)\b"),
    ("learning-language-books", r"\b(learning|education|study|studying|books?|reading|english|language|languages|persian|grammar|vocabulary|learnenglish)\b"),
    ("media-entertainment", r"\b(movies?|film|netflix|memes?|anime|series|tvshow|comedy|shorts|entertainment|viral|cartoon)\b"),
    ("history-myth", r"\b(history|historical|mythology|mystery|mysteries|ancient|archaeology|civilization)\b"),
    ("news-politics", r"\b(news|politics|political|war|election|government|breakingnews)\b"),
    ("society-religion", r"\b(religion|islam|quran|muslim|christian|bible|charity|volunteer|ngo|society|community)\b"),
    ("health-sports", r"\b(fitness|gym|workout|health|nutrition|sports?|football|soccer|running|diet|training|bodybuilding|calisthenics)\b"),
    ("music-sound", r"\b(music|musician|producer|beats|flstudio|daw|audio|sound|synth|guitar|piano|mixing)\b"),
    ("visual-art", r"\b(art|artist|painting|drawing|sketch|illustration|artwork|portrait|sculpture|paint)\b"),
    ("culture-spirituality", r"\b(culture|spirituality|spiritual|philosophy|meditation|mindfulness|poetry|literature)\b"),
]
KIND_RULES = [
    ("ابزار/ریپو", r"\b(github|repo|repository|tool|tools|app|cli|library|framework|plugin|extension|open ?source|opensource|install|self[- ]hosted)\b"),
    ("آموزش", r"\b(tutorial|learn|learning|course|guide|how to|step by step|lesson|masterclass|explained|beginner)\b"),
    ("خبر/بروزرسانی", r"\b(news|update|released|launch|launched|new model|announce|announced|breaking)\b"),
    ("ایده/الهام", r"\b(idea|inspiration|inspire|art|design|cinematic|aesthetic|concept)\b"),
]
DOMAIN_TITLE = {
    "ai": "هوش مصنوعی", "gamedev": "بازی‌سازی", "math": "ریاضی", "physics-astronomy": "فیزیک و نجوم",
    "programming-infra": "برنامه‌نویسی و زیرساخت", "design-typography": "طراحی و تایپوگرافی",
    "hardware-tech-privacy": "سخت‌افزار، فناوری و حریم خصوصی", "business-marketing": "کسب‌وکار و بازاریابی",
    "learning-language-books": "یادگیری، زبان و کتاب", "media-entertainment": "سرگرمی و رسانهٔ تصویری",
    "history-myth": "تاریخ، اسطوره و رازها", "news-politics": "خبر و سیاست", "society-religion": "فعالیت اجتماعی و دین",
    "health-sports": "سلامت و ورزش", "music-sound": "موسیقی و صدا", "visual-art": "هنر تجسمی",
    "culture-spirituality": "فرهنگ و معنویت", "نامشخص": "نامشخص",
}
AI_NODES = [  # (node folder, pattern) for the AI domain only
    ("ai/01-llm-basics", r"\b(llm|llms|token|tokens|context|hallucination|pretraining|rlhf|model)\b"),
    ("ai/02-prompting", r"\b(prompt|prompts|prompting|few-shot|system prompt)\b"),
    ("ai/03-tools-map", r"\b(tool|tools|cursor|copilot|chatgpt|claude|gemini|perplexity|midjourney|higgsfield)\b"),
    ("ai/04-agents-automation", r"\b(agent|agents|agentic|automation|n8n|zapier|mcp|workflow)\b"),
    ("ai/05-api-rag", r"\b(api|rag|embedding|embeddings|vector|retrieval|eval|evals|json)\b"),
]


def fix(s):
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def score(text, rules):
    best, best_n = "", 0
    for name, pat in rules:
        n = len(re.findall(pat, text, flags=re.I))
        if n > best_n:
            best, best_n = name, n
    return best


def categorize(row):
    text = " ".join([row["caption"], row["hashtags"], row["creator"], row["url"], row.get("external", "")])
    domain = score(text, DOMAIN_RULES) or "نامشخص"
    node = ""
    if domain == "ai":
        node = score(text, AI_NODES)
    kind = score(text, KIND_RULES) or "الهام/سرگرمی"
    return domain, node, kind


def summary(caption, limit=280):
    cap = re.sub(r"#\w+", "", caption).strip()
    cap = re.sub(r"\s+", " ", cap)
    if not cap:
        return ""
    cut = re.split(r"(?<=[.!؟?])\s", cap, maxsplit=2)
    text = " ".join(cut[:2]) if cut else cap
    return (text[:limit] + "…") if len(text) > limit else text


def external_text():
    path = os.path.join(BASE, "external.tsv")
    if not os.path.exists(path):
        return {}
    return {r["url"]: r["title"] + " " + r["summary"] for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t")}


def main():
    src = os.path.join(BASE, "catalog.tsv")
    rows = list(csv.DictReader(open(src, encoding="utf-8"), delimiter="\t"))
    ext = external_text()
    out_rows = []
    for i, r in enumerate(rows, 1):
        r["creator"] = fix(r["creator"])
        r["caption"] = fix(r["caption"])
        r["hashtags"] = fix(r["hashtags"])
        # external page text (title and summary) also counts as evidence for the domain
        r["external"] = " ".join(ext.get(u, "") for u in r["links_in_caption"].split())
        domain, node, kind = categorize(r)
        r.update(domain=domain, node=node, kind_class=kind, id=f"{i:04d}", summary=summary(r["caption"]))
        out_rows.append(r)

    # machine-readable table
    fields = ["id", "domain", "node", "kind_class", "url", "kind", "creator", "followed", "date", "summary", "links_in_caption", "hashtags"]
    with open(os.path.join(BASE, "categorized.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)

    # one page per item, grouped by domain
    items_dir = os.path.join(BASE, "items")
    for r in out_rows:
        d = os.path.join(items_dir, r["domain"])
        os.makedirs(d, exist_ok=True)
        node_line = f"- **گرهٔ پیشنهادی:** {r['node']}\n" if r["node"] else ""
        links = "\n".join(f"- {u}" for u in r["links_in_caption"].split()) or "- ندارد"
        page = f"""# {r['creator'] or 'نامشخص'} · {r['id']}

- **حوزه:** {DOMAIN_TITLE.get(r['domain'], r['domain'])}
{node_line}- **کاربرد:** {r['kind_class']}
- **نوع:** {'ریل' if r['kind']=='reel' else 'پست' if r['kind']=='post' else r['kind']}
- **سازنده:** {r['creator']} · {'دنبال‌شده' if r['followed']=='yes' else 'دنبال‌نشده'}
- **تاریخ اشتراک:** {r['date']}
- **لینک:** {r['url']}

## خلاصهٔ استخراجی (از کپشن)
{r['summary'] or 'کپشن ندارد.'}

## لینک‌های داخل کپشن
{links}

## هشتگ‌ها
{r['hashtags'] or '—'}

> ویدیو و زیرنویس این ریل از متن کپشن جداست و اینجا خوانده نشده است.
"""
        open(os.path.join(d, f"{r['id']}.md"), "w", encoding="utf-8").write(page)

    # index
    dom = collections.Counter(r["domain"] for r in out_rows)
    kinds = collections.Counter(r["kind_class"] for r in out_rows)
    lines = ["# خروجی ذخیره‌شده‌ها: فهرست", "", f"جمع: {len(out_rows)} مورد.", "", "## حوزه‌ها"]
    for d, n in dom.most_common():
        lines.append(f"- [{DOMAIN_TITLE.get(d, d)}](items/{d}/) — {n}")
    lines += ["", "## کاربرد", *[f"- {k}: {n}" for k, n in kinds.most_common()], ""]
    open(os.path.join(BASE, "index.md"), "w", encoding="utf-8").write("\n".join(lines))
    print(len(out_rows), "items;", dict(dom.most_common()))


if __name__ == "__main__":
    main()
