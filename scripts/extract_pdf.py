#!/usr/bin/env python3
"""Extract text from a JD PDF and emit JSON with only url + clean_md."""

import argparse
import base64
import json
import re
import sys
from io import BytesIO

from pypdf import PdfReader


def pdf_to_text(raw):
    reader = PdfReader(BytesIO(raw))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n\n".join(pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        short = sum(1 for ln in lines if len(ln) <= 40)
        if short / float(len(lines)) >= 0.7:
            text = " ".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_payload(args):
    if args.pdf:
        with open(args.pdf, "rb") as handle:
            raw = handle.read()
        return {"url": args.url, "pdf_bytes": raw}
    if args.b64:
        raw = base64.b64decode(args.b64)
        return json.loads(raw.decode("utf-8"))
    if args.infile:
        with open(args.infile, "r") as handle:
            return json.load(handle)
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("No input: pass --pdf, --in, --b64, or JSON on stdin")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default="", help="JSON file with url + pdf_b64")
    parser.add_argument("--out", dest="outfile", default="", help="Write JSON here instead of stdout")
    parser.add_argument("--b64", default="", help="Base64-encoded JSON payload")
    parser.add_argument("--pdf", default="", help="Raw PDF file (for local checks)")
    parser.add_argument("--url", default="", help="URL to include when using --pdf")
    args = parser.parse_args()

    data = load_payload(args)
    url = data.get("url") or args.url or ""
    if data.get("pdf_bytes") is not None:
        raw = data["pdf_bytes"]
    else:
        pdf_b64 = data.get("pdf_b64") or ""
        if not pdf_b64:
            raise SystemExit("No pdf_b64 in payload")
        raw = base64.b64decode(pdf_b64)

    clean_md = pdf_to_text(raw)
    if not clean_md:
        raise SystemExit("PDF had no extractable text (scanned PDFs are not supported)")

    result = {"url": url, "clean_md": clean_md}
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
