# ELI5: Put JD Flow into your n8n (n8n + Docker already ready)

This file is the full map. In chat we do **one step at a time** and wait for you.

You already have:

- n8n installed and running
- Docker ready
- This project folder: `/home/mario/Documents/n8n/Nuevo trabajo`

You do **not** need to install n8n again.

---

## The toy version of the whole system

Imagine a post office:

1. **Chrome extension** = you drop a letter (the job page) in the slot.
2. **n8n webhook** = the slot. It **waits** for scoring, then tells the popup skipped / duplicate / needs context.
3. **Parse Clean MD** = throws away ads/menus and keeps the job text.
4. **Notion search** = “Did we already file this exact job URL?” If yes, stop. Costs nothing.
5. **Haiku** = cheap intern who scores fit 0–100.
6. **If score &lt; 70** = **Skipped**. Popup says skipped.
7. **If score ≥ 70** = **Haiku Phase 1** audits gaps and asks you questions → Notion **Needs Context**.
8. **You** fill **Candidate Answers**, then click **Continue Phase 2**.
9. **Sonnet Phase 2** returns line patches; Python writes the CV `.tex`. Continue stays CV-only.
10. File lands in **Downloads**. Notion becomes **Ready to Apply** with a LaTeX CV preview.
11. Optional: **Write cover letter** → Sonnet letter body → Python splices `master_letter.tex` → Downloads `_CoverLetter.tex`.

You click → Notion asks questions → you answer → Downloads gets real tailored `.tex` files.

---

## Two n8n “doors” (important)

| Door | URL | When to use |
| --- | --- | --- |
| Test | `http://localhost:5678/webhook-test/job-ingest` | Workflow is **not** Active. You must click **Test workflow** in the editor first. Works for **one** call. |
| Live | `http://localhost:5678/webhook/job-ingest` | Workflow **Active** toggle is on. Use this after credentials work. |

The Chrome extension default is the **live** door. While we set things up, keep the workflow **off** (not Active) and use the **test** door.

---

## If n8n runs on the machine vs inside Docker

The **Clean HTML** node runs a command on the **same computer n8n is using**.

### A. n8n is a normal program on Linux (this machine already was)

The command should stay:

```text
/home/mario/Documents/n8n/Nuevo trabajo/.venv/bin/python "/home/mario/Documents/n8n/Nuevo trabajo/scripts/clean_html.py" --b64 '{{ $json.b64 }}'
```

Docker can still be installed. You just are not running n8n *inside* a container.

### B. n8n is a Docker container

The container cannot see your home folder unless you **mount** it.

In `docker-compose.yml` (or `docker run -v`), mount the project, for example:

```yaml
volumes:
  - /home/mario/Documents/n8n/Nuevo trabajo:/data/jd-flow
```

Then change **Clean HTML** to:

```text
/data/jd-flow/.venv/bin/python "/data/jd-flow/scripts/clean_html.py" --b64 '{{ $json.b64 }}'
```

`.venv` is a Linux venv. It only works if the container is also Linux **and** the Python inside `.venv` matches that OS. If Execute Command fails inside Docker, say so in chat; we point the command at the container’s `python3` or we install `beautifulsoup4` + `html2text` in the image.

---

## What you will create (checklist)

Do these in the order of the steps below. Do not paste API keys into this repo.

- [ ] n8n editor open, **JD Flow** canvas visible, **Active = off**
- [ ] `anthropic_api_key` in `secrets/notion_ids.json` (not n8n Header Auth)
- [ ] Notion internal integration token in n8n **Notion API** credential
- [ ] Notion database **Applications** with the properties listed below
- [ ] Page **Style & Learnings**, shared with the integration
- [ ] IDs in `secrets/notion_ids.json` (`applications_db_id`, `style_learnings_page_id`)
- [ ] Notion + SSH credentials attached
- [ ] Chrome extension loaded unpacked
- [ ] One test send, then (only then) turn **Active** on

---

## Notion database properties (copy this when you build the DB)

Database title property name: **Job Title** (type **Title**).

| Property name | Type | Options |
| --- | --- | --- |
| Job Title | Title | (built-in) |
| Job URL | URL | — |
| Company | Text (rich_text) | — |
| Location | Text | — |
| Skills | Text | — |
| Fit Score | Number | number format is fine |
| Status | Select | `Skipped`, `Needs Context`, `Generating`, `Proceed Phase 2`, `Ready to Apply`, `Write Cover Letter` |
| Rationale | Text | — |
| Salary Range | Text | — |
| Salary Flag | Select | `extracted`, `UNVERIFIED Estimate` |
| Candidate notes | Text | Phase 1 questions (seeded) |
| Candidate Answers | Text | Your replies |
| LaTex CV | Text | Preview ≤1900 chars (full file in Downloads) |
| LaTex Cover Letter | Text | Preview after **Write cover letter** |

**LaTex CV** is a preview only. Phase 2 writes the full `.tex` to Downloads. Cover letter is a second click after Ready to Apply.

---

## How to copy a Notion ID

Open the database or page in the browser.

