# Setup

Do these in order. Do not put API keys in the repo.

Replace `PROJECT` with:

`/home/mario/Documents/n8n/Nuevo trabajo`

---

## 1. Python libraries

Debian/Ubuntu blocks system `pip`. Use a project venv (this is what the n8n Execute Command node calls):

```bash
python3 -m venv "$PROJECT/.venv"
"$PROJECT/.venv/bin/pip" install beautifulsoup4 html2text pypdf
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/clean_html.py" --in "$PROJECT/tests/sample_ingest.json"
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/extract_pdf.py" --pdf "$PROJECT/tests/sample_jd.pdf" --url "https://jd-flow.local/pdf/sample"
```

Expect JSON on stdout with `url` and `clean_md`. `clean_md` must not contain the sample `<script>` or `<nav>` text `Ignore this nav`. The PDF check must print the sentence starting `Senior Python Engineer` and no other JSON keys.

Runtime distill (Haiku reads this JSON; do not paste markdown into Notion):

```bash
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/distill_cv.py" --tex "$PROJECT/secrets/master_cv.tex" --verify-json
```

Expect `"ok": true`. If `"missing"` is non-empty, facts were dropped — fix the `.tex` or the converter before ingest. Optional `--csv` / `--out-dir` still drafts Style & Learnings; without `--csv`, `style_learnings.md` is a placeholder — do not overwrite a real Style page with it.

Copy the original `.tex` locally (gitignored):

```bash
mkdir -p "$PROJECT/secrets"
cp /path/to/cv.tex "$PROJECT/secrets/master_cv.tex"
```

After **Continue Phase 2**, the patched CV lands in `/home/mario/Downloads/{company}_{job_title}_CV.tex`. After **Write cover letter**, `{company}_{job_title}_CoverLetter.tex` is written the same way (requires `secrets/master_letter.tex` and `secrets/storytelling.md`).

### Master CV (ATS)

Workday, Greenhouse, Taleo, and Lever map PDF text to form fields from **standalone headings**. Combined titles (`EDUCATION, CERTIFICATIONS & SKILLS`), nested bullets, and `Degree | School (Year)` pipes leave Education/Certifications empty.

Required `\section*` titles (each on its own line, never merged):

- `EDUCATION` — programs with a start–end range (school + dates, credential on the next line)
- `CERTIFICATIONS` — issued, non-expired credentials (issuer + name + date). No credential IDs (parsers treat them as dates).
- `LANGUAGES`
- `SKILLS`

Date ranges use an ASCII hyphen (`2014 - 2015`), not LaTeX `--` (en-dashes often extract as a gap). Preamble must include `lmodern` + `cmap` so `fi` ligatures extract as `Effective` / `Certificate` / `Proficient`, not `Ective` / `Certicate`.

Phase 2 (`Sonnet Phase 2` in [`JD Flow.json`](../JD Flow.json)) returns line patches only. It may reorder certifications to match the JD; degree entries stay fixed; it must not nest or merge those four sections. `assemble_tex.py --cv-only` applies patches and restores missing `\begin{itemize}` / `\end{itemize}`. Phase 3 is opt-in: Sonnet returns `{ "latex_cover_letter": "<body>" }` only; `assemble_tex.py --letter-only` splices `secrets/master_letter.tex`.

Compile and check extractable text before uploading a PDF to an ATS:

```bash
sudo apt install texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-lang-spanish poppler-utils
mkdir -p /tmp/jd-cv-pdf
pdflatex -interaction=nonstopmode -output-directory=/tmp/jd-cv-pdf "$PROJECT/secrets/master_cv.tex"
pdftotext -layout /tmp/jd-cv-pdf/master_cv.pdf - | sed -n '/EDUCATION/,$p'
```

Expect four headings on their own lines, four education blocks, nine certification lines, and the words `Effective`, `Certificate`, `Proficient`. Tailored Downloads `.tex` files need the same compile step before you apply. If one ATS still leaves Education empty, use a `.docx` fallback for that employer only.

---

## 2. Claude Console

