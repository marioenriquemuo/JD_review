#!/usr/bin/env python3
"""Print Notion IDs + Anthropic key from secrets/notion_ids.json."""

import json
import sys


def clean_id(value):
    text = str(value or "").strip()
    if text.startswith("="):
        text = text[1:]
    text = text.split("?", 1)[0].strip()
    return text


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: load_secret_ids.py PATH_TO_notion_ids.json")
    with open(sys.argv[1], "r") as handle:
        data = json.load(handle)
    out = {
        "applications_db_id": clean_id(data.get("applications_db_id")),
        "master_cv_page_id": clean_id(data.get("master_cv_page_id")),
        "style_learnings_page_id": clean_id(data.get("style_learnings_page_id")),
        "anthropic_api_key": str(data.get("anthropic_api_key") or "").strip(),
    }
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise SystemExit("missing fields in secrets file: " + ", ".join(missing))
    print(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main()
