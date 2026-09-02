# Setup

Do these in order. Do not put API keys in the repo.

Replace `PROJECT` with:

`/home/mario/Documents/n8n/Nuevo trabajo`

---

## 1. Python libraries

Debian/Ubuntu blocks system `pip`. Use a project venv (this is what the n8n Execute Command node calls):

```bash
python3 -m venv "$PROJECT/.venv"
"$PROJECT/.venv/bin/pip" install beautifulsoup4 html2text
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/clean_html.py" --in "$PROJECT/tests/sample_ingest.json"
```

Expect JSON on stdout with `url` and `clean_md`. `clean_md` must not contain the sample `<script>` or `<nav>` text `Ignore this nav`.

Optional CV distill (your files, not in git):

```bash
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/distill_cv.py" --tex /path/to/cv.tex --csv /path/to/writing.csv --out-dir /tmp/jd-distill
```

Paste `/tmp/jd-distill/master_cv.md` into the Notion **Master CV** page and `/tmp/jd-distill/style_learnings.md` into **Style & Learnings**. Edit before use.

---

## 2. Claude Console

1. Open [console.anthropic.com](https://console.anthropic.com).
2. **API keys** → create a key. Copy it once.
3. **Settings → limits** (or Plans & Billing): set a monthly spend cap.
4. Confirm models `claude-haiku-4-5` and `claude-sonnet-5` are available on your account.

In n8n: **Credentials → Header Auth**

- Name: `Anthropic API`
- Header name: `x-api-key`
- Header value: the key

The workflow also sends `anthropic-version: 2023-06-01` as a request header (not part of this credential).

---

## 3. Notion

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New integration** (internal). Copy the token.
2. Create database **Applications** with the properties in [README.md](../README.md) (title = Job Title).
3. Create two empty pages: **Master CV**, **Style & Learnings**. Paste the distilled Markdown.
4. Share the database and both pages with the integration (**Connect to**).
5. Copy IDs from the URLs:
   - Database: `https://notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...` → 32 hex chars (optionally insert dashes as `8-4-4-4-12`).
   - Page: the 32 hex chars after the page title slug.

In n8n: **Credentials → Notion API** → Internal integration token.

Open **JD Flow** in n8n and replace the three placeholders on the Notion nodes / sticky note:

- `REPLACE_ME_APPLICATIONS_DB_ID`
- `REPLACE_ME_MASTER_CV_PAGE_ID`
- `REPLACE_ME_STYLE_PAGE_ID`

Select the Notion credential on every Notion node. Select **Anthropic API** Header Auth on **Haiku Triage** and **Sonnet Assets**.

---

## 4. n8n (self-hosted, this machine)

1. Import [`JD Flow.json`](../JD Flow.json): **Workflows → Import from File**. If **JD Flow** is already listed, refresh the n8n tab instead.
2. Confirm **Execute Command** on **Clean HTML** points at the venv interpreter:

```text
/home/mario/Documents/n8n/Nuevo trabajo/.venv/bin/python "/home/mario/Documents/n8n/Nuevo trabajo/scripts/clean_html.py" --b64 '{{ $json.b64 }}'
```

If n8n runs in Docker, mount `PROJECT` (including `.venv`) into the container or change the command. The n8n process user must be able to execute that venv Python.

3. Attach credentials (step 2–3). Paste Notion IDs.
4. **Webhook** node: production URL is `http://localhost:5678/webhook/job-ingest`. Inactive workflows use `http://localhost:5678/webhook-test/job-ingest` and require **Test workflow** in the editor.
5. Save. Set **Active** only after credentials and IDs are set.

If Execute Command is blocked in your n8n install, swap **Clean HTML** for a Code node that shells out the same script, or enable the Python task runner and paste the body of `clean_html.py` (allowlist `bs4`, `html2text`, `re`, `json`, `argparse`, `sys`, `base64`). Prefer Execute Command on local n8n.

### First test POST (no extension)

```bash
curl -sS -X POST http://localhost:5678/webhook-test/job-ingest \
  -H 'Content-Type: application/json' \
  -d @"$PROJECT/tests/sample_ingest.json"
```

Expect `{ "status": "accepted" }` immediately. Then open **Executions**:

- First run: Haiku (and maybe Sonnet). Notion **Skipped** or **Ready to Apply**.
- Second run with the same `url`: stops at **Stop Duplicate**, no LLM.

---

## 5. Chrome extension

1. Chrome → `chrome://extensions` → **Developer mode** → **Load unpacked** → select `$PROJECT/chrome-extension`.
2. Extension **Details → Extension options**. Set webhook URL:
   - Active workflow: `http://localhost:5678/webhook/job-ingest`
   - Testing in editor: `http://localhost:5678/webhook-test/job-ingest`
3. Open a job posting → click the extension → **Send job to n8n**.
4. Popup shows `accepted` if the webhook responded. Check n8n **Executions** for duplicate / skip / ready.

To allow a non-localhost n8n URL, add it to `host_permissions` in [`chrome-extension/manifest.json`](../chrome-extension/manifest.json) and reload the extension.

---

## Checklist

- [ ] `clean_html.py` smoke test prints Markdown without nav/script
- [ ] Claude key in n8n Header Auth; spend cap set
- [ ] Applications DB + two pages shared with the integration
- [ ] Three Notion IDs pasted into the workflow
- [ ] Webhook URL in the extension matches active vs test
- [ ] Duplicate curl does not call Haiku
