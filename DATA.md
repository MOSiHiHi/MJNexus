# Data, sources and privacy

نگارش: ۲۰۲۶-۱۱-۰۵

## Where the data comes from

| Source | What is kept | Where |
|---|---|---|
| The owner's own Instagram data export (saved posts shared to the owner's second account) | Post links, account names, dates, captions as published, derived summaries | `learning/sources/instagram-export/` |
| The owner's list of followed accounts | Usernames | `instagram-index/input/following.json` |
| Public profile data for followed accounts, fetched through the Apify Instagram profile scraper | Public profile fields per account: display name, bio, external links, follower, following and post counts, category; plus a derived Persian description and topic | `instagram-index/index/`, `instagram-index/analysis/`, `instagram-index/runs/*/results.jsonl` |
| Public GitHub repositories, read with anonymous `git` | Existence, default branch, last commit date, license file name and type | `knowledge/data/repos.tsv` |
| Wikidata (CC0) via its public SPARQL endpoint | Item id, official website, English description, links to Wikipedia articles | `knowledge/data/entity_links.tsv` |
| Language-model reading of captions and reels | Summaries, named resources, claims, categories, risk flags; validated by `check_llm.py` | `knowledge/data/llm/`, `knowledge/data/video/` |

## What is deliberately not kept

- **Comment text by third parties.** Only comment counts are kept.
- **Raw scraper dumps** (`instagram-index/runs/*/raw.jsonl`). They held full public profiles and recent posts of followed accounts. They were removed from the working tree on 2026-11-05 and are ignored by git. Older commits still contain them, so the git history must be rewritten before the repository is made public (see below).
- **Videos, audio and frames** from the video layer. These stay on the machine that processed them.
- **Login cookies, tokens and API keys.** None are stored. The Apify credential is attached by the execution environment.

## Owner-only fields

`ring`, `notes_fa`, `verification`, projects, and anything `my_*` are decisions made by the repository owner. Tools never infer or fill them. Until the owner sets a ring, every resource shows as **Assess**.

## Accuracy

- **Model-generated text.** Summaries, translations and claims come from a language model and have not been checked by a person.
- **Claims are unverified.** Each claim stays `unverified` until it is checked.
- **Entity links.** Links to Wikidata and official sites are either hand-checked (`entity_curated.tsv`, method `curated`), matched by exact Wikipedia title with a type check (`title`), or found through a repository link on Wikidata (`repo`). The method is recorded for every link.

## Removal requests

If you are the author of a post or an account in this data and want it removed, open an issue with the post or account link. It will be removed from the data and the site.

## Before making the repository public

1. **Rewrite the git history** so the raw scraper dumps leave older commits too, for example with `git filter-repo --path-glob 'instagram-index/runs/*/raw.jsonl' --invert-paths`. Then force-push. Alternatively, publish a fresh repository from the current tree.
2. **Check the files in the owner's own export.** `learning/sources/instagram-export/messages.json` is the owner's own conversation between two of the owner's accounts. Keeping it public is the owner's explicit decision.
3. **Enable GitHub Pages** (Source: GitHub Actions) to publish `site/`.