1. Open [console.anthropic.com](https://console.anthropic.com).
2. **API keys** → create a key. Copy it once.
3. **Settings → limits** (or Plans & Billing): set a monthly spend cap.
4. Confirm models `claude-haiku-4-5` and `claude-sonnet-5` are available on your account.

Put the key in `$PROJECT/secrets/notion_ids.json` as `anthropic_api_key`. Claude HTTP nodes read it via **Load Secret IDs** (no Header Auth credential required).

---

## 3. Notion

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New integration** (internal). Copy the token.
2. Create database **Applications** with the properties in [README.md](../README.md) (title = Job Title).
3. **Status** select must include exactly: `Skipped`, `Needs Context`, `Generating`, `Proceed Phase 2`, `Ready to Apply`, `Write Cover Letter`.
4. Add **Candidate notes** (Text / rich_text) if missing.
5. Create page **Style & Learnings**. Paste tone rules (optional distill `--csv` draft). Share the Applications DB and this page with the integration. A Notion Master CV page is unused (source of truth is `secrets/master_cv.tex`).
6. Share the database and the Style page with the integration (**Connect to**).
7. Copy IDs from the URLs:
   - Database: `https://notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...` → 32 hex chars (optionally insert dashes as `8-4-4-4-12`).
   - Page: the 32 hex chars after the page title slug.

In n8n: **Credentials → Notion API** → Internal integration token.

Put IDs and the Claude key in `$PROJECT/secrets/notion_ids.json` (`applications_db_id`, `style_learnings_page_id`, `anthropic_api_key`; `master_cv_page_id` optional/unused). The workflow loads them at runtime via SSH (**Load Secret IDs**).

Select the Notion credential on every Notion node. Select **SSH localhost** on Load Secret IDs / Distill Master CV / Persist Run State / Write Full Tex / Read Master Tex Resume.

---

## 4. n8n (self-hosted, this machine)

1. Import [`JD Flow.json`](../JD Flow.json): **Workflows → Import from File**. If **JD Flow** is already listed, open **Sonnet Phase 2** and confirm the system prompt contains `latex_cv_patches` and `Preserve EDUCATION, CERTIFICATIONS, LANGUAGES, and SKILLS as separate sections.` If that is missing, import the file again, re-attach credentials, Save.
2. Confirm **Execute Command** on **Clean HTML** points at the venv interpreter:

```text
/home/mario/Documents/n8n/Nuevo trabajo/.venv/bin/python "/home/mario/Documents/n8n/Nuevo trabajo/scripts/clean_html.py" --b64 '{{ $json.b64 }}'
```

If n8n runs in Docker, mount `PROJECT` (including `.venv`) into the container or change the command. The n8n process user must be able to execute that venv Python.

3. Attach credentials (step 2–3). Confirm `secrets/notion_ids.json` exists (IDs load via SSH).
4. **Webhook** node: production URL is `http://localhost:5678/webhook/job-ingest`. Inactive workflows use `http://localhost:5678/webhook-test/job-ingest` and require **Test workflow** in the editor.
5. Save. Set **Active** only after credentials and the secrets file are set.

If Execute Command is blocked in your n8n install, swap **Clean HTML** for a Code node that shells out the same script, or enable the Python task runner and paste the body of `clean_html.py` (allowlist `bs4`, `html2text`, `re`, `json`, `argparse`, `sys`, `base64`). Prefer Execute Command on local n8n.

### First test POST (no extension)

```bash
curl -sS -X POST http://localhost:5678/webhook-test/job-ingest \
  -H 'Content-Type: application/json' \
  -d @"$PROJECT/tests/sample_ingest.json"
```

Expect `{ "status": "skipped" }` or `{ "status": "needs_context" }` (the webhook **waits**; it is not instant `accepted`). Then open **Executions**:

- First run: popup shows `skipped` or `needs_context`. Notion **Skipped** or **Needs Context**.
- Same `url` again: popup `Already filed.`
- After **Candidate Answers** + extension **Continue Phase 2**: Downloads `{company}_{title}_CV.tex` and Notion **Ready to Apply**.
- After **Write cover letter**: Downloads `{company}_{title}_CoverLetter.tex`; Status stays **Ready to Apply**. Fails with Continue Phase 2 first if you skipped Phase 2.

---

## 5. Chrome extension

1. Chrome → `chrome://extensions` → **Developer mode** → **Load unpacked** → select `$PROJECT/chrome-extension` (reload if already loaded).
2. Extension **Details → Extension options**. Set webhook URL:
   - Active workflow: `http://localhost:5678/webhook/job-ingest`
   - Testing in editor: `http://localhost:5678/webhook-test/job-ingest`
3. Open a job posting → click the extension → **Send job to n8n**.
4. Popup shows `Scoring…` then `Skipped…` / `Already filed…` / `Needs Context…`.

To allow a non-localhost n8n URL, add it to `host_permissions` in [`chrome-extension/manifest.json`](../chrome-extension/manifest.json) and reload the extension.

---

## Checklist

- [ ] `secrets/master_cv.tex` present; `distill_cv.py --verify-json` returns `"ok": true`
- [ ] For letters: `secrets/master_letter.tex` (`% LETTER_BODY` markers) and `secrets/storytelling.md`
- [ ] Master CV `.tex` has separate EDUCATION / CERTIFICATIONS / LANGUAGES / SKILLS
- [ ] `pdftotext` of the compiled PDF shows those four headings and `Effective` / `Certificate` / `Proficient`
- [ ] **Sonnet Phase 2** prompt includes `latex_cv_patches` and Preserve EDUCATION… (re-import `JD Flow.json` if not)
- [ ] `anthropic_api_key` in `secrets/notion_ids.json`; spend cap set in Anthropic console
- [ ] Applications DB Status options include Needs Context / Proceed Phase 2 / Generating
- [ ] **Candidate notes** property exists
- [ ] Applications DB + Style & Learnings shared with the integration
- [ ] Import latest `JD Flow.json`; Notion + SSH credentials attached
- [ ] Workflow **Active**; extension uses `/webhook/job-ingest`
- [ ] Reload Chrome extension so popup status messages update