- **Database:** URL looks like `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`  
  The 32 hex characters before `?v=` are the ID. You may insert dashes: `8-4-4-4-12`.
- **Page:** URL looks like `https://www.notion.so/My-Page-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`  
  The last 32 hex characters are the page ID.

IDs go in `secrets/notion_ids.json` (no Master CV page, no `REPLACE_ME_...` on the canvas). Notion nodes use those IDs at runtime via **Load Secret IDs**.

---

## Nodes on the canvas (what each one does)

Read left to right.

| Node | Plain English |
| --- | --- |
| Webhook | The mailbox. POST JSON `{ "url", "html" }`. **Waits** and answers skipped / duplicate / needs_context. |
| Pack Ingest | Packs HTML into base64 so the shell command does not break. |
| Clean HTML | Code node. Strips nav/scripts. Makes Markdown (`url` + `clean_md`). |
| Load Secret IDs | SSH. Reads `secrets/notion_ids.json`. |
| Search Job URL | Asks Notion: any row with this Job URL? |
| Is Duplicate? | If Notion returned a page `id` → duplicate. |
| Distill Master CV | SSH. `distill_cv.py --verify-json` from `secrets/master_cv.tex`. |
| Flatten CV | Parses `{cv_md, ok, missing}`. |
| Build Haiku Prompt | Full CV markdown + JD (JD capped at 8000 chars). |
| Haiku Triage | Cheap model. JSON with `fit_score`. |
| Parse Triage | Reads that JSON; copies `usage`. |
| Fit Score >= 70%? | Fork. |
| Log Skipped | New Notion row, Status = Skipped. |
| Get Style Learnings | Downloads style rules (only if fit is high). |
| Flatten Style | One `style_rules` string. |
| Build Phase 1 Prompt | Derived CV markdown + JD + style. |
| Haiku Phase 1 | Gap audit + questions JSON. |
| Create Needs Context | New Notion row, Status = Needs Context. |
| Persist Run State | Saves Phase 1 JSON under `secrets/runs/`. |
| Webhook Resume | Continue Phase 2 or **Write cover letter** (`write_letter: true`). |
| Letter by Status? | Letter click searches Status = Write Cover Letter (exactly one row). |
| Write Letter? | After Merge Run State: false = Phase 2 CV; true = Phase 3 letter (no P2 rerun). |
| Read Master Tex Resume | `assemble_tex.py --number --cap 0`. |
| Sonnet Phase 2 | Returns `latex_cv_patches` only. |
| Write Full Tex | `assemble_tex.py --cv-only` (patches + repair itemize) → Downloads. |
| Persist Phase 2 Output | Merges `latex_cv_patches` + `cv_path` into the run JSON. |
| Sonnet Phase 3 | Opt-in. Rewrites master letter body (hook, bridge, 3 themed bullets, close). |
| Read Master Letter | `cat secrets/master_letter.tex` — structure template for Phase 3. |
| Write Letter Tex | `assemble_tex.py --letter-only` → Downloads `_CoverLetter.tex`. |

---

## Step-by-step (same order we use in chat)

### Step 1 — Open n8n

