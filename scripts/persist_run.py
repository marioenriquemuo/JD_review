#!/usr/bin/env python3
"""Persist or load JD Flow run state under secrets/runs/."""

import argparse
import json
import os
import re
import sys


def safe_id(page_id):
    text = str(page_id or "").strip()
    text = text.replace("-", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", text):
        raise ValueError("invalid page_id: %r" % (page_id,))
    return text.lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--read", action="store_true")
    parser.add_argument("--page-id", default="")
    args = parser.parse_args()

    if args.write == args.read:
        raise SystemExit("use exactly one of --write or --read")

    os.makedirs(args.runs_dir, exist_ok=True)

    if args.write:
        payload = json.loads(sys.stdin.read())
        page_id = safe_id(payload.get("page_id") or args.page_id)
        path = os.path.join(args.runs_dir, page_id + ".json")
        payload["page_id"] = page_id
        with open(path, "w") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        print(json.dumps({"ok": True, "path": path, "page_id": page_id}))
        return

    page_id = safe_id(args.page_id)
    path = os.path.join(args.runs_dir, page_id + ".json")
    if not os.path.isfile(path):
        print(json.dumps({
            "error": "no run state for page_id %s (re-run Phase 1 ingest so Persist Run State can write %s)" % (page_id, path)
        }))
        raise SystemExit(1)
    with open(path, "r") as handle:
        data = json.load(handle)
    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
