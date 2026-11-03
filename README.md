# Automated Job Analysis & Asset Engine

Manual ingest of a job posting via a **Chrome** or **Firefox** extension. n8n deduplicates against Notion for $0 and triages with Claude Haiku. Fit **80 or above** is queued for a CV. Fit **70–79** stays **Held** (no file until you promote it). **Continue Phase 2** applies Sonnet **line patches** to `secrets/master_cv.tex`; Python writes the CV. **Write cover letter** is a second click after Ready to Apply (Sonnet letter body only; Python splices `secrets/master_letter.tex`).

API keys, Notion tokens, and Notion page/DB IDs are **not** stored in the workflow export. They live in gitignored [`secrets/notion_ids.json`](secrets/notion_ids.json) and load at runtime via SSH (**Load Secret IDs**). Import [`JD Flow.json`](JD Flow.json) and attach **Notion account** + **SSH localhost** locally.

Source graph: [`mearmaid.txt`](mearmaid.txt). Setup: [`docs/SETUP.md`](docs/SETUP.md). ELI5: [`docs/ELI5.md`](docs/ELI5.md). **Beginner walkthrough:** [`docs/BEGINNER_GUIDE.md`](docs/BEGINNER_GUIDE.md).

## Architecture principles

- **Zero-risk ingest.** You click the extension on a JD tab, or **Upload PDF**. Nothing crawls the open web. Claude receives markdown only (never PDF bytes).
- **Secrets outside the canvas.** Notion IDs and the Anthropic `x-api-key` are read from `secrets/notion_ids.json` on each run.
- **Deterministic dedup.** Notion is queried by `Job URL` before any LLM call.
- **Two-tier LLM routing.** Haiku scores fit. Sonnet Phase 2 runs when you resume a **Proceed Phase 2** row. Sonnet Phase 3 runs only on **Write cover letter**. Haiku Phase 1 is unhooked.
- **Honest feedback loop.** The CV uses the master CV and `secrets/facts.md`. Candidate Answers may be empty. Lines under `Never claim` stay off the CV. You review the `.tex` before you send it.
- **Python owns the `.tex` shell.** Sonnet returns line patches; `assemble_tex.py --cv-only` applies them and restores missing `\begin{itemize}` / `\end{itemize}`. Letter click uses `--letter-only` (body into `master_letter.tex`). Notion **LaTex CV** / **LaTex Cover Letter** hold 1,900-char previews.
- **ATS-parseable master CV.** `secrets/master_cv.tex` is the only CV source of truth. Phase 2 must not merge EDUCATION / CERTIFICATIONS / LANGUAGES / SKILLS. Details: [`docs/SETUP.md`](docs/SETUP.md#master-cv-ats).

## Flow

```text
Chrome / Firefox extension (URL + HTML, or Upload PDF)
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
       fit >= 70 → Style & Learnings
  → Band Fit (WRITE_AT = 80)
       70–79 → Notion Held, notes "- none", persist run, Respond { status: held }
       >= 80 → Notion Proceed Phase 2, notes "- none", persist run, Respond { status: proceed }

You: for Held, set that one row to **Proceed Phase 2**
  python3 scripts/resume_phase2.py
  → POST /webhook/job-resume (same Job URL)
  → Status=Generating
  → SSH cat secrets/facts.md again
  → Claude Sonnet Phase 2 (latex_cv_patches on numbered master; FACTS + this row's answers)
  → assemble_tex.py --cv-only (apply patches + repair itemize) → humanize_tex.py --kind cv → ~/Downloads
  → persist latex_cv_patches + cv_path
  → Notion Status=Ready to Apply + LaTex CV preview + CV File basename
  → popup: ready_to_apply + cv_path

Optional, no Claude: `python3 scripts/stamp_cv.py ~/Downloads/<source>_CV.tex`
  copies that file onto the other three Operator Equity coordinator titles
  (header line only). It does not change Notion.

Morning list, no extension button. This matches the n8n workflow that is running today (it still returns needs_context):
  python3 scripts/discover_jobs.py
  # then Execute workflow on Mail Discover in n8n (unread Gmail/Outlook → discovery files only)
  python3 scripts/ingest_new_jobs.py
  python3 scripts/answer_candidates.py   # maps Candidate notes onto secrets/facts.md; sets Proceed Phase 2
  python3 scripts/resume_phase2.py       # writes those rows
  Mail Discover only updates secrets/discovery_*.* — it does not call job-ingest.
  ingest posts each NEW row that is not in secrets/discovery_filed.json to /webhook/job-ingest.
  It does not start Phase 2. Rows already marked already are left alone.
  Re-import JD Flow.json before dropping answer_candidates. Until that import, fit >= 70 stays Needs Context, including scores over 80, and resume_phase2 sees an empty queue.
  After that import: 70–79 is Held (`resume_phase2.py --held`), 80 or above is Proceed Phase 2, and answer_candidates is only for leftover Needs Context rows. After five mornings, if you promote more than half of the Held rows, set WRITE_AT back to 70 in the Band Fit node.

Optional: set Notion Status to **Write Cover Letter** (exactly one row) → extension **Write cover letter**
  → POST /webhook/job-resume { write_letter: true }  (finds that row; does not re-run Phase 2)
  → cat patched CV + storytelling.md → Sonnet Phase 3 (Hook / Mechanism / Bridge / Proof / Close)
  → assemble_tex.py --letter-only (body + Date/To/Company/Location/Position) → humanize_tex.py --kind letter → ~/Downloads *_CoverLetter.tex
  → Notion LaTex Cover Letter preview (Status back to Ready to Apply)
```

## Models and unit economics

| Stage | When | Model | Est. cost |
| --- | --- | --- | --- |
| Dedup | Every run | Notion | $0 |
| Triage fail | fit &lt; 70 | `claude-haiku-4-5` | ~$0.005 |
| Phase 2 patches | After resume, fit ≥ 80 or a promoted Held row | `claude-sonnet-5` | ~$0.03–0.08 |
| Phase 3 letter | After **Write cover letter** (opt-in) | `claude-sonnet-5` | extra Sonnet call |
| Full pass | Queued + resume | Haiku triage + Sonnet patches | **target ≤ $0.10** (letter not included) |

Webhook JSON includes `usage_triage` / `usage_phase1` / `usage_phase2` token counts, plus `usage_phase3` after a letter click. Continue Phase 2 stays CV-only.

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
| Status | select | `Skipped`, `Needs Context`, `Generating`, `Held`, `Proceed Phase 2`, `Ready to Apply`, `Write Cover Letter`, `Applied` |
| Rationale | rich_text | Two-sentence Haiku reason |
| Salary Range | rich_text | Number range or estimate |
| Salary Flag | select | `extracted`, `UNVERIFIED Estimate` |
| Candidate notes | rich_text | `- none` on Held and Proceed Phase 2. Old **Needs Context** rows may still list questions. |
| Candidate Answers | rich_text | Your answers to those questions |
| LaTex CV | rich_text | Preview ≤1900 chars (full file in Downloads) |
| CV File | rich_text | Downloads basename to upload (`Company_Title_CV.tex`) |
| LaTex Cover Letter | rich_text | Preview after **Write cover letter** (empty until then) |

### Context pages / local secrets

| Path / page | Role |
| --- | --- |
| Notion Style & Learnings | Tone rules for Phase 1–2. Not the fact card. |
| `secrets/facts.md` | Answered facts and `Never claim`. Gitignored. Phase 1 and Phase 2 read it. |
| `secrets/master_cv.tex` | Only CV source of truth (runtime distill + Phase 2 patches) |
| `secrets/master_letter.tex` | Letter shell (`% LETTER_BODY` / `% END_LETTER_BODY`); required for letter click |
| `secrets/storytelling.md` | Phase 3 voice/structure; required for letter click |
| `secrets/runs/{page_id}.json` | Phase 1 state; Phase 2 merges `latex_cv_patches` + `cv_path` |
| `secrets/notion_ids.json` | DB/page IDs + `anthropic_api_key` (`master_cv_page_id` optional) |

## Repo layout

| Path | What |
| --- | --- |
| [`JD Flow.json`](JD Flow.json) | n8n workflow export |
| [`scripts/extract_pdf.py`](scripts/extract_pdf.py) | PDF bytes → `{ url, clean_md }` only |
| [`scripts/assemble_tex.py`](scripts/assemble_tex.py) | `--cv-only` / `--letter-only` / `--number` / patch apply / repair itemize |
| [`scripts/humanize_tex.py`](scripts/humanize_tex.py) | After assemble: human-text voice pass + Never-claim fallback |
| [`scripts/stamp_cv.py`](scripts/stamp_cv.py) | Copy one coordinator CV onto the other three Operator Equity titles |
| [`scripts/discover_jobs.py`](scripts/discover_jobs.py) | Poll public boards; write `secrets/discovery_latest.md` |
| [`scripts/discover_mail.py`](scripts/discover_mail.py) | Scan mail-drop JSON; append title matches to discovery files |
| [`scripts/ingest_new_jobs.py`](scripts/ingest_new_jobs.py) | POST NEW unfiled discovery rows to `/webhook/job-ingest` only |
| [`scripts/answer_candidates.py`](scripts/answer_candidates.py) | Morning step while n8n still returns needs_context. Maps questions onto `secrets/facts.md`, asks only real gaps, sets Proceed Phase 2. |
| [`scripts/resume_phase2.py`](scripts/resume_phase2.py) | `--held` lists Held rows. Default POSTs `/webhook/job-resume` for each Proceed Phase 2 row. |
| [`scripts/backfill_cv_file.py`](scripts/backfill_cv_file.py) | `--schema` adds Status **Applied** and **Held**. Default also writes CV basenames. |
| [`scripts/distill_cv.py`](scripts/distill_cv.py) | Runtime `--verify-json` markdown + fact gate |
| [`scripts/persist_run.py`](scripts/persist_run.py) | Save/load run JSON (`--write` merges onto existing) |
| [`scripts/load_secret_ids.py`](scripts/load_secret_ids.py) | Print IDs + Claude key |
| [`chrome-extension/`](chrome-extension/) | Chrome MV3 (popup shows skip / needs_context) |
| [`firefox-extension/`](firefox-extension/) | Same popup; install the signed `.xpi` |

## Assumptions

- Extension waits for triage (tens of seconds). Popup shows `Scoring…` then skipped, held, or proceed.
- **Upload PDF** is for text PDFs only (no OCR). Dedup URL is `https://jd-flow.local/pdf/<sha256>`.
- Empty Candidate Answers + Continue Phase 2 still patches from the master CV and `secrets/facts.md`. It does not invent past those. A missing or empty `facts.md` stops the run.
- Phase 2 starts from `python3 scripts/resume_phase2.py` (or the extension **Continue Phase 2** button) on **Proceed Phase 2** rows. Cover letter: set Status to **Write Cover Letter** on one row, then click **Write cover letter**. It fails if Phase 2 has not written `cv_path` / patches.
- Phase 2 may reorder **CERTIFICATIONS** to match the JD. Degree entries stay fixed. It must not merge EDUCATION / CERTIFICATIONS / LANGUAGES / SKILLS or turn education into nested bullets.
- After you edit `secrets/master_cv.tex`, the next ingest re-distills it. No Notion Master CV paste.
- If Phase 2 patches drop `\begin{itemize}` / `\end{itemize}`, `repair_lists` in `assemble_tex.py` puts them back. Check the first experience block after Continue.
- After assemble, `humanize_tex.py` rewrites spans. A Never-claim hit replaces the Downloads CV with a copy of `secrets/master_cv.tex`; the letter reverts to the pre-humanize file.
- Fit under 70 is Skipped. `WRITE_AT` in the Band Fit node is 80: that score and above are queued. 70–79 are Held.
