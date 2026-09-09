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

Optional CV distill (your files, not in git):

```bash
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/distill_cv.py" --tex /path/to/cv.tex --csv /path/to/writing.csv --out-dir /tmp/jd-distill
```

Paste `/tmp/jd-distill/master_cv.md` into the Notion **Master CV** page and `/tmp/jd-distill/style_learnings.md` into **Style & Learnings**. Edit before use.

Copy the original `.tex` locally (gitignored). Notion stays Markdown-only:

```bash
mkdir -p "$PROJECT/secrets"
cp /path/to/cv.tex "$PROJECT/secrets/master_cv.tex"
```

Also keep `"$PROJECT/secrets/storytelling.md"` (Phase 3 letter structure). After **Proceed Phase 2**, complete files land in `/home/mario/Downloads/{company}_{job_title}_CV.tex` and `_CoverLetter.tex`.

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
3. **Status** select must include exactly: `Skipped`, `Needs Context`, `Generating`, `Proceed Phase 2`, `Ready to Apply`.
4. Add **Candidate notes** (Text / rich_text) if missing.
5. Create two empty pages: **Master CV**, **Style & Learnings**. Paste the distilled Markdown.
6. Share the database and both pages with the integration (**Connect to**).
7. Copy IDs from the URLs:
   - Database: `https://notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...` → 32 hex chars (optionally insert dashes as `8-4-4-4-12`).
   - Page: the 32 hex chars after the page title slug.

In n8n: **Credentials → Notion API** → Internal integration token.

Put IDs and the Claude key in `$PROJECT/secrets/notion_ids.json` (`applications_db_id`, `master_cv_page_id`, `style_learnings_page_id`, `anthropic_api_key`). The workflow loads them at runtime via SSH (**Load Secret IDs**).

Select the Notion credential on every Notion node (including **Notion Resume Trigger**). Select **SSH localhost** on Load Secret IDs / Read Master Tex / Persist Run State / Write Full Tex / Read Storytelling.

---

## 4. n8n (self-hosted, this machine)

1. Import [`JD Flow.json`](../JD Flow.json): **Workflows → Import from File**. If **JD Flow** is already listed, refresh the n8n tab instead.
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

Expect `{ "status": "accepted" }` immediately. Then open **Executions**:

- First run: popup shows `skipped` or `needs_context` (not instant `accepted`). Notion **Skipped** or **Needs Context**.
- Same `url` again: popup `Already filed. No new row.`
- After Candidate notes + Status **Proceed Phase 2**: within ~1 minute, Downloads `.tex` files and Notion **Ready to Apply**.

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

- [ ] `secrets/master_cv.tex` + `secrets/storytelling.md` present
- [ ] `anthropic_api_key` in `secrets/notion_ids.json`; spend cap set in Anthropic console
- [ ] Applications DB Status options include Needs Context / Proceed Phase 2 / Generating
- [ ] **Candidate notes** property exists
- [ ] Applications DB + two pages shared with the integration
- [ ] Import latest `JD Flow.json`; Notion + SSH credentials attached
- [ ] Workflow **Active**; extension uses `/webhook/job-ingest`
- [ ] Reload Chrome extension so popup status messages update
