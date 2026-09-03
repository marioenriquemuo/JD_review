#!/usr/bin/env python3
"""Number a master .tex, apply line-range patches, write complete copies."""

import argparse
import json
import os
import re
import sys


LETTER_START = "% LETTER_BODY"
LETTER_END = "% END_LETTER_BODY"


# --- Numbering ---

def number_lines(text, cap=0):
    lines = text.splitlines()
    if cap:
        lines = lines[:cap]
    width = max(3, len(str(len(lines))))
    return "\n".join(
        "L%0*d: %s" % (width, i + 1, line) for i, line in enumerate(lines)
    )


# --- Patch application ---

def _ranges(patches, nlines):
    ranges = []
    for patch in patches:
        start = int(patch.get("start_line") or 0)
        end = int(patch.get("end_line") or 0)
        latex = patch.get("latex")
        latex = "" if latex is None else str(latex)
        if not latex.strip():
            continue
        if start < 1 or end < start or end > nlines:
            raise ValueError(
                "bad range %s-%s (file has %s lines)" % (start, end, nlines)
            )
        ranges.append((start, end, latex))
    ranges.sort(key=lambda item: item[0])
    for i in range(1, len(ranges)):
        if ranges[i][0] <= ranges[i - 1][1]:
            raise ValueError(
                "overlapping ranges %s-%s and %s-%s"
                % (ranges[i - 1][0], ranges[i - 1][1], ranges[i][0], ranges[i][1])
            )
    return ranges


def apply_patches(text, patches):
    lines = text.splitlines()
    ranges = _ranges(patches, len(lines))
    for start, end, latex in sorted(ranges, key=lambda item: item[0], reverse=True):
        lines[start - 1 : end] = latex.splitlines()
    out = "\n".join(lines)
    if text.endswith("\n"):
        out += "\n"
    return out


# --- Cover letter ---

def wrap_letter(body):
    return (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        + str(body).rstrip()
        + "\n\\end{document}\n"
    )


def apply_letter(master_text, body):
    if LETTER_START not in master_text or LETTER_END not in master_text:
        raise ValueError("letter master missing %s / %s" % (LETTER_START, LETTER_END))
    pre, rest = master_text.split(LETTER_START, 1)
    _mid, post = rest.split(LETTER_END, 1)
    return (
        pre
        + LETTER_START
        + "\n"
        + str(body).rstrip()
        + "\n"
        + LETTER_END
        + post
    )


# --- Output paths ---

def slug(value):
    text = re.sub(r"[^\w\s-]", "", str(value or ""), flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text[:60] or "untitled"


def unique_path(out_dir, filename):
    path = os.path.join(out_dir, filename)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(filename)
    n = 2
    while True:
        path = os.path.join(out_dir, "%s_%s%s" % (stem, n, ext))
        if not os.path.exists(path):
            return path
        n += 1


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def _write(path, text, master_path):
    if master_path and _same_file(path, master_path):
        raise ValueError("refusing to overwrite master %s" % master_path)
    with open(path, "w") as handle:
        handle.write(text)


def _letter_body(payload):
    letter = payload.get("latex_cover_letter")
    if letter is None:
        return ""
    if isinstance(letter, dict):
        return str(letter.get("latex") or "")
    return str(letter)


# --- Full write (Phase 2/3) ---

def write_full(payload, out_dir, master_path="", letter_master=""):
    cv_text = str(payload.get("cv_tex") or "")
    letter_text = str(payload.get("letter_tex") or "")
    if not cv_text.strip():
        raise ValueError("cv_tex is empty")
    if not letter_text.strip():
        raise ValueError("letter_tex is empty")
    os.makedirs(out_dir, exist_ok=True)
    company = slug(payload.get("company"))
    title = slug(payload.get("job_title"))
    cv_path = unique_path(out_dir, "%s_%s_CV.tex" % (company, title))
    letter_path = unique_path(
        out_dir, "%s_%s_CoverLetter.tex" % (company, title)
    )
    _write(cv_path, cv_text if cv_text.endswith("\n") else cv_text + "\n", master_path)
    _write(
        letter_path,
        letter_text if letter_text.endswith("\n") else letter_text + "\n",
        letter_master,
    )
    return {"cv_path": cv_path, "letter_path": letter_path}


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", default="", help="Read-only master CV .tex")
    parser.add_argument("--letter", default="", help="Optional master letter .tex")
    parser.add_argument("--out-dir", default="", help="Write copies here (apply mode)")
    parser.add_argument("--number", action="store_true", help="Print numbered lines")
    parser.add_argument(
        "--write-full",
        action="store_true",
        help="Write complete cv_tex + letter_tex from stdin JSON",
    )
    parser.add_argument("--cap", type=int, default=350, help="Max lines for --number")
    args = parser.parse_args()

    if args.write_full:
        if not args.out_dir:
            raise SystemExit("--write-full needs --out-dir")
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
            result = write_full(payload, args.out_dir, args.master, args.letter)
            sys.stdout.write(json.dumps(result) + "\n")
        except Exception as exc:
            sys.stdout.write(json.dumps({"error": str(exc)}) + "\n")
            raise SystemExit(1)
        return

    if not args.master:
        raise SystemExit("--master is required unless --write-full")

    with open(args.master, "r") as handle:
        master = handle.read()

    if args.number:
        sys.stdout.write(number_lines(master, cap=args.cap) + "\n")
        return

    if not args.out_dir:
        raise SystemExit("apply mode needs --out-dir")

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        patches = payload.get("latex_cv_patches") or []
        if not isinstance(patches, list):
            patches = [patches]

        cv_text = apply_patches(master, patches)
        body = _letter_body(payload)
        if args.letter:
            with open(args.letter, "r") as handle:
                letter_src = handle.read()
            if LETTER_START in letter_src and LETTER_END in letter_src:
                letter_text = apply_letter(letter_src, body)
                letter_master = args.letter
            else:
                letter_text = wrap_letter(body)
                letter_master = ""
        else:
            letter_text = wrap_letter(body)
            letter_master = ""

        os.makedirs(args.out_dir, exist_ok=True)
        company = slug(payload.get("company"))
        title = slug(payload.get("job_title"))
        cv_path = unique_path(args.out_dir, "%s_%s_CV.tex" % (company, title))
        letter_path = unique_path(
            args.out_dir, "%s_%s_CoverLetter.tex" % (company, title)
        )
        _write(cv_path, cv_text, args.master)
        _write(letter_path, letter_text, letter_master)
        sys.stdout.write(
            json.dumps({"cv_path": cv_path, "letter_path": letter_path}) + "\n"
        )
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}) + "\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
