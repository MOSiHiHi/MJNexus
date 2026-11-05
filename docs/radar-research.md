# Similar tools, and what this radar takes from them

Written 2026-11-05. It compares the open-source technology radars that most teams reuse, and personal knowledge tools. Each entry says what this project adopted.

## Technology radars

| Tool | What it is | Data input | Notable features |
|---|---|---|---|
| [Thoughtworks Technology Radar](https://www.thoughtworks.com/radar) and [Build Your Own Radar](https://github.com/thoughtworks/build-your-own-radar) | The original radar: four quadrants and four rings (Adopt, Trial, Assess, Hold), published twice a year | Google Sheet, CSV or JSON with `name, ring, quadrant, isNew, description` | Blip movement markers (new, moved in, moved out); one description per blip |
| [Zalando Tech Radar](https://github.com/zalando/tech-radar) | A single static page drawn with d3, the base for many company radars | A JS object with `quadrant`, `ring`, `label`, `moved` per entry | Static hosting; numbered blips with a legend list; marks for new and moved blips |
| [AOE Technology Radar](https://github.com/AOEpeople/aoe_technology_radar) | A static site generator for radars (v4 no longer depends on d3) | One Markdown file per blip, grouped by release date, with front matter (`ring`, `quadrant`, `tags`) | Fuzzy search, tag filter, a page per blip with its history; blips that leave the radar stay searchable |
| [Backstage Tech Radar plugin](https://github.com/backstage/community-plugins/tree/main/workspaces/tech-radar) | Zalando's radar inside a developer portal | A JSON data model: `quadrants`, `rings`, `entries` with a timeline of ring moves | A timeline of each entry's ring changes with a reason |
| [CNCF Tech Radar](https://radar.cncf.io/) | Community radars on one theme per edition | Survey of end users | Each blip shows how many teams use it; a theme per edition |

## Personal and knowledge tools

| Tool | Relevant idea |
|---|---|
| Wikidata and Wikipedia | A shared identity for well-known things: one item id, official website (property P856), source repository (P1324), and an article in many languages |
| Bookmark managers (Raindrop, Pinboard) and GitHub star organisers | Saved links grouped by tags; they rarely say *who* recommended something or *how often* it came up |
| Note graphs (Obsidian graph view, Logseq) | A force graph of notes and links, with a side panel for the open note |

## What this project took

| Idea | Source | Here |
|---|---|---|
| Rings Adopt, Trial, Assess, Hold, and a slice per area | Thoughtworks, Zalando | «رادار» view: 8 category slices × 4 rings. The ring is an owner-only decision in `knowledge/data/radar_owner.tsv`; everything else starts in Assess. |
| Data in plain files, one static page | Zalando, BYOR | `site/` is plain HTML, JS and JSON, and can be hosted anywhere (GitHub Pages workflow included) |
| A mark for new blips | Thoughtworks, Zalando | A dark edge marks resources first saved in the last 30 days |
| Search, filters, a detail view per blip | AOE | Search box, category, license, mention and risk filters; the right panel holds everything about the picked node |
| Ring history with a reason | Backstage | Planned: `radar_owner.tsv` keeps `ring`, `verification` and `notes_fa` today; a dated history column is the next step |
| Shared identity for known things | Wikidata | `knowledge/tools/link_entities.py` links resources and concepts to their Wikidata item, official site and Wikipedia pages |

## What is different here

- **Evidence comes first.** Every blip comes from saved posts. The detail panel lists those posts, the accounts that published them, and the claims they make.
- **Accounts are part of the model.** Each post names its account, and the canvas shows which accounts talk about which tools.
- **License and activity are measured, not guessed.** They come from each repo's license file and last commit.
- **The radar is one view of a larger graph.** The same canvas shows concepts from the learning wiki and the ontology itself.

## Not taken

- **Google Sheets input:** the data lives in the repository instead.
- **A Node build step:** the site needs no build tool. A Python script copies the data.
- **Numbered blips:** with hundreds of blips, hovering and search work better than a printed legend.
