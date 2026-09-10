#!/usr/bin/env python3
"""Number a master .tex, apply line-range patches, write complete copies."""

import argparse
import json
import os
import re
import sys
from datetime import date


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


# --- List repair (model patches sometimes drop itemize wrappers) ---

BEGIN_LIST_RE = re.compile(r"\\begin\{(itemize|enumerate)\}")
END_LIST_RE = re.compile(r"\\end\{(itemize|enumerate)\}")
ITEM_RE = re.compile(r"^\\item(\s|\[|$)")
LIST_BREAK_PREFIXES = (
    "\\section",
    "\\subsection",
    "\\newpage",
    "\\vspace",
    "\\noindent",
    "\\end{document}",
    "\\begin{document}",
)


def _list_name(match):
    return match.group(1) if match else "itemize"


def _is_item_line(line):
    return bool(ITEM_RE.match(str(line or "").lstrip()))


def _is_list_break(line):
    stripped = str(line or "").strip()
    if not stripped or stripped.startswith("%"):
        return bool(stripped)
    if _is_item_line(stripped):
        return False
    return any(stripped.startswith(prefix) for prefix in LIST_BREAK_PREFIXES)


def repair_lists(tex):
    """Insert missing \\begin{itemize}/\\end{itemize} around orphan \\item lines."""
    lines = str(tex or "").splitlines()
    out = []
    stack = []
    for line in lines:
        stripped = line.lstrip()
        begin = BEGIN_LIST_RE.search(line)
        end = END_LIST_RE.search(line)
        if begin and stripped.startswith("\\begin{"):
            stack.append(_list_name(begin))
            out.append(line)
            continue
        if end and stripped.startswith("\\end{"):
            if stack:
                stack.pop()
                out.append(line)
            continue
        if _is_item_line(line) and not stack:
            out.append("\\begin{itemize}")
            stack.append("itemize")
            out.append(line)
            continue
        if _is_list_break(line) and stack:
            while stack:
                out.append("\\end{%s}" % stack.pop())
            out.append(line)
            continue
        out.append(line)
    while stack:
        out.append("\\end{%s}" % stack.pop())
    result = "\n".join(out)
    if str(tex or "").endswith("\n"):
        result += "\n"
    return result


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


def tex_escape(text):
    out = str(text or "")
    for old, new in (
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
    ):
        out = out.replace(old, new)
    return out


HEADER_LINE_RE = re.compile(
    r"^((?:\\noindent\s+)?\\textbf\{(Date|To|Company|Location|Position):\}\s*).*$",
    re.M,
)


def letter_header_values(payload):
    today = date.today()
    letter_date = str(payload.get("letter_date") or "").strip()
    if not letter_date:
        letter_date = "%s %s, %s" % (today.strftime("%B"), today.day, today.year)
    return {
        "Date": letter_date,
        "To": str(payload.get("letter_to") or "Hiring Team").strip(),
        "Company": str(payload.get("company") or "").strip(),
        "Location": str(payload.get("location") or "").strip(),
        "Position": str(payload.get("job_title") or "").strip(),
    }


def apply_letter_header(text, payload):
    values = letter_header_values(payload)

    def repl(match):
        value = values.get(match.group(2)) or ""
        if not value:
            return match.group(0)
        return match.group(1) + tex_escape(value) + " \\\\"

    return HEADER_LINE_RE.sub(repl, text)


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


BEGIN_DOC = "\\begin{document}"
END_DOC = "\\end{document}"


def document_body(tex):
    text = str(tex or "")
    if BEGIN_DOC in text:
        text = text.split(BEGIN_DOC, 1)[1]
    if END_DOC in text:
        text = text.rsplit(END_DOC, 1)[0]
    return text.strip()


def splice_preamble(master, generated):
    """Keep master packages/colors; use generated document body."""
    master = str(master or "")
    generated = str(generated or "")
    if BEGIN_DOC not in master:
        return generated if generated.endswith("\n") else generated + "\n"
    body = document_body(generated)
    if not body:
        raise ValueError("generated tex has no document body")
    pre = master.split(BEGIN_DOC, 1)[0]
    return pre + BEGIN_DOC + "\n" + body + "\n" + END_DOC + "\n"


def letter_out_path(out_dir, company, title):
    return os.path.join(out_dir, "%s_%s_CoverLetter.tex" % (company, title))


def write_letter_only(payload, out_dir, letter_master=""):
    body = _letter_body(payload)
    if not str(body).strip():
        raise ValueError("latex_cover_letter is empty")
    letter_src = ""
    if letter_master and os.path.isfile(letter_master):
        with open(letter_master, "r") as handle:
            letter_src = handle.read()
    if LETTER_START in letter_src and LETTER_END in letter_src:
        letter_text = apply_letter_header(apply_letter(letter_src, body), payload)
        master_for_write = letter_master
    else:
        letter_text = wrap_letter(body)
        master_for_write = ""
    if not letter_text.endswith("\n"):
        letter_text += "\n"
    os.makedirs(out_dir, exist_ok=True)
    company = slug(payload.get("company"))
    title = slug(payload.get("job_title"))
    path = letter_out_path(out_dir, company, title)
    _write(path, letter_text, master_for_write)
    preview = letter_text if len(letter_text) <= 1900 else letter_text[:1899] + "\u2026"
    return {"letter_path": path, "letter_preview": preview}


def write_full(payload, out_dir, master_path="", letter_master=""):
    cv_text = str(payload.get("cv_tex") or "")
    letter_text = str(payload.get("letter_tex") or "")
    if not cv_text.strip():
        raise ValueError("cv_tex is empty")
    if not letter_text.strip():
        raise ValueError("letter_tex is empty")
    if master_path and os.path.isfile(master_path):
        with open(master_path, "r") as handle:
            cv_text = splice_preamble(handle.read(), cv_text)
    if letter_master and os.path.isfile(letter_master):
        with open(letter_master, "r") as handle:
            letter_text = splice_preamble(handle.read(), letter_text)
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
    parser.add_argument(
        "--cv-only",
        action="store_true",
        help="Apply mode: write the CV copy only (no cover letter)",
    )
    parser.add_argument(
        "--letter-only",
        action="store_true",
        help="Write cover letter body into the master letter; do not write a CV",
    )
    args = parser.parse_args()

    if args.letter_only:
        if not args.out_dir:
            raise SystemExit("--letter-only needs --out-dir")
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
            result = write_letter_only(payload, args.out_dir, args.letter)
            sys.stdout.write(json.dumps(result) + "\n")
        except Exception as exc:
            sys.stdout.write(json.dumps({"error": str(exc)}) + "\n")
            raise SystemExit(1)
        return

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

        cv_text = repair_lists(apply_patches(master, patches))
        os.makedirs(args.out_dir, exist_ok=True)
        company = slug(payload.get("company"))
        title = slug(payload.get("job_title"))
        cv_path = unique_path(args.out_dir, "%s_%s_CV.tex" % (company, title))
        _write(cv_path, cv_text, args.master)
        preview = cv_text if len(cv_text) <= 1900 else cv_text[:1899] + "\u2026"
        result = {"cv_path": cv_path, "cv_preview": preview}
        if not args.cv_only:
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
            letter_path = unique_path(
                args.out_dir, "%s_%s_CoverLetter.tex" % (company, title)
            )
            _write(letter_path, letter_text, letter_master)
            result["letter_path"] = letter_path
        sys.stdout.write(json.dumps(result) + "\n")
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}) + "\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
