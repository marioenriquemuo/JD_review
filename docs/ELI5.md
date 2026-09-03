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
2. **n8n webhook** = the slot. It says “got it” right away.
3. **Python script** = a clerk who throws away ads, menus, and scripts, and keeps the job text.
4. **Notion search** = “Did we already file this exact job URL?” If yes, stop. Costs nothing.
5. **Haiku** = a cheap intern who scores fit 0–100.
6. **If score &lt; 70** = file as **Skipped**. Stop.
7. **If score ≥ 70** = read your CV style notes, then **Sonnet** writes bullets, letter, flashcards, dossier.
8. A **second small Sonnet** call turns those bullets/letter into LaTeX sections (not a full `.tex` file).
9. **Notion** = the filing cabinet. New page: **Ready to Apply**, plus columns **LaTex CV** and **LaTex Cover Letter**.

You click. n8n thinks. Notion stores.

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
- [ ] Anthropic API key stored as n8n **Header Auth**
- [ ] That credential attached to **Haiku Triage**, **Sonnet Assets**, and **Sonnet LaTeX**
- [ ] Notion internal integration token in n8n **Notion API** credential
- [ ] Notion database **Applications** with the properties listed below
- [ ] Pages **Master CV** and **Style & Learnings**, shared with the integration
- [ ] Three IDs pasted into the Notion nodes (no `REPLACE_ME_...` left)
- [ ] Notion credential attached to every Notion node
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
| Status | Select | `Skipped`, `Ready to Apply` |
| Rationale | Text | — |
| Salary Range | Text | — |
| Salary Flag | Select | `extracted`, `UNVERIFIED Estimate` |
| LaTex CV | Text | LaTeX fragment to paste into the master CV |
| LaTex Cover Letter | Text | LaTeX fragment to paste into the master letter |

Long text (CV bullets, cover letter, flashcards, dossier) is **not** a property. The workflow writes those into the **page body**. **LaTex CV** / **LaTex Cover Letter** are properties (cap 2,000 characters) filled by a second Sonnet call from the parsed bullets/letter.

---

## How to copy a Notion ID

Open the database or page in the browser.

- **Database:** URL looks like `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`  
  The 32 hex characters before `?v=` are the ID. You may insert dashes: `8-4-4-4-12`.
- **Page:** URL looks like `https://www.notion.so/My-Page-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`  
  The last 32 hex characters are the page ID.

In n8n, paste that ID into the node’s resource field (mode **ID**, not URL), replacing:

- `REPLACE_ME_APPLICATIONS_DB_ID` → Applications database
- `REPLACE_ME_MASTER_CV_PAGE_ID` → Master CV page
- `REPLACE_ME_STYLE_PAGE_ID` → Style & Learnings page

Those placeholders sit on:

- **Search Job URL** (database)
- **Log Skipped** (database)
- **Create Application** (database)
- **Get Master CV** (page / block ID)
- **Get Style Learnings** (page / block ID)

A yellow sticky note on the left of the canvas lists the same three names.

---

## Nodes on the canvas (what each one does)

Read left to right.

| Node | Plain English |
| --- | --- |
| Webhook | The mailbox. POST JSON `{ "url", "html" }`. Answers `{ "status": "accepted" }` immediately. |
| Pack Ingest | Packs HTML into base64 so the shell command does not break. |
| Clean HTML | Code node. Strips nav/scripts. Makes Markdown (`url` + `clean_md`). |
| Search Job URL | Asks Notion: any row with this Job URL? |
| Is Duplicate? | If Notion returned a page `id` → duplicate. |
| Stop Duplicate | End. No new row. $0. |
| Get Master CV | Downloads your CV page blocks. |
| Flatten CV | Turns blocks into one `cv_md` string. |
| Build Haiku Prompt | JD + short CV. |
| Haiku Triage | Cheap model. JSON with `fit_score`. |
| Parse Triage | Reads that JSON. |
| Fit Score >= 70%? | Fork. |
| Log Skipped | New Notion row, Status = Skipped. |
| Get Style Learnings | Downloads style rules (only if fit is high). |
| Flatten Style | One `style_rules` string. |
| Build Sonnet Prompt | JD + full CV + style. |
| Sonnet Assets | Writes the application pack as JSON (mermaid H1–H4). |
| Parse Assets | Flattens JSON into text fields (capped ~1900 chars for Notion). |
| Build Latex Prompt | Packs those bullets + letter only (no full JD). |
| Sonnet LaTeX | Translates them into `latex_cv` / `latex_cover_letter` fragments. |
| Parse Latex | Reads that JSON; caps ~1900 chars. |
| Assemble Payload | Picks the fields we store. |
| Create Application | New Notion row, Status = Ready to Apply, assets in the page body, LaTeX in the two columns. |

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

### Step 4 — Save the key inside n8n

n8n: **Credentials** (left) → **Add credential** → search **Header Auth**.

- Name: `Anthropic API`
- Header name: `x-api-key`
- Header value: paste the key

Save.

### Step 5 — Attach Claude to the three HTTP nodes

Open **Haiku Triage** → Credentials → pick **Anthropic API**.  
Open **Sonnet Assets** → same.  
Open **Sonnet LaTeX** → same.

Those nodes already send header `anthropic-version: 2023-06-01`. You do not add that in the credential.

### Step 6 — Notion integration token

1. [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. **New integration**, type **Internal**.
3. Copy the **Internal Integration Secret** (token).

n8n: **Add credential** → **Notion API** → paste token → save. Name it `Notion account`.

### Step 7 — Create the Applications database

In Notion, **New page** → type `/database` → **Table – Full page**. Name it **Applications**.

Add the properties from the table above. Names must match **exactly** (including spaces and spelling): `Job URL`, `Fit Score`, `Salary Flag`, `LaTex CV`, `LaTex Cover Letter`, etc.

Status options: `Skipped` and `Ready to Apply`.  
Salary Flag options: `extracted` and `UNVERIFIED Estimate`.

### Step 8 — Create two pages and share everything

Create pages **Master CV** and **Style & Learnings**.

For now you can paste a short placeholder, e.g. “CV goes here”. Later we distill your LaTeX/CSV with:

```bash
/home/mario/Documents/n8n/Nuevo trabajo/.venv/bin/python \
  /home/mario/Documents/n8n/Nuevo trabajo/scripts/distill_cv.py \
  --tex /path/to/your.tex \
  --csv /path/to/your.csv \
  --out-dir /tmp/jd-distill
```

Then paste `master_cv.md` and `style_learnings.md` into those pages.

**Share / Connect** the database **and both pages** with your integration. If you skip this, n8n gets 404.

### Step 9 — Paste the three IDs into JD Flow

Replace every `REPLACE_ME_...` on the Notion nodes (list above).  
Click each red/warning Notion node → pick credential **Notion account**.

Nodes that need Notion:

- Search Job URL
- Get Master CV
- Log Skipped
- Get Style Learnings
- Create Application

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

Expect `{ "status": "accepted" }` (or the popup showing `accepted`).  
Then n8n **Executions**: green = good; red = open the failed node.

First new URL → Haiku, then Skipped or Ready to Apply in Notion.  
Same URL again → **Stop Duplicate**, no Claude call.

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
| Haiku/Sonnet 401 | Header Auth name is not `x-api-key`, or wrong key |
| Popup CORS / failed fetch | Webhook host is not `localhost:5678`; add it to `host_permissions` in `manifest.json` and reload the extension |

---

## What we will not do in git

No API keys, no live Notion tokens, no full LaTeX CV, no writing CSV in the repo.
