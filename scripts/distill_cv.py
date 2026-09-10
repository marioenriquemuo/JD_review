#!/usr/bin/env python3
"""Distill master_cv.tex to markdown; optional CSV → style draft.

Runtime: --verify-json prints {cv_md, ok, missing} from the .tex (no second
source of truth). --out-dir still writes drafts for optional Notion Style page.
Without --csv, style_learnings.md is a placeholder — do not overwrite a real
Style page.
"""

import argparse
import csv
import json
import os
import re
import sys


COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?")
BRACE_RE = re.compile(r"\{([^{}]*)\}")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?%")
DOLLAR_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
TEXTBF_RE = re.compile(r"\\textbf\{([^{}]+)\}")
BEGIN_DOC = "\\begin{document}"
END_DOC = "\\end{document}"


def latex_to_markdown(tex):
    if "\\begin{document}" in tex:
        tex = tex.split("\\begin{document}", 1)[1]
    if "\\end{document}" in tex:
        tex = tex.split("\\end{document}", 1)[0]
    text = re.sub(r"(?<!\\)%.*", "", tex)
    text = text.replace("\\&", "&").replace("\\%", "%")
    text = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\section\*\{([^{}]+)\}", r"\n## \1\n", text)
    text = re.sub(r"\\subsection\*\{([^{}]+)\}", r"\n### \1\n", text)
    text = re.sub(r"\\textbf\{([^{}]+)\}", r"**\1**", text)
    text = re.sub(r"\\textit\{([^{}]+)\}", r"*\1*", text)
    text = re.sub(r"\\emph\{([^{}]+)\}", r"*\1*", text)
    text = re.sub(r"\\hfill", " — ", text)
    text = re.sub(r"\\(?:vspace|hspace)\{[^}]*\}", "", text)
    text = re.sub(r"\\newpage", "\n", text)
    text = re.sub(r"\\noindent\s*", "", text)
    text = text.replace("\\begin{center}", "").replace("\\end{center}", "")
    text = text.replace("\\\\", "\n")
    text = re.sub(r"\\item\s*", "\n- ", text)
    text = text.replace("\\begin{itemize}", "").replace("\\end{itemize}", "")
    text = text.replace("\\begin{enumerate}", "").replace("\\end{enumerate}", "")
    text = re.sub(r"\\(?:Huge|LARGE|Large|large|bfseries)\s*", "", text)
    for _ in range(8):
        text = COMMAND_RE.sub("", text)
        text = BRACE_RE.sub(r"\1", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _document_body(tex):
    text = str(tex or "")
    if BEGIN_DOC in text:
        text = text.split(BEGIN_DOC, 1)[1]
    if END_DOC in text:
        text = text.rsplit(END_DOC, 1)[0]
    return text


def _unescape_latex(text):
    return str(text or "").replace("\\%", "%").replace("\\$", "$").replace("\\&", "&")


def extract_facts(tex):
    body = _document_body(tex)
    unesc = _unescape_latex(body)
    facts = []
    seen = set()

    def add(value):
        item = str(value or "").strip()
        if len(item) < 2:
            return
        key = item.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append(item)

    for match in YEAR_RE.findall(unesc):
        add(match)
    for match in PERCENT_RE.findall(unesc):
        add(match)
    for match in DOLLAR_RE.findall(unesc):
        add(match)
    for match in TEXTBF_RE.findall(body):
        add(_unescape_latex(match))
    return facts


def verify_facts(tex, md):
    hay = str(md or "").lower()
    return [fact for fact in extract_facts(tex) if fact.lower() not in hay]


def _cell_text(row, key):
    value = row.get(key)
    if value is None:
        return ""
    return str(value).strip()


def distill_csv(path):
    with open(path, "r") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    preferred = [
        name
        for name in fieldnames
        if re.search(r"text|note|writ|body|content|letter|bullet|style|tone", name, re.I)
    ]
    columns = preferred or [
        name for name in fieldnames if name and name.lower() not in ("id", "url", "date")
    ]

    snippets = []
    for row in rows:
        for name in columns:
            cell = _cell_text(row, name)
            if len(cell) >= 40:
                snippets.append(cell)

    sentences = []
    for snippet in snippets:
        for piece in re.split(r"(?<=[.!?])\s+", snippet):
            piece = piece.strip()
            if 40 <= len(piece) <= 240:
                sentences.append(piece)

    avoid_words = ("passionate", "synergistic", "results-oriented", "team player")
    unique = []
    seen = set()
    for sentence in sentences:
        key = sentence.lower()
        if any(w in key for w in avoid_words):
            continue
        if key not in seen:
            seen.add(key)
            unique.append(sentence)
        if len(unique) >= 15:
            break

    lines = [
        "# Style & Learnings",
        "",
        "Edit this page. The Sonnet node injects it verbatim when fit >= 70%.",
        "",
        "## Rules",
        "- Tone: concise, specific, first person where a cover letter needs it.",
        "- Lead with metrics (%, $, time saved, scale) when the JD names that outcome.",
        "- Mirror JD keywords in CV bullets; do not invent employers or dates.",
        "- Cover letter: exactly 3 short paragraphs. No generic 'passionate about'.",
        "- Never dump raw application history into the letter.",
        "",
        "## Phrases to prefer",
    ]
    if unique:
        for sentence in unique:
            lines.append("- " + sentence)
    else:
        lines.append("- (CSV had no long text cells — add 5–10 sentences you actually use.)")
    lines.extend(
        [
            "",
            "## Phrases to avoid",
            "- Passionate, synergistic, results-oriented, team player.",
            "",
            "## Metrics to highlight",
            "- Add 3–5 numbers from the Master CV that you want reused.",
        ]
    )
    return "\n".join(lines) + "\n"


def master_cv_wrapper(body):
    return "# Master CV\n\n" + body + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tex", required=True, help="Path to master CV .tex")
    parser.add_argument("--csv", default="", help="Path to past-writing CSV (optional)")
    parser.add_argument("--out-dir", default="", help="Write master_cv.md and style_learnings.md here")
    parser.add_argument(
        "--verify-json",
        action="store_true",
        help="Print {cv_md, ok, missing} JSON; exit 1 if facts dropped",
    )
    args = parser.parse_args()

    with open(args.tex, "r") as handle:
        tex = handle.read()
    body_md = latex_to_markdown(tex)
    cv_md = master_cv_wrapper(body_md)

    if args.verify_json:
        missing = verify_facts(tex, cv_md)
        payload = {"cv_md": cv_md, "ok": not missing, "missing": missing}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        if missing:
            raise SystemExit(1)
        return

    if args.csv:
        style_md = distill_csv(args.csv)
    else:
        style_md = (
            "# Style & Learnings\n\n"
            "No CSV passed. Add 10–20 rules: tone, metrics to highlight, phrases to avoid.\n"
        )

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        cv_path = os.path.join(args.out_dir, "master_cv.md")
        style_path = os.path.join(args.out_dir, "style_learnings.md")
        with open(cv_path, "w") as handle:
            handle.write(cv_md)
        with open(style_path, "w") as handle:
            handle.write(style_md)
        sys.stdout.write("Wrote %s\nWrote %s\n" % (cv_path, style_path))
        return

    sys.stdout.write("===== MASTER CV =====\n")
    sys.stdout.write(cv_md)
    sys.stdout.write("\n===== STYLE & LEARNINGS =====\n")
    sys.stdout.write(style_md)


if __name__ == "__main__":
    main()
