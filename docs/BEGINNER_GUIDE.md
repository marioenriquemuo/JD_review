# How to set up and use JD Flow (beginner guide)

This guide is for people who are **new** to n8n, Notion integrations, and Chrome extensions.  
Follow the steps **in order**. Do not skip ahead.

When you finish, you will be able to:

1. Open a job posting in Chrome (or upload a text PDF).
2. Click **Send job to n8n** or **Upload PDF**.
3. Answer a few questions in Notion.
4. Click **Continue Phase 2**.
5. Get a tailored CV and cover letter (LaTeX files) in your Downloads folder.

---

## What this system is (in plain words)

Think of a small post office:

| Piece | What it is | What it does |
| --- | --- | --- |
| Chrome extension | A button in your browser | Sends the job page to n8n |
| n8n | An automation app on your computer | Runs the steps automatically |
| Claude (Anthropic) | An AI service you pay for by usage | Scores the job and writes CV / letter text |
| Notion | Your filing cabinet (online database) | Stores each job, questions, and answers |
| Your CV files | Files on your computer | The “master” resume the AI is allowed to use |

**Important honesty rule:** the AI may only use facts from your master CV and the answers you type. It must not invent jobs, dates, or metrics.

---

## What you need before you start

Checklist — have all of these ready:

- [ ] A computer with this project folder already on disk  
  Example path: `/home/mario/Documents/n8n/Nuevo trabajo`
- [ ] **n8n** installed and able to open in the browser (usually `http://localhost:5678`)
- [ ] **Google Chrome** (or Chromium)
- [ ] A **Notion** account
- [ ] An **Anthropic** account (for Claude API) with billing/spend limit set
- [ ] Your resume as a **`.tex` (LaTeX)** file, or a Markdown version you can paste into Notion
- [ ] About **45–90 minutes** for the first setup

You do **not** need to know how to code.

---

## Big picture: two buttons you will use every day

After setup, your daily work is only this:

```text
1. Open the job page in Chrome, or have a text PDF of the JD
2. Click extension → “Send job to n8n”  (web posting)
   or “Upload PDF”                      (PDF job description)
3. If the job is a good fit → Notion shows questions
4. Type your answers in Notion column “Candidate Answers”
5. Click extension → “Continue Phase 2”
6. Wait until the popup says Ready to Apply
7. Open the .tex files in Downloads
```

**Upload PDF** works only if the PDF has selectable text. Scanned/image PDFs are not supported.

Possible popup results after **Send job**:

| Popup message | Meaning | What you do next |
| --- | --- | --- |
| Skipped (fit …) | Job is a weak match | Nothing — or improve your Master CV later |
| Already filed… | This job URL was sent before | Click **Continue Phase 2** if you still need the CV |
| Needs Context… | Good enough fit; questions are ready | Fill **Candidate Answers**, then **Continue Phase 2** |

---

# Part A — One-time setup

## Step 1 — Create an Anthropic (Claude) API key

1. Go to [https://console.anthropic.com](https://console.anthropic.com) and sign in.
2. Open **API keys**.
3. Click **Create key**.
4. Copy the key and paste it into a temporary notes file on your computer.  
   You will put it into a secrets file later.  
   **Do not** put this key into GitHub, Notion public pages, or chat screenshots.
5. In Anthropic settings, set a **monthly spend limit** so costs cannot run away.

You are done with Anthropic for now.

---

## Step 2 — Create a Notion integration (robot user)

Notion needs a “robot” that n8n can use.

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations).
2. Click **New integration**.
3. Name it something clear, for example: `JD Flow`.
4. Type: **Internal**.
5. Click **Save** / **Submit**.
6. Copy the **Internal Integration Secret** (token).  
   Keep it private, same as the Claude key.

---

## Step 3 — Create the Applications database in Notion

This database is your job tracker.

1. In Notion, create a **new page**.
2. Type `/database` and choose **Table – Full page**.
3. Name the database: **Applications**.

### 3.1 Rename the title column

The first column is usually called “Name” or “Title”.

1. Click the column header.
2. Rename it to exactly: **Job Title**  
   (spelling and spaces must match)

### 3.2 Add these properties (columns)

Click **+** to add each property. Names must match **exactly**:

| Property name | Type in Notion | Notes |
| --- | --- | --- |
| Job URL | URL | Used to avoid duplicates |
| Company | Text | |
| Location | Text | |
| Skills | Text | |
| Fit Score | Number | 0–100 |
| Status | Select | See options below |
| Rationale | Text | Short AI explanation |
| Salary Range | Text | |
| Salary Flag | Select | Options below |
| Candidate notes | Text | Questions from the AI (auto-filled) |
| Candidate Answers | Text | **You type answers here** |
| LaTex CV | Text | Short preview only |
| LaTex Cover Letter | Text | Short preview only |

### 3.3 Status options

Open the **Status** property → Edit options. Create these exact options:

- `Skipped`
- `Needs Context`
- `Generating`
- `Proceed Phase 2` (optional / legacy; the extension button is preferred)
- `Ready to Apply`