Browser: [http://localhost:5678](http://localhost:5678)

You should see the n8n home (workflow list). If the page does not load, n8n is not running on 5678.

### Step 2 — Open JD Flow (do not turn Active on)

In the left list, click **JD Flow**.  
You should see a long chain of nodes and a sticky note on the left.

If it is missing: **… menu → Import from File** → choose  
`/home/mario/Documents/n8n/Nuevo trabajo/JD Flow.json`

Leave the **Active** toggle **off**.

### Step 3 — Claude Console key

1. Open [https://console.anthropic.com](https://console.anthropic.com) and sign in.
2. **API keys** → **Create key**. Copy it once. Treat it like a password.
3. Set a **spend limit** so a loop cannot bill you freely.
4. You need models `claude-haiku-4-5` and `claude-sonnet-5`.

Do not put this key in a git file.

### Step 4 — Save the key in secrets (not n8n Header Auth)

Put `anthropic_api_key` in `$PROJECT/secrets/notion_ids.json` with the Notion IDs. Claude HTTP nodes read `x-api-key` from **Load Secret IDs**. You do **not** need an n8n Header Auth credential.

### Step 5 — Confirm Claude HTTP nodes

Open **Haiku Triage**, **Haiku Phase 1**, **Sonnet Phase 2**, and **Sonnet Phase 3**. Each should POST to `https://api.anthropic.com/v1/messages` with header `x-api-key` from Secret IDs. They already send `anthropic-version: 2023-06-01`.

### Step 6 — Notion integration token

1. [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. **New integration**, type **Internal**.
3. Copy the **Internal Integration Secret** (token).

n8n: **Add credential** → **Notion API** → paste token → save. Name it `Notion account`.

### Step 7 — Create the Applications database

In Notion, **New page** → type `/database` → **Table – Full page**. Name it **Applications**.

Add the properties from the table above. Names must match **exactly** (including spaces and spelling): `Job URL`, `Fit Score`, `Salary Flag`, `LaTex CV`, `LaTex Cover Letter`, etc.

Status options: `Skipped`, `Needs Context`, `Generating`, `Proceed Phase 2`, `Ready to Apply`, `Write Cover Letter`.  
Salary Flag options: `extracted` and `UNVERIFIED Estimate`.

### Step 8 — Create Style & Learnings and the local master CV

Create page **Style & Learnings** (tone rules). Do **not** paste the CV into Notion.

Haiku distills `secrets/master_cv.tex` at runtime (`--verify-json`). After you edit that file, the next ingest re-distills it. ATS compile/check: [`SETUP.md`](SETUP.md#master-cv-ats).

Copy the original CV `.tex` locally. Do **not** paste the `.tex` into n8n:

```bash
mkdir -p /home/mario/Documents/n8n/Nuevo trabajo/secrets
cp /path/to/your.tex /home/mario/Documents/n8n/Nuevo trabajo/secrets/master_cv.tex
```

Continue Phase 2 writes:

`/home/mario/Downloads/{company}_{job_title}_CV.tex`

**Write cover letter** (after Ready to Apply) also needs:

```bash
cp /path/to/letter.tex /home/mario/Documents/n8n/Nuevo trabajo/secrets/master_letter.tex
cp /path/to/storytelling.md /home/mario/Documents/n8n/Nuevo trabajo/secrets/storytelling.md
```

`master_letter.tex` should contain `% LETTER_BODY` / `% END_LETTER_BODY` markers. Letter file:

`/home/mario/Downloads/{company}_{job_title}_CoverLetter.tex`

**Share / Connect** the Applications database **and Style & Learnings** with your integration. If you skip this, n8n gets 404.

### Step 9 — Put IDs in secrets, attach Notion + SSH

Put `applications_db_id`, `style_learnings_page_id`, and `anthropic_api_key` in `secrets/notion_ids.json`. `master_cv_page_id` is optional/unused.

Click each red/warning Notion node → pick credential **Notion account**. Click each SSH node → **SSH localhost** (Load Secret IDs, Distill Master CV, Persist Run State, Persist Phase 2 Output, Write Full Tex, Write Letter Tex, Read Master Tex Resume, Read Storytelling, Read Master Letter, Read Patched CV).

Nodes that need Notion:

- Search Job URL
- Log Skipped
- Get Style Learnings
- Create Needs Context
- Update Ready to Apply (and other resume Notion nodes)

### Step 10 — Confirm Clean HTML

This n8n build does **not** include the Execute Command node. **Clean HTML** is a **Code** node (JavaScript) that strips nav/scripts. No Docker Python path is required.

If you still see a node with a **?** and “Install this node”, delete it and use a Code node named **Clean HTML** instead (see the chat walkthrough).

### Step 11 — Load the Chrome extension

1. Chrome → `chrome://extensions`
2. **Developer mode** on
3. **Load unpacked** → folder  
   `/home/mario/Documents/n8n/Nuevo trabajo/chrome-extension`
4. Extension **Details → Extension options**
5. While testing:  
   `http://localhost:5678/webhook-test/job-ingest`  
   After Active is on:  
   `http://localhost:5678/webhook/job-ingest`

### Step 12 — One test run (still not Active)

In the JD Flow editor click **Test workflow**.  
Then either:

```bash
curl -sS -X POST http://localhost:5678/webhook-test/job-ingest \
  -H 'Content-Type: application/json' \
  -d @"/home/mario/Documents/n8n/Nuevo trabajo/tests/sample_ingest.json"
```

or open a job page and click the extension **Send job to n8n**.

Expect `{ "status": "skipped" }` or `{ "status": "needs_context" }` (or the popup showing those).  
Then n8n **Executions**: green = good; red = open the failed node.

First new URL → Distill + Haiku, then **Skipped** or **Needs Context** in Notion.  
Same URL again → duplicate, no Claude call.

### Step 13 — Turn Active on

Only after a test execution is green:

- Switch webhook in the extension to `/webhook/job-ingest`
- Toggle **Active** on JD Flow
- Save

You can now send jobs without clicking Test workflow first.

---

## If something breaks

| What you see | Likely cause |
| --- | --- |
| Webhook 404 | Workflow not Active, or you did not click **Test workflow** for the test URL |
| Clean HTML failed | Python path wrong (Docker not mounted) or `bs4` missing |
| Notion 404 / unauthorized | Page/DB not shared with the integration, or wrong ID |
| Notion property error | Property name/type does not match the table (e.g. `richText` vs Text) |
| Haiku/Sonnet 401 | `anthropic_api_key` missing/wrong in `secrets/notion_ids.json` |
| Popup CORS / failed fetch | Webhook host is not `localhost:5678`; add it to `host_permissions` in `manifest.json` and reload the extension |
| ATS Education/Certifications stay empty | Combined CV heading or nested bullets; see [`SETUP.md`](SETUP.md#master-cv-ats) |

---

## What we will not do in git

No API keys, no live Notion tokens, no full LaTeX CV, no writing CSV in the repo.
