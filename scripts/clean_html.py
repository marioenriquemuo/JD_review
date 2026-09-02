#!/usr/bin/env python3
"""Strip chrome/nav chrome from a JD HTML blob and emit Markdown JSON."""

import argparse
import base64
import json
import re
import sys

from bs4 import BeautifulSoup
import html2text


DROP_TAGS = (
    "script",
    "style",
    "svg",
    "nav",
    "footer",
    "header",
    "noscript",
    "iframe",
    "form",
    "button",
)


def html_to_markdown(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(list(DROP_TAGS)):
        tag.decompose()
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    markdown_text = converter.handle(str(soup))
    return re.sub(r"\n\s*\n", "\n\n", markdown_text).strip()


def load_payload(args):
    if args.b64:
        raw = base64.b64decode(args.b64)
        return json.loads(raw.decode("utf-8"))
    if args.infile:
        with open(args.infile, "r") as handle:
            return json.load(handle)
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("No input: pass --in, --b64, or JSON on stdin")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default="", help="JSON file with url + html")
    parser.add_argument("--out", dest="outfile", default="", help="Write JSON here instead of stdout")
    parser.add_argument("--b64", default="", help="Base64-encoded JSON payload")
    args = parser.parse_args()

    data = load_payload(args)
    url = data.get("url") or ""
    html = data.get("html") or data.get("content") or ""
    result = {"url": url, "clean_md": html_to_markdown(html)}

    encoded = json.dumps(result, ensure_ascii=False)
    if args.outfile:
        with open(args.outfile, "w") as handle:
            handle.write(encoded)
            handle.write("\n")
    else:
        sys.stdout.write(encoded)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