### 3.4 Salary Flag options

- `extracted`
- `UNVERIFIED Estimate`

---

## Step 4 — Create two helper pages in Notion

1. Create a page named **Master CV**.  
   Paste a plain-text / Markdown summary of your resume (not the raw LaTeX if you prefer readability).
2. Create a page named **Style & Learnings**.  
   Paste short writing rules (tone, phrases to avoid, what “good” bullets look like).  
   Keep it short (about 10–20 rules).

Later you can improve these pages; they do not need to be perfect on day one.

---

## Step 5 — Connect Notion pages to your integration

For **each** of these, open the page → `…` / **Connections** / **Connect to** → choose `JD Flow`:

- the **Applications** database
- the **Master CV** page
- the **Style & Learnings** page

If you skip this, n8n will show “object not found” or permission errors.

---

## Step 6 — Copy Notion IDs (important)

You need three IDs for the secrets file.

### Database ID (Applications)

1. Open the Applications database in a browser.
2. Look at the URL. Example shape:

`https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=yyyy`

3. Copy the long `xxxxxxxx…` part (**32 characters**, letters and numbers).  
   **Do not** include `?v=…`.

### Page IDs (Master CV and Style & Learnings)

1. Open the page.
2. From the URL, copy the 32-character ID (often at the end, sometimes with dashes).
3. You may keep dashes or remove them; both usually work. Be consistent and careful.

Write down:

- Applications database ID  
- Master CV page ID  
- Style & Learnings page ID  

---

## Step 7 — Put secrets on your computer

Your project has a private folder named `secrets` (it should not be uploaded to GitHub).

1. Open a file manager and go to:

`/home/mario/Documents/n8n/Nuevo trabajo/secrets`

2. Create or edit the file: `notion_ids.json`

3. Put content like this (replace the fake values with yours):

```json
{
  "applications_db_id": "PASTE_APPLICATIONS_DATABASE_ID",
  "master_cv_page_id": "PASTE_MASTER_CV_PAGE_ID",
  "style_learnings_page_id": "PASTE_STYLE_PAGE_ID",
  "anthropic_api_key": "PASTE_CLAUDE_API_KEY"
}
```

4. Save the file.

5. Also place your master resume LaTeX here:

`/home/mario/Documents/n8n/Nuevo trabajo/secrets/master_cv.tex`

6. Make sure this file exists (cover-letter storytelling rules):

`/home/mario/Documents/n8n/Nuevo trabajo/secrets/storytelling.md`

If `storytelling.md` is missing, copy the version from the project or ask someone to recreate it before using Phase 2.

---

## Step 8 — Prepare Python tools (one time)

Open a terminal and run these commands one by one.

Replace the path if your folder is different.

```bash
PROJECT="/home/mario/Documents/n8n/Nuevo trabajo"
python3 -m venv "$PROJECT/.venv"
"$PROJECT/.venv/bin/pip" install beautifulsoup4 html2text pypdf
```

You should see packages install without red fatal errors.

Optional check:

```bash
"$PROJECT/.venv/bin/python" "$PROJECT/scripts/load_secret_ids.py" "$PROJECT/secrets/notion_ids.json"
```

You should see a single line of JSON that includes your IDs (and the API key).  
If it says `missing fields`, fix `notion_ids.json` and try again.

---

## Step 9 — Add credentials inside n8n

1. Open n8n (`http://localhost:5678`).
2. Go to **Credentials** (left menu or settings area).

### 9.1 Notion credential

1. Add credential → **Notion API**.
2. Paste the Notion **Internal Integration Secret** from Step 2.
3. Name it: `Notion account`.
4. Save.

### 9.2 SSH credential (so n8n can read local files)

The workflow reads files on your machine through an SSH node named **SSH localhost**.

1. Add credential → **SSH Password** (or the SSH type your n8n shows).
2. Host: `127.0.0.1` or `localhost`
3. Port: `22` (typical)
4. User: your Linux username
5. Password or private key: whatever you use for local SSH login
6. Name it exactly: `SSH localhost`
7. Save.

If SSH to localhost is new for you, ask whoever set up this computer to confirm SSH login works with:

```bash
ssh localhost
```

---

## Step 10 — Import the workflow

1. In n8n: **Workflows** → **Import from File**.
2. Choose:

`/home/mario/Documents/n8n/Nuevo trabajo/JD Flow.json`

3. Open the imported workflow named **JD Flow**.
4. For every red / warning Notion node: select credential **Notion account**.
5. For every SSH node: select credential **SSH localhost**.
6. Click **Save**.

### Turn it ON for daily use

1. Toggle the workflow to **Active** (ON).
2. Do **not** rely on “Test workflow” for normal use.

Live webhook URLs:

- Send job: `http://localhost:5678/webhook/job-ingest`
- Continue Phase 2: `http://localhost:5678/webhook/job-resume`

---

## Step 11 — Install the Chrome extension

1. Open Chrome and go to: `chrome://extensions`
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked**.
4. Select this folder:

