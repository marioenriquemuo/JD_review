# Automated Job Analysis & Asset Engine

Manual ingest of a job posting via a Chrome extension. n8n deduplicates against Notion for $0, triages with Claude Haiku, and only then spends Sonnet tokens on CV bullets, cover letter, interview flashcards, and a company dossier.

API keys and Notion tokens are **not** in this repo. Import [`JD Flow.json`](JD Flow.json) into n8n and attach credentials locally.

Source graph: [`mearmaid.txt`](mearmaid.txt). Importable workflow: [`JD Flow.json`](JD Flow.json). Setup click-path: [`docs/SETUP.md`](docs/SETUP.md). ELI5 walkthrough: [`docs/ELI5.md`](docs/ELI5.md).

## Architecture principles

- **Zero-risk ingest.** You click the extension on a JD tab. Nothing crawls the open web.
- **Deterministic dedup.** Notion is queried by `Job URL` before any LLM call. Duplicates stop the workflow and do **not** create a second row.
- **Two-tier LLM routing.** Haiku scores fit. Sonnet runs only when `fit_score >= 70`.
- **Feedback injection.** Distilled style rules from a Notion page go into the Sonnet prompt. Raw application logs and the full writing CSV do not.

## Flow

```text
Chrome extension (URL + HTML)
  → n8n Webhook POST /webhook/job-ingest
  → Code node HTML → Markdown
  → Notion Applications DB lookup by Job URL
       duplicate → stop ($0)
       new      → Get Master CV page
  → Claude Haiku triage (JSON: title, company, skills, location, fit_score, rationale)
       fit < 70  → Notion row Status=Skipped  (~$0.004)
       fit >= 70 → Get Style & Learnings
  → Claude Sonnet (one JSON: bullets, letter, flashcards, dossier, salary)
  → Claude Sonnet LaTeX (fragments from those bullets/letter only)
  → Notion row Status=Ready to Apply  (~$0.045 total)
```

The mermaid H1–H4 boxes are fields from **one** Sonnet response, not four model calls. LaTeX columns are a **second** Sonnet call that only translates those bullets/letter — not another mermaid model box.

## Models and unit economics

Claude 3.5 Haiku is retired on the Claude API. This project uses the current cheap/fast and high-reasoning pair:

| Stage | When | Model | Est. tokens | Est. cost |
| --- | --- | --- | --- | --- |
| Dedup | Every run | Python + Notion | 0 LLM | $0.000 |
| Triage fail | New JD, fit &lt; 70 | `claude-haiku-4-5` | ~2,500 in / 300 out | ~$0.004 |
| Assets | fit &gt;= 70 | `claude-sonnet-5` | ~3,500 in / 2,000 out | ~$0.027 |
| LaTeX | after assets | `claude-sonnet-5` | ~800 in / 1,200 out | ~$0.014 |
| Full pass | Qualified JD | Haiku + two Sonnets | — | **~$0.045** |

Prices from [Anthropic API pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Haiku 4.5 $1/$5 per MTok, Sonnet 5 $2/$10 per MTok). Recalculate if you change models.

## Notion

### Applications DB

Title property: **Job Title**.

| Property | Type | Role |
| --- | --- | --- |
| Job Title | title | Parsed title |
| Job URL | url | Dedup key |
| Company | rich_text | Parsed company |
| Location | rich_text | Location / remote |
| Skills | rich_text | Comma-separated |
| Fit Score | number | 0–100 |
| Status | select | `Skipped`, `Ready to Apply` |
| Rationale | rich_text | Two-sentence Haiku reason |
| Salary Range | rich_text | Number range or estimate |
| Salary Flag | select | `extracted`, `UNVERIFIED Estimate` |
| LaTex CV | rich_text | LaTeX fragment of CV sections to paste into the master `.tex` |
| LaTex Cover Letter | rich_text | LaTeX fragment of the letter body to paste into the master letter |

Long assets (CV bullets, cover letter, flashcards, dossier) are written into the **page body**, not properties — Notion property values cap at 2,000 characters. **LaTex CV** and **LaTex Cover Letter** are section fragments (capped ~1,900 chars), not a full `\documentclass` dump.

`Status=Duplicate` is not written. A hit on `Job URL` ends the execution; n8n’s execution log is the duplicate record.

### Context pages

| Page | Injected into | Content |
| --- | --- | --- |
| Master CV | Haiku (first ~2,500 chars) and Sonnet (full) | Distilled Markdown from your LaTeX CV |
| Style & Learnings | Sonnet only | 10–20 rules distilled from past writing |

Do not paste the raw `.tex` or writing CSV into these pages. Generate drafts with [`scripts/distill_cv.py`](scripts/distill_cv.py).

## Repo layout

| Path | What |
| --- | --- |
| [`JD Flow.json`](JD Flow.json) | n8n workflow export |
| [`chrome-extension/`](chrome-extension/) | Unpacked MV3 extension |
| [`scripts/clean_html.py`](scripts/clean_html.py) | HTML → Markdown (called by n8n) |
| [`scripts/distill_cv.py`](scripts/distill_cv.py) | One-time LaTeX + CSV → Notion drafts |
| [`docs/SETUP.md`](docs/SETUP.md) | n8n, Python, Notion, Claude Console, Chrome |
| [`tests/sample_ingest.json`](tests/sample_ingest.json) | Smoke-test payload for `clean_html.py` |

## Assumptions that affect cost or quality

- Extension sends **HTML**, not `innerText`, so BeautifulSoup actually reduces tokens.
- Master CV and style rules are static Notion pages you maintain. The workflow does not learn from Skipped rows automatically.
- Fit threshold is hard-coded at 70 in the n8n IF node.
- Webhook responds immediately with `{ "status": "accepted" }`. Duplicate vs skip vs ready is visible in n8n executions and Notion, not in the extension popup.
