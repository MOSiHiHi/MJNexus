# MJNexus

**A personal tool radar and knowledge graph, built from 1,986 saved Instagram posts.**
It lists the tools, repos, models and courses those posts point to, the accounts that posted them, and the evidence behind each one. Well-known tools and concepts link to their official site, Wikipedia and Wikidata.

**رادار ابزار و گراف دانش شخصی، ساخته‌شده از ۱٬۹۸۶ پست ذخیره‌شدهٔ اینستاگرام.** نشان می‌دهد این پست‌ها به چه ابزارها، ریپوها، مدل‌ها و دوره‌هایی اشاره می‌کنند، هر پست را کدام حساب منتشر کرده و شاهد هر ادعا چیست. ابزارها و مفهوم‌های شناخته‌شده به سایت رسمی، ویکی‌پدیا و ویکی‌داده وصل‌اند.

> Persian is the working language of this repository. Code and file names are in English.

## The radar site · سایت رادار

`site/` is a static page with no build step and no server code. It offers three views of the same data:

| View | Shows |
|---|---|
| مخزن دانش (knowledge graph) | Learning-wiki domains and concepts, radar categories, 764 resources, and the 465 accounts that posted about them |
| رادار (radar) | The classic radar: one slice per category and four rings (Adopt, Trial, Assess, Hold) |
| هستی‌شناسی (ontology) | The data model itself: entities, relations and their counts |

Click any node and the right panel shows:
- the summary, license, last commit and risk flags
- official site, Wikipedia (fa and en) and Wikidata links
- related concepts
- the accounts that posted about it
- every saved post that mentions it

The selection is kept in the URL, so a view can be shared. For example, `#sel=r:res:claude-code` opens Claude Code.

- **Online:** GitHub Pages, published by `.github/workflows/pages.yml` once Pages is enabled (Settings > Pages > Source: GitHub Actions).
- **Locally:** `python3 -m http.server -d site 8000`, then open http://localhost:8000.

## What is inside · محتوا

| Path | Contents |
|---|---|
| `knowledge/` | The model: `ontology.yaml`, `kg.sqlite`, extraction outputs, tools and the radar page. See [knowledge/README.md](knowledge/README.md) |
| `site/` | The published radar (page, data, d3 and a small runtime) |
| `learning/` | A Persian learning wiki: 17 domains, 79 concept nodes, the saved-posts export and its catalogue |
| `instagram-index/` | Public profile fields of followed accounts, their derived summaries, and the tools that fetched them |
| `docs/radar-research.md` | Comparison with Thoughtworks, Zalando, AOE, Backstage and CNCF radars, and what this project took from each |
| `.claude/skills/` | Claude Code skills: `tool-radar` (ask the radar) and `agent-reach` |

## Ask the radar from the command line · پرسیدن از رادار

```sh
python3 -I knowledge/tools/radar.py find rag
python3 -I knowledge/tools/radar.py top --category coding-agents
python3 -I knowledge/tools/radar.py resource "Claude Code"
python3 -I knowledge/tools/radar.py account gittrend.io
python3 -I knowledge/tools/radar.py licenses
```

## Rebuild · ساخت دوباره

Python 3.11+ with `pyyaml`:

```sh
python3 -I knowledge/tools/link_entities.py     # Wikidata ids, official sites, Wikipedia pages
python3 -I knowledge/tools/build_db.py          # knowledge/kg.sqlite from every source
python3 -I knowledge/tools/export_dashboard.py  # datasets for the page
python3 -I knowledge/tools/build_site.py        # site/
```

The full pipeline, including link and repo checks, language-model extraction and the video layer, is in [knowledge/README.md](knowledge/README.md).

## Data, sources and privacy · داده و حریم خصوصی

See [DATA.md](DATA.md). In short:
- Saved posts are public posts by their authors. This repository keeps their links, short summaries and the resources they name.
- Third-party comment text and raw scraper dumps are not kept.
- Fields marked owner-only (ring, notes, projects) are never inferred.
- Account owners can ask for removal by opening an issue.

## License · مجوز

- **Code:** [MIT](LICENSE).
- **Third-party content:** captions and post text quoted in the data belong to their authors.
- **Wikidata facts:** CC0.
- **Wikipedia links:** link to CC BY-SA articles.
- **d3:** [ISC](site/assets/vendor/d3-LICENSE.txt).
