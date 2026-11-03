#!/usr/bin/env python3
"""Write each run's CV basename onto its Notion row. Add Status option Applied.

Does not change Status.

Usage:
  python3 scripts/backfill_cv_file.py
  python3 scripts/backfill_cv_file.py --schema
  python3 scripts/backfill_cv_file.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import re

from answer_candidates import applications_db_id, notion, notion_token, rich_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "secrets", "runs")
PAGE_ID = re.compile(r"^[0-9a-f]{32}$")


def cv_file_name(path):
    name = os.path.basename(str(path or "").strip())
    if not name or name in (".", ".."):
        raise ValueError("bad cv path: %r" % (path,))
    return name


def runs_with_cv():
    rows = []
    for name in sorted(os.listdir(RUNS)):
        if not name.endswith(".json"):
            continue
        page_id = name[:-5].lower()
        if not PAGE_ID.fullmatch(page_id):
            print("SKIP bad page id %s" % name)
            continue
        with open(os.path.join(RUNS, name), "r") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            continue
        cv_path = str(data.get("cv_path") or "").strip()
        if not cv_path:
            continue
        rows.append((page_id, cv_path, cv_file_name(cv_path)))
    return rows


def missing_status(names):
    return [name for name in ("Applied", "Held") if name not in names]


def ensure_schema(token, db_id):
    db = notion(token, "/databases/" + db_id)
    props = db.get("properties") or {}
    cv = props.get("CV File")
    if cv is None:
        notion(
            token,
            "/databases/" + db_id,
            {"properties": {"CV File": {"rich_text": {}}}},
            method="PATCH",
        )
        print("added property CV File")
    elif cv.get("type") != "rich_text":
        raise SystemExit("CV File exists but is %s" % cv.get("type"))
    status = props.get("Status") or {}
    if status.get("type") != "select":
        raise SystemExit("Status is not a select")
    options = list((status.get("select") or {}).get("options") or [])
    names = {opt.get("name") for opt in options}
    missing = missing_status(names)
    for name in ("Applied", "Held"):
        if name in names:
            print("Status option %s already present" % name)
    if not missing:
        if "Needs Context" not in names:
            raise SystemExit("Status option Needs Context is missing")
        return
    kept = []
    for opt in options:
        item = {"name": opt["name"]}
        if opt.get("id"):
            item["id"] = opt["id"]
        if opt.get("color"):
            item["color"] = opt["color"]
        kept.append(item)
    colors = {"Applied": "green", "Held": "yellow"}
    for name in missing:
        kept.append({"name": name, "color": colors[name]})
    notion(
        token,
        "/databases/" + db_id,
        {"properties": {"Status": {"select": {"options": kept}}}},
        method="PATCH",
    )
    print("added Status option %s" % ", ".join(missing))
    if "Needs Context" not in names:
        raise SystemExit("Status option Needs Context is missing")


def patch_page(token, page_id, filename):
    try:
        notion(
            token,
            "/pages/" + page_id,
            {"properties": {"CV File": {"rich_text": rich_text(filename)}}},
            method="PATCH",
        )
    except SystemExit as exc:
        text = str(exc)
        if "Notion HTTP 404" in text or "archived" in text.lower():
            print("PAGE SKIP %s %s" % (page_id, text[:180]))
            return False
        raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        ensure_schema(notion_token(), applications_db_id())
        return
    if args.check:
        got = cv_file_name(
            "/home/mario/Downloads/BairesDev_Technical_Growth_Marketing_Manager_CV_2.tex"
        )
        assert got == "BairesDev_Technical_Growth_Marketing_Manager_CV_2.tex"
        assert cv_file_name("Foo_CV.tex") == "Foo_CV.tex"
        for bad in ("", "/"):
            try:
                cv_file_name(bad)
            except ValueError:
                continue
            raise SystemExit("expected ValueError for %r" % (bad,))
        assert missing_status({"Needs Context", "Applied"}) == ["Held"]
        assert missing_status({"Needs Context", "Applied", "Held"}) == []
        print("ok")
        return

    token = notion_token()
    db_id = applications_db_id()
    ensure_schema(token, db_id)
    wrote = 0
    missing = 0
    for page_id, cv_path, filename in runs_with_cv():
        if not os.path.isfile(cv_path):
            missing += 1
            print("FILE MISSING %s" % cv_path)
        if patch_page(token, page_id, filename):
            wrote += 1
            print("CV File %s %s" % (filename, page_id))
    print("wrote %d missing_files %d" % (wrote, missing))


if __name__ == "__main__":
    main()
