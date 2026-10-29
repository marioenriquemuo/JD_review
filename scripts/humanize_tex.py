#!/usr/bin/env python3
"""Humanize assemble_tex JSON output; restore CV header; Never-claim fallback."""

import argparse
import json
import os
import re
import subprocess
import sys

from stamp_cv import HEADER_RE, replace_header

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUMAN_TEXT = os.path.abspath(os.path.join(ROOT, "..", "human-text"))
FACTS = os.path.join(ROOT, "secrets", "facts.md")
MASTER = os.path.join(ROOT, "secrets", "master_cv.tex")
UV = "/home/mario/.local/bin/uv"
UV_TIMEOUT = 300
ELLIPSIS = "\u2026"


# --- Facts gate ---

def never_claim_needles(facts):
    parts = facts.split("# Never Claim", 1)
    if len(parts) < 2:
        return []
    needles = []
    for raw in parts[1].splitlines():
        line = raw.strip()
        if not line.startswith("*"):
            continue
        body = line.lstrip("* ").strip()
        bold = re.match(r"\*\*([^*]+)\*\*", body)
        if bold:
            needles.append(bold.group(1).rstrip(":").strip())
            continue
        if ":" in body:
            needles.append(body.split(":", 1)[0].strip())
    return [item for item in needles if item]


def never_claim_hit(text, needles):
    hay = text.casefold()
    return any(item.casefold() in hay for item in needles)


# --- Header ---

def restore_header(pre, post):
    match = HEADER_RE.search(pre)
    if not match:
        return post
    title = match.group("title").strip()
    now = HEADER_RE.search(post)
    if now and now.group("title").strip() == title:
        return post
    try:
        out, _ = replace_header(post, title)
        return out
    except SystemExit:
        return post


# --- IO ---

def cap(text):
    text = str(text or "")
    if len(text) <= 1900:
        return text
    return text[:1899] + ELLIPSIS


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def write_text(path, text, master_path=""):
    if master_path and _same_file(path, master_path):
        raise SystemExit("refusing to overwrite master %s" % master_path)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w") as handle:
        handle.write(text)


def read_text(path):
    with open(path) as handle:
        return handle.read()


def load_facts():
    if not os.path.isfile(FACTS) or os.path.getsize(FACTS) == 0:
        raise SystemExit("secrets/facts.md missing or empty")
    text = read_text(FACTS).strip()
    if not text:
        raise SystemExit("secrets/facts.md missing or empty")
    return text


def parse_assemble(raw):
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise SystemExit("assemble_tex returned no JSON")
    data = json.loads(match.group(0))
    if data.get("error"):
        sys.stdout.write(json.dumps(data) + "\n")
        raise SystemExit(1)
    return data


def run_humanize(src, dest):
    uv = UV if os.path.isfile(UV) else "uv"
    cmd = [
        uv,
        "run",
        "--project",
        HUMAN_TEXT,
        os.path.join(HUMAN_TEXT, "humanize.py"),
        "--format",
        "tex",
        src,
        "-o",
        dest,
        "--facts",
        FACTS,
    ]
    env = os.environ.copy()
    env["PATH"] = "/home/mario/.local/bin:" + env.get("PATH", "")
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=UV_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("humanize timed out")
    err = proc.stderr.decode("utf-8", "replace")
    if err:
        sys.stderr.write(err)
        if not err.endswith("\n"):
            sys.stderr.write("\n")
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def process(kind, data):
    key = "cv_path" if kind == "cv" else "letter_path"
    path = str(data.get(key) or "").strip()
    if not path:
        raise SystemExit("assemble_tex returned no %s" % key)
    pre = read_text(path)
    facts = load_facts()
    tmp = path + ".humanize.tex"
    try:
        run_humanize(path, tmp)
        text = read_text(tmp)
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)
    if kind == "cv":
        text = restore_header(pre, text)
    if never_claim_hit(text, never_claim_needles(facts)):
        if kind == "cv":
            text = read_text(MASTER)
            sys.stderr.write("fallback master\n")
        else:
            text = pre
            sys.stderr.write("fallback pre-humanize\n")
    write_text(path, text, MASTER)
    preview = cap(text)
    if kind == "cv":
        data["cv_preview"] = preview
    else:
        data["letter_preview"] = preview
    return data


def check():
    facts = (
        "# Facts\n* Hello\n\n# Never Claim\n\n"
        "* **Salesforce:** no admin\n"
        "* **GEO measurement discipline:** none\n"
    )
    needles = never_claim_needles(facts)
    assert needles == ["Salesforce", "GEO measurement discipline"], needles
    assert never_claim_hit("I ran Salesforce admin.", needles)
    assert not never_claim_hit("I ran Google Ads.", needles)
    pre = "Name\n\\textbf{Old Title} \\\\\nHello\n"
    post = "Name\n\\textbf{New Title} \\\\\nHello\n"
    restored = restore_header(pre, post)
    assert HEADER_RE.search(restored).group("title").strip() == "Old Title"
    same = restore_header(pre, pre)
    assert same == pre
    data = {"cv_path": "/tmp/x_CV.tex", "cv_preview": "old"}
    data["cv_preview"] = cap("n" * 20)
    assert data["cv_preview"] == "n" * 20
    assert cap("n" * 1901).endswith(ELLIPSIS)
    print("check ok")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("cv", "letter"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        return
    if not args.kind:
        raise SystemExit("--kind is required unless --check")
    data = parse_assemble(sys.stdin.read())
    data = process(args.kind, data)
    sys.stdout.write(json.dumps(data) + "\n")


if __name__ == "__main__":
    main()
