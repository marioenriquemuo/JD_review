#!/usr/bin/env python3
"""POST each NEW unfiled discovery row to job-ingest. Stops at questions."""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from discover_jobs import REPORT_PATH, kept_blocks, write_json

ROOT = Path(__file__).resolve().parents[1]
FILED_PATH = ROOT / "secrets" / "discovery_filed.json"
WEBHOOK = "http://127.0.0.1:5678/webhook/job-ingest"
UA = {"User-Agent": "discover-jobs"}


# --- Report rows ---

def new_jobs(text):
    jobs = []
    for block in kept_blocks(text):
        lines = block.splitlines()
        if not lines[0].startswith("- NEW |"):
            continue
        ats = lines[0].split("|")[4].strip()
        urls = [line.strip() for line in lines if line.strip().startswith("http")]
        if urls:
            jobs.append({"ats": ats, "url": urls[-1]})
    return jobs


# --- Job body ---

def fetch(url, accept):
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"], "Accept": accept})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def as_html(text):
    body = str(text or "").strip()
    if not body:
        return ""
    if "<" in body and ">" in body:
        return body
    return "<p>%s</p>" % body


def workable_html(url):
    match = re.search(r"/view/([^/]+)/", url)
    if not match:
        raise RuntimeError("workable url has no id")
    data = json.loads(fetch("https://jobs.workable.com/api/v1/jobs/" + match.group(1), "application/json"))
    parts = [data.get("description") or ""]
    extra = data.get("requirementsSection")
    if isinstance(extra, str):
        parts.append(extra)
    return as_html("\n".join(parts))


def lever_html(url):
    match = re.search(r"jobs\.lever\.co/([^/]+)/([^/?#]+)", url)
    if not match:
        raise RuntimeError("lever url has no id")
    api = "https://api.lever.co/v0/postings/%s/%s" % match.groups()
    data = json.loads(fetch(api, "application/json"))
    return as_html(data.get("description") or data.get("descriptionPlain") or "")


def greenhouse_html(url):
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not match:
        raise RuntimeError("greenhouse url has no id")
    slug, job_id = match.groups()
    api = "https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s" % (slug, job_id)
    data = json.loads(fetch(api, "application/json"))
    return as_html(data.get("content") or "")


def ashby_html(url):
    match = re.search(r"jobs\.ashbyhq.com/([^/]+)/", url)
    if not match:
        raise RuntimeError("ashby url has no board")
    api = "https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true" % match.group(1)
    data = json.loads(fetch(api, "application/json"))
    for job in data.get("jobs") or []:
        if str(job.get("jobUrl") or "").strip() == url or url.endswith("/" + str(job.get("id") or "")):
            return as_html(job.get("descriptionHtml") or job.get("descriptionPlain") or "")
    raise RuntimeError("ashby job not on the board")


def job_html(ats, url):
    if ats == "workable":
        return workable_html(url)
    if ats == "lever":
        return lever_html(url)
    if ats == "greenhouse":
        return greenhouse_html(url)
    if ats == "ashby":
        return ashby_html(url)
    return fetch(url, "text/html").decode("utf-8", "replace")


def post_ingest(url, html):
    body = json.dumps({"url": url, "html": html}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA["User-Agent"]},
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.status, response.read().decode("utf-8", "replace")


# --- Run ---

def run():
    report = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
    filed = {}
    if FILED_PATH.exists():
        filed = json.loads(FILED_PATH.read_text(encoding="utf-8"))
    pending = [job for job in new_jobs(report) if job["url"] not in filed]
    print("pending: %s" % len(pending))
    for job in pending:
        try:
            html = job_html(job["ats"], job["url"])
        except (urllib.error.URLError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            print("FETCH FAIL %s %s" % (job["url"], exc))
            continue
        if not html.strip():
            print("EMPTY %s" % job["url"])
            continue
        print("POST %s html=%s" % (job["url"], len(html)))
        try:
            status, raw = post_ingest(job["url"], html)
        except urllib.error.HTTPError as exc:
            print("HTTP %s %s" % (exc.code, job["url"]))
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print("POST FAIL %s %s" % (job["url"], exc))
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw[:400]}
        keep = {key: parsed.get(key) for key in ("status", "fit_score", "company", "job_title", "page_id", "message") if key in parsed}
        print("DONE http=%s %s" % (status, json.dumps(keep, ensure_ascii=False)))
        if status == 200 and parsed.get("status"):
            filed[job["url"]] = parsed["status"]
            write_json(FILED_PATH, filed)


def check():
    sample = "\n".join([
        "- already | x | d | pay n | jazzhr | **T** | C",
        "  https://example.com/a",
        "",
        "- NEW | y | d | pay n | wwr | **U** | D",
        "  https://example.com/b",
    ])
    assert new_jobs(sample) == [{"ats": "wwr", "url": "https://example.com/b"}]
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        run()
