#!/usr/bin/env python3
"""Copy one coordinator CV onto the other Operator Equity titles."""

import os
import re
import sys

from assemble_tex import slug

# --- Titles ---

TITLES = (
    "Project Manager, Marketing Operations",
    "Project Manager, Marketing Operations (Senior)",
    "Project Manager, Media Operations",
    "Senior Marketing Operations Project Manager",
)

HEADER_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)\\textbf\{(?P<title>[^{}]*)\}(?P<tail>[ \t]*\\\\)?[ \t]*$"
)


# --- Stamp ---

def replace_header(tex, new_title):
    found = {}

    def repl(match):
        if found:
            return match.group(0)
        found["title"] = match.group("title").strip()
        tail = match.group("tail") or ""
        return "%s\\textbf{%s}%s" % (match.group("indent"), new_title, tail)

    out = HEADER_RE.sub(repl, tex)
    if "title" not in found:
        raise SystemExit("no bold header line under the name")
    return out, found["title"]


def stamp_text(tex, new_title):
    stamped, source = replace_header(tex, new_title)
    if source not in TITLES:
        raise SystemExit("header title is not a coordinator title: %s" % source)
    if new_title not in TITLES or new_title == source:
        raise SystemExit("stamp target must be a different coordinator title")
    exact = re.compile(r"\\textbf\{" + re.escape(source) + r"\}")
    return exact.sub(lambda _match: "\\textbf{%s}" % new_title, stamped), source


def out_name(source_path, source_title, new_title):
    stem = os.path.splitext(os.path.basename(source_path))[0]
    if stem.endswith("_CV"):
        stem = stem[:-3]
    old = slug(source_title)
    prefix = stem[: -len(old)].rstrip("_") if stem.endswith(old) else ""
    name = slug(new_title) + "_CV.tex"
    if prefix:
        name = prefix + "_" + name
    return name


def stamp_file(path):
    with open(path, encoding="utf-8") as handle:
        tex = handle.read()
    source = source_title_of(tex)
    if source not in TITLES:
        raise SystemExit("header title is not a coordinator title: %s" % source)
    folder = os.path.dirname(os.path.abspath(path))
    written = []
    for title in TITLES:
        if title == source:
            continue
        stamped, _ = stamp_text(tex, title)
        dest = os.path.join(folder, out_name(path, source, title))
        if os.path.abspath(dest) == os.path.abspath(path):
            continue
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(stamped)
        written.append(dest)
    return written


def source_title_of(tex):
    match = HEADER_RE.search(tex)
    if not match:
        raise SystemExit("no bold header line under the name")
    return match.group("title").strip()


# --- Check ---

def check():
    sample = "\n".join([
        r"\begin{center}",
        r"    {\Huge \textbf{Mario Muñoz}} \\",
        r"    \textbf{Project Manager, Media Operations} \\",
        r"\end{center}",
        r"\noindent \textbf{Project Manager, Media Operations} with 12 years.",
        r"\noindent \textbf{Project Manager, Media Operations leader} stays.",
        r"A \textbf{later body mark} stays.",
        r"    \textbf{Keep this body line} \\",
    ])
    stamped, source = stamp_text(sample, "Project Manager, Marketing Operations")
    assert source == "Project Manager, Media Operations"
    assert r"\textbf{Project Manager, Marketing Operations} \\" in stamped
    assert r"\textbf{Project Manager, Media Operations} \\" not in stamped
    assert r"\textbf{Project Manager, Marketing Operations} with 12 years." in stamped
    assert r"\textbf{Project Manager, Media Operations leader}" in stamped
    assert r"\textbf{later body mark}" in stamped
    assert r"\textbf{Keep this body line}" in stamped
    assert r"\textbf{Mario Muñoz}" in stamped
    print("check ok")


def main():
    if len(sys.argv) == 1:
        check()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: stamp_cv.py [CV.tex]")
    for path in stamp_file(sys.argv[1]):
        print(path)


if __name__ == "__main__":
    main()