`/home/mario/Documents/n8n/Nuevo trabajo/chrome-extension`

5. Pin the extension to the toolbar (puzzle icon → pin).
6. Open extension **Options** (or “Webhook options” in the popup).
7. Set webhook URL to:

`http://localhost:5678/webhook/job-ingest`

8. Save.

If you change the extension files later, return to `chrome://extensions` and click **Reload** on JD Flow Ingest.

---

# Part B — First successful test (do this once)

## Test 1 — Send a real job page

1. Make sure:
   - n8n is running
   - JD Flow is **Active**
   - Extension webhook points to `/webhook/job-ingest`
2. Open a real job posting in Chrome (LinkedIn, company career site, etc.).
3. Click the extension.
4. Click **Send job to n8n**.  
   If the JD is a **text PDF** instead of a web page, click **Upload PDF** and pick the file (scanned/image PDFs will fail).
5. Wait. The popup shows **Scoring…** then a result.

### If you see Skipped

That means fit score was below 70. Check Notion: a **Skipped** row should exist.  
**Candidate notes** on that row lists the gaps Haiku did not find in the Master CV. Treat those as a ticket: add only true facts, then delete the row and send the job again.

### If you see Needs Context

Success for Phase 1.

1. Open Notion → Applications.
2. Open the new row.
3. Read **Candidate notes** / page body questions.
4. Type honest answers in **Candidate Answers**.
5. Click the extension again → **Continue Phase 2**.
6. Wait (can take one or a few minutes).
7. Popup should show **Ready to Apply** and file paths.
8. Check:
   - Notion Status = `Ready to Apply`
   - Files in `/home/mario/Downloads/` ending with `_CV.tex` and `_CoverLetter.tex`

### If you see Already filed

The URL was already in Notion.

1. The extension should remember the page id.
2. Fill **Candidate Answers** if needed.
3. Click **Continue Phase 2**.

---

# Part C — Everyday operating instructions

## Recommended routine for each job

1. Open the job posting tab.
2. **Send job to n8n**.
3. If **Needs Context**:
   - Answer in Notion **Candidate Answers** (short, factual, no exaggeration).
   - Click **Continue Phase 2**.
4. Download / compile the LaTeX files.
5. Review before applying. You are still responsible for accuracy.

## What each Notion Status means

| Status | Meaning |
| --- | --- |
| Skipped | Weak fit; no tailored CV generated |
| Needs Context | Waiting for your answers |
| Generating | Phase 2/3 is running |
| Ready to Apply | Files generated; review and apply |
| Proceed Phase 2 | Old manual trigger; prefer the extension button |

## Where your answers go

- **Candidate notes** = questions written by the AI (you can leave them).
- **Candidate Answers** = **your** replies. This is what Phase 2 reads.

Empty answers are allowed, but then the CV can only use facts already in the master CV.

---

# Part D — Common problems and fixes

## Popup says “No Notion row for this Job URL”

Usually means Continue ran without a saved application id.

Fix:

1. Open the **original job posting** tab.
2. Click **Send job to n8n** once (even if it says already filed).
3. Then click **Continue Phase 2**.

## Popup never changes / request failed

Check:

1. Is n8n running?
2. Is JD Flow **Active**?
3. Is the webhook URL exactly `/webhook/job-ingest` (not `webhook-test`)?
4. Did you reload the extension after updates?

## Notion errors: invalid ID / object not found

Check:

1. Database/page shared with the integration.
2. IDs in `secrets/notion_ids.json` are correct (no `?v=` view suffix).
3. Notion credential is attached on every Notion node.

## SSH / secret errors in n8n Executions

Check:

1. SSH credential works for localhost.
2. `secrets/notion_ids.json` exists and has all four fields.
3. `secrets/master_cv.tex` exists.

## LaTeX columns in Notion look “cut off”

That is normal. Notion text fields are limited (~2000 characters).  
Full files are in **Downloads**.

## Costs feel high

- Weak jobs should stay **Skipped** (cheap).
- Only click **Continue Phase 2** for roles you truly want.
- Keep Anthropic spend limits on.

---

# Part E — What “done” looks like

You are fully set up when all of these are true:

- [ ] Claude key and Notion IDs are in `secrets/notion_ids.json`
- [ ] `master_cv.tex` and `storytelling.md` exist in `secrets/`
- [ ] Applications database has all required columns
- [ ] Integration is connected to DB + Master CV + Style pages
- [ ] n8n JD Flow is Active with Notion + SSH credentials attached
- [ ] Chrome extension installed and webhook set to live `/webhook/job-ingest`
- [ ] You completed one full pass: Send → answers → Continue → Downloads files

---

## Where to get more technical detail

- Short architecture overview: [`README.md`](../README.md)
- Compact setup notes: [`SETUP.md`](SETUP.md)
- Simple story version: [`ELI5.md`](ELI5.md)

If something fails, open n8n → **Executions**, click the failed run, and note:

1. which node is red  
2. the exact error text  

That information makes troubleshooting much faster.
