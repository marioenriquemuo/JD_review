# Automated Job Analysis & Asset Engine

Manual ingest of a job posting via a Chrome extension. n8n deduplicates against Notion for $0, triages with Claude Haiku, runs a **Phase 1 semantic gap audit** (Haiku), then **pauses** for your Candidate notes. **Continue Phase 2** applies Sonnet **line patches** to `secrets/master_cv.tex`; Python writes the CV. Cover letter is not generated in v1.

API keys, Notion tokens, and Notion page/DB IDs are **not** stored in the workflow export. They live in gitignored [`secrets/notion_ids.json`](secrets/notion_ids.json) and load at runtime via SSH (**Load Secret IDs**). Import [`JD Flow.json`](JD Flow.json) and attach **Notion account** + **SSH localhost** locally.

Source graph: [`mearmaid.txt`](mearmaid.txt). Setup: [`docs/SETUP.md`](docs/SETUP.md). ELI5: [`docs/ELI5.md`](docs/ELI5.md). **Beginner walkthrough:** [`docs/BEGINNER_GUIDE.md`](docs/BEGINNER_GUIDE.md).

## Architecture principles

- **Zero-risk ingest.** You click the extension on a JD tab, or **Upload PDF**. Nothing crawls the open web. Claude receives markdown only (never PDF bytes).
- **Secrets outside the canvas.** Notion IDs and the Anthropic `x-api-key` are read from `secrets/notion_ids.json` on each run.
- **Deterministic dedup.** Notion is queried by `Job URL` before any LLM call.
- **Two-tier LLM routing.** Haiku scores fit. Haiku Phase 1 runs only when `fit_score >= 70`. Sonnet runs only on Continue Phase 2.
- **Honest feedback loop.** Phase 1 audits gaps and asks questions; Phase 2 uses only your CV + Candidate notes (no invented metrics).
- **Python owns the `.tex` shell.** Sonnet returns line patches; `assemble_tex.py --cv-only` applies them and restores missing `\begin{itemize}` / `\end{itemize}`. Notion **LaTex CV** holds a 1,900-char preview.
- **ATS-parseable master CV.** `secrets/master_cv.tex` is the only CV source of truth. Phase 2 must not merge EDUCATION / CERTIFICATIONS / LANGUAGES / SKILLS. Details: [`docs/SETUP.md`](docs/SETUP.md#master-cv-ats).

## Flow

```text
Chrome extension (URL + HTML, or Upload PDF)
  → n8n Webhook POST /webhook/job-ingest  (waits; responseNode)
  → Pack Ingest
       pdf_b64 → extract_pdf.py → { url, clean_md }
       else    → Parse Clean MD
  → SSH Load Secret IDs
  → Notion Applications DB lookup by Job URL
       duplicate → Respond { status: duplicate }  ($0)
       new      → distill_cv.py --verify-json (from secrets/master_cv.tex)
  → Claude Haiku triage
       fit < 70  → Notion Skipped → Respond { status: skipped }
       fit >= 70 → Style & Learnings + derived CV markdown
  → Claude Haiku Phase 1 (semantic gap audit + questions)
  → Notion row Status=Needs Context (Candidate notes seeded with questions)
  → Persist secrets/runs/{page_id}.json
  → Respond { status: needs_context }

You: fill **Candidate Answers** → extension **Continue Phase 2**
  → POST /webhook/job-resume (same Job URL)
  → Status=Generating
  → Claude Sonnet Phase 2 (latex_cv_patches on numbered master)
  → assemble_tex.py --cv-only (apply patches + repair itemize) → ~/Downloads
  → Notion Status=Ready to Apply + LaTex CV preview
  → popup: ready_to_apply + cv_path
```

## Models and unit economics

| Stage | When | Model | Est. cost |
| --- | --- | --- | --- |
| Dedup | Every run | Notion | $0 |
| Triage fail | fit &lt; 70 | `claude-haiku-4-5` | ~$0.005 |
| Phase 1 audit | fit ≥ 70 | `claude-haiku-4-5` | ~$0.01–0.02 |
| Phase 2 patches | After Continue Phase 2 | `claude-sonnet-5` | ~$0.03–0.08 |
| Full pass | Qualified + resume | Haiku ×2 + Sonnet patches | **target ≤ $0.10** |

Webhook JSON includes `usage_triage` / `usage_phase1` / `usage_phase2` token counts. Cover letter (Phase 3) is not called in v1.

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
| Candidate notes | rich_text | Phase 1 questions (seeded); on **Skipped**, Haiku gaps |
| Candidate Answers | rich_text | Your answers to those questions |
| LaTex CV | rich_text | Preview ≤1900 chars (full file in Downloads) |
| LaTex Cover Letter | rich_text | Unused in v1 (empty) |

### Context pages / local secrets

| Path / page | Role |
| --- | --- |
| Notion Style & Learnings | Tone rules for Phase 1–2 |
| `secrets/master_cv.tex` | Only CV source of truth (runtime distill + Phase 2 patches) |
| `secrets/runs/{page_id}.json` | Phase 1 state for resume |
| `secrets/notion_ids.json` | DB/page IDs + `anthropic_api_key` (`master_cv_page_id` optional) |

## Repo layout

| Path | What |
| --- | --- |
| [`JD Flow.json`](JD Flow.json) | n8n workflow export |
| [`scripts/extract_pdf.py`](scripts/extract_pdf.py) | PDF bytes → `{ url, clean_md }` only |
| [`scripts/assemble_tex.py`](scripts/assemble_tex.py) | `--cv-only` / `--number` / patch apply / repair itemize |
| [`scripts/distill_cv.py`](scripts/distill_cv.py) | Runtime `--verify-json` markdown + fact gate |
| [`scripts/persist_run.py`](scripts/persist_run.py) | Save/load Phase 1 run JSON |
| [`scripts/load_secret_ids.py`](scripts/load_secret_ids.py) | Print IDs + Claude key |
| [`chrome-extension/`](chrome-extension/) | MV3 extension (popup shows skip / needs_context) |

## Assumptions

- Extension waits for Phase 1 (tens of seconds). Popup shows `Scoring…` then the real status.
- **Upload PDF** is for text PDFs only (no OCR). Dedup URL is `https://jd-flow.local/pdf/<sha256>`.
- Empty Candidate Answers + Continue Phase 2 still patches from the master CV only (no invented facts).
- Phase 2 starts from the extension **Continue Phase 2** button (not a Notion poll).
- Phase 2 may reorder **CERTIFICATIONS** to match the JD. Degree entries stay fixed. It must not merge EDUCATION / CERTIFICATIONS / LANGUAGES / SKILLS or turn education into nested bullets.
- After you edit `secrets/master_cv.tex`, the next ingest re-distills it. No Notion Master CV paste.
- If Phase 2 patches drop `\begin{itemize}` / `\end{itemize}`, `repair_lists` in `assemble_tex.py` puts them back. Check the first experience block after Continue.
- Fit threshold is hard-coded at 70.
