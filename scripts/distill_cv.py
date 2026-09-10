#!/usr/bin/env python3
"""One-time LaTeX CV + writing CSV → Notion-ready Markdown drafts.

Re-run after editing secrets/master_cv.tex. Paste only master_cv.md into the
Notion Master CV page. That page must keep EDUCATION, CERTIFICATIONS,
LANGUAGES, and SKILLS as separate headings (ATS + Haiku). Without --csv,
style_learnings.md is a placeholder — do not overwrite a real Style page.
"""

import argparse
import csv
import os
import re
import sys


COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?")
BRACE_RE = re.compile(r"\{([^{}]*)\}")


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
    return (
        "# Master CV\n\n"
        "Distilled from LaTeX. Keep this under ~1,000 tokens. "
        "Haiku sees the first ~2,500 characters; Sonnet gets the full page.\n\n"
        + body
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tex", required=True, help="Path to master CV .tex")
    parser.add_argument("--csv", default="", help="Path to past-writing CSV (optional)")
    parser.add_argument("--out-dir", default="", help="Write master_cv.md and style_learnings.md here")
    args = parser.parse_args()

    with open(args.tex, "r") as handle:
        cv_md = master_cv_wrapper(latex_to_markdown(handle.read()))

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
