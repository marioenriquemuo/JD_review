# Automated Job Analysis & Asset Engine

Manual ingest of a job posting via a Chrome extension. n8n deduplicates against Notion for $0, triages with Claude Haiku, runs a **Phase 1 semantic gap audit**, then **pauses** for your Candidate notes. When you set Status to **Proceed Phase 2**, Sonnet writes a **full** tailored LaTeX CV and cover letter.

API keys, Notion tokens, and Notion page/DB IDs are **not** stored in the workflow export (except the Applications DB id on the Notion Trigger). They live in gitignored [`secrets/notion_ids.json`](secrets/notion_ids.json) and load at runtime via SSH (**Load Secret IDs**). Import [`JD Flow.json`](JD Flow.json) and attach **Notion account** + **SSH localhost** locally.

Source graph: [`mearmaid.txt`](mearmaid.txt). Setup: [`docs/SETUP.md`](docs/SETUP.md). ELI5: [`docs/ELI5.md`](docs/ELI5.md). **Beginner walkthrough:** [`docs/BEGINNER_GUIDE.md`](docs/BEGINNER_GUIDE.md).

## Architecture principles

- **Zero-risk ingest.** You click the extension on a JD tab. Nothing crawls the open web.
- **Secrets outside the canvas.** Notion IDs and the Anthropic `x-api-key` are read from `secrets/notion_ids.json` on each run.
- **Deterministic dedup.** Notion is queried by `Job URL` before any LLM call.
- **Two-tier LLM routing.** Haiku scores fit. Sonnet runs only when `fit_score >= 70`.
- **Honest feedback loop.** Phase 1 audits gaps and asks questions; Phase 2/3 use only your CV + Candidate notes (no invented metrics).
- **Full LaTeX, not patches.** Complete compilable `.tex` files go to Downloads; Notion columns hold a 1,900-char preview (Notion property cap).

## Flow

```text
Chrome extension (URL + HTML)
  → n8n Webhook POST /webhook/job-ingest  (waits; responseNode)
  → Pack Ingest / Parse Clean MD
  → SSH Load Secret IDs
  → Notion Applications DB lookup by Job URL
       duplicate → Respond { status: duplicate }  ($0)
       new      → Get Master CV page
  → Claude Haiku triage
       fit < 70  → Notion Skipped → Respond { status: skipped }
       fit >= 70 → Style & Learnings + master_cv.tex
  → Claude Sonnet Phase 1 (semantic gap audit + questions)
  → Notion row Status=Needs Context (Candidate notes seeded with questions)
  → Persist secrets/runs/{page_id}.json
  → Respond { status: needs_context }

You: fill **Candidate Answers** → extension **Continue Phase 2**
  → POST /webhook/job-resume (same Job URL)
  → Status=Generating
  → Claude Sonnet Phase 2 (full CV .tex) → Phase 3 (full letter .tex)
  → assemble_tex.py --write-full → ~/Downloads
  → Notion Status=Ready to Apply + LaTex CV / LaTex Cover Letter previews
  → popup: ready_to_apply + file paths
```

## Models and unit economics

| Stage | When | Model | Est. cost |
| --- | --- | --- | --- |
| Dedup | Every run | Notion | $0 |
| Triage fail | fit &lt; 70 | `claude-haiku-4-5` | ~$0.004 |
| Phase 1 audit | fit ≥ 70 | `claude-sonnet-5` | ~$0.03 |
| Phase 2+3 | After Proceed Phase 2 | `claude-sonnet-5` ×2 | ~$0.06–0.10 |
| Full pass | Qualified + resume | Haiku + 3 Sonnets | **~$0.10–0.14** |

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
| Status | select | `Skipped`, `Needs Context`, `Generating`, `Proceed Phase 2`, `Ready to Apply` |
| Rationale | rich_text | Two-sentence Haiku reason |
| Salary Range | rich_text | Number range or estimate |
| Salary Flag | select | `extracted`, `UNVERIFIED Estimate` |
| Candidate notes | rich_text | Phase 1 questions (seeded) |
| Candidate Answers | rich_text | Your answers to those questions |
| LaTex CV | rich_text | Preview ≤1900 chars (full file in Downloads) |
| LaTex Cover Letter | rich_text | Preview ≤1900 chars |

### Context pages / local secrets

| Path / page | Role |
| --- | --- |
| Notion Master CV | Distilled Markdown for Haiku |
| Notion Style & Learnings | Tone rules for Sonnet |
| `secrets/master_cv.tex` | Full LaTeX master for Phase 1–2 |
| `secrets/storytelling.md` | Phase 3 letter structure |
| `secrets/runs/{page_id}.json` | Phase 1 state for resume |
| `secrets/notion_ids.json` | DB/page IDs + `anthropic_api_key` |

## Repo layout

| Path | What |
| --- | --- |
| [`JD Flow.json`](JD Flow.json) | n8n workflow export |
| [`scripts/assemble_tex.py`](scripts/assemble_tex.py) | `--write-full` / patch / `--number` |
| [`scripts/persist_run.py`](scripts/persist_run.py) | Save/load Phase 1 run JSON |
| [`scripts/load_secret_ids.py`](scripts/load_secret_ids.py) | Print IDs + Claude key |
| [`chrome-extension/`](chrome-extension/) | MV3 extension (popup shows skip / needs_context) |

## Assumptions

- Extension waits for Phase 1 (tens of seconds). Popup shows `Scoring…` then the real status.
- Empty Candidate Answers + Proceed Phase 2 still generates files from the master CV only (no invented facts).
- Phase 2 starts from the extension **Continue Phase 2** button (not a Notion poll).
- Fit threshold is hard-coded at 70.
