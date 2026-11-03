#!/usr/bin/env python3
"""POST job-resume for each Proceed Phase 2 row, one at a time.

The webhook allows exactly one Proceed Phase 2 row. Extra rows wait as
Generating for that call. A failed call goes back to Proceed Phase 2.
Held rows are never selected.

Usage:
  python3 scripts/resume_phase2.py
  python3 scripts/resume_phase2.py --no-humanize
  python3 scripts/resume_phase2.py --held
  python3 scripts/resume_phase2.py --check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from answer_candidates import applications_db_id, notion, notion_token, prop_text

WEBHOOK = "http://127.0.0.1:5678/webhook/job-resume"
PARK = "Generating"
FAIL = "Proceed Phase 2"
WANT = "Proceed Phase 2"
HELD = "Held"
PY = "/home/mario/dev/n8n-automation/.venv/bin/python"
HUMANIZE = "/home/mario/dev/n8n-automation/scripts/humanize_tex.py"


def field_text(prop):
    if not prop:
        return ""
    if prop.get("type") == "number":
        num = prop.get("number")
        if num is None:
            return ""
        if isinstance(num, float) and num.is_integer():
            return str(int(num))
        return str(num)
    return prop_text(prop)


def fetch_status(token, db_id, status):
    cursor = None
    rows = []
    while True:
        body = {
            "page_size": 100,
            "filter": {"property": "Status", "select": {"equals": status}},
        }
        if cursor:
            body["start_cursor"] = cursor
        res = notion(token, "/databases/%s/query" % db_id, body)
        for page in res.get("results") or []:
            props = page["properties"]
            rows.append(
                {
                    "id": page["id"],
                    "title": prop_text(props.get("Job Title")),
                    "company": prop_text(props.get("Company")),
                    "url": prop_text(props.get("Job URL")),
                    "fit": field_text(props.get("Fit Score")),
                    "rationale": prop_text(props.get("Rationale")),
                }
            )
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")
    return rows


def fetch_proceed(token, db_id):
    return fetch_status(token, db_id, WANT)


def format_held(rows):
    lines = ["held %d" % len(rows)]
    for row in rows:
        lines.append("%s | %s" % (row.get("company") or "", row.get("title") or ""))
        lines.append("fit %s" % row.get("fit"))
        lines.append("rationale: %s" % (row.get("rationale") or ""))
        lines.append("url: %s" % (row.get("url") or ""))
    return "\n".join(lines)


def set_status(token, page_id, name):
    notion(
        token,
        "/pages/%s" % page_id,
        {"properties": {"Status": {"select": {"name": name}}}},
        method="PATCH",
    )


def post_resume(url):
    body = json.dumps({"url": url or "https://jd-flow.local/phase2"}).encode()
    req = urllib.request.Request(
        WEBHOOK,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.status, json.loads(resp.read().decode())


def humanize(cv_path):
    proc = subprocess.run(
        [PY, HUMANIZE, "--kind", "cv"],
        input=json.dumps({"cv_path": cv_path}).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    err = proc.stderr.decode("utf-8", "replace").strip()
    out = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode, out, err


def check():
    assert PARK == "Generating"
    assert FAIL == "Proceed Phase 2"
    assert WANT == "Proceed Phase 2"
    assert HELD != WANT
    assert WEBHOOK.endswith("/job-resume")
    assert format_held([]) == "held 0"
    sample = format_held(
        [
            {
                "company": "Acme",
                "title": "Ops",
                "fit": "74",
                "rationale": "Close match.",
                "url": "https://example.com/job",
            }
        ]
    )
    assert "Acme | Ops" in sample
    assert "fit 74" in sample
    assert "rationale: Close match." in sample
    assert "url: https://example.com/job" in sample
    print("check ok")


def run(do_humanize):
    token = notion_token()
    db_id = applications_db_id()
    queue = fetch_proceed(token, db_id)
    print("queue %d" % len(queue))
    if not queue:
        return
    for i, row in enumerate(queue):
        if i:
            set_status(token, row["id"], PARK)
    set_status(token, queue[0]["id"], WANT)
    time.sleep(0.5)
    failed = []
    for i, row in enumerate(queue):
        label = "%s | %s" % (row["company"], row["title"])
        if i:
            set_status(token, row["id"], WANT)
            time.sleep(0.4)
        print("\n=== %d/%d %s ===" % (i + 1, len(queue), label))
        try:
            status, parsed = post_resume(row["url"])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:500]
            print("HTTP %s %s" % (exc.code, body))
            failed.append(row["id"])
            set_status(token, row["id"], PARK)
            continue
        except Exception as exc:
            print("POST FAIL %s" % exc)
            failed.append(row["id"])
            try:
                set_status(token, row["id"], PARK)
            except Exception:
                pass
            continue
        # success path continues below; failures stay Generating until the queue ends
        print(
            "RESUME http=%s %s"
            % (
                status,
                json.dumps(
                    {
                        k: parsed.get(k)
                        for k in ("status", "company", "job_title", "cv_path", "message")
                        if k in parsed
                    },
                    ensure_ascii=False,
                ),
            )
        )
        cv_path = str(parsed.get("cv_path") or "").strip()
        if do_humanize and parsed.get("status") == "ready_to_apply" and cv_path:
            code, out, err = humanize(cv_path)
            print("HUMANIZE exit=%s %s" % (code, err.splitlines()[-1] if err else out[:200]))
            if code != 0 and err:
                print(err[-800:])
    for page_id in failed:
        set_status(token, page_id, FAIL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--held", action="store_true")
    parser.add_argument(
        "--no-humanize",
        action="store_true",
        help="skip humanize_tex.py (use after n8n already pipes assemble into it)",
    )
    args = parser.parse_args()
    if args.check:
        check()
        return
    if args.held:
        rows = fetch_status(notion_token(), applications_db_id(), HELD)
        print(format_held(rows))
        return
    run(do_humanize=not args.no_humanize)


if __name__ == "__main__":
    main()
