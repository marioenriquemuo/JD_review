#!/usr/bin/env python3
"""Fill Notion Candidate Answers from secrets/facts.md; ask gaps in the terminal.

Scope: Status=Needs Context and empty Candidate Answers.
After each row: write answers, Status=Proceed Phase 2. Does not call job-resume.

Usage:
  python3 scripts/answer_candidates.py
  python3 scripts/answer_candidates.py --check
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# --- Paths ---

ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "secrets" / "facts.md"
IDS_PATH = ROOT / "secrets" / "notion_ids.json"
N8N_CONFIG = Path("/home/mario/external_storage/n8n_data/config")
N8N_DB = Path("/home/mario/external_storage/n8n_data/database.sqlite")
NOTION_VERSION = "2022-06-28"
HAIKU = "claude-haiku-4-5-20251001"


# --- Notion auth ---

def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16):
    dt = b""
    prev = b""
    while len(dt) < key_len + iv_len:
        prev = hashlib.md5(prev + password + salt).digest()
        dt += prev
    return dt[:key_len], dt[key_len : key_len + iv_len]


def _decrypt_cryptojs(b64: str, passphrase: str) -> str:
    raw = base64.b64decode(b64)
    salt, body = raw[8:16], raw[16:]
    key, iv = _evp_bytes_to_key(passphrase.encode(), salt)
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    out = dec.update(body) + dec.finalize()
    return out[: -out[-1]].decode()


def notion_token() -> str:
    env = (os.environ.get("NOTION_TOKEN") or "").strip()
    if env:
        return env
    if not N8N_CONFIG.is_file() or not N8N_DB.is_file():
        raise SystemExit(
            "Set NOTION_TOKEN or keep n8n credentials at "
            "/home/mario/external_storage/n8n_data/"
        )
    cfg = json.loads(N8N_CONFIG.read_text())
    con = sqlite3.connect("file:%s?mode=ro" % N8N_DB, uri=True)
    blob = con.execute(
        "SELECT data FROM credentials_entity WHERE type='notionApi'"
    ).fetchone()[0]
    return json.loads(_decrypt_cryptojs(blob, cfg["encryptionKey"]))["apiKey"]


def applications_db_id() -> str:
    data = json.loads(IDS_PATH.read_text())
    return str(data["applications_db_id"]).split("?", 1)[0].strip()


def anthropic_key() -> str:
    data = json.loads(IDS_PATH.read_text())
    key = str(data.get("anthropic_api_key") or "").strip()
    if not key:
        raise SystemExit("anthropic_api_key missing in secrets/notion_ids.json")
    return key


# --- Notion HTTP ---

def notion(token: str, path: str, payload=None, method: str | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path,
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode() if exc.fp else ""
            if exc.code in (429, 502, 503) and attempt < 3:
                time.sleep(2 + attempt * 2)
                continue
            raise SystemExit("Notion HTTP %s: %s" % (exc.code, body[:500]))


def prop_text(prop) -> str:
    if not prop:
        return ""
    kind = prop.get("type")
    if kind == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text") or [])
    if kind == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title") or [])
    if kind == "select":
        return (prop.get("select") or {}).get("name") or ""
    if kind == "url":
        return prop.get("url") or ""
    return ""


def rich_text(content: str, limit: int = 1900):
    text = content or ""
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return [{"type": "text", "text": {"content": text}}]


# --- Questions / facts ---

def parse_questions(notes: str) -> list[str]:
    notes = (notes or "").strip()
    if not notes or notes.lower() in ("- none", "none"):
        return []
    parts = re.split(r"(?m)^\s*\d+\.\s+", notes)
    return [p.strip() for p in parts if p.strip()]


def load_facts() -> str:
    if not FACTS_PATH.is_file() or FACTS_PATH.stat().st_size == 0:
        raise SystemExit("secrets/facts.md missing or empty")
    return FACTS_PATH.read_text(encoding="utf-8")


def append_fact(line: str) -> None:
    line = line.strip()
    if not line:
        return
    if not line.startswith("*"):
        line = "* " + line.lstrip("-").strip()
    text = FACTS_PATH.read_text(encoding="utf-8")
    # skip if already present (case-folded)
    if line.lstrip("* ").strip().casefold() in text.casefold():
        return
    # insert before Never claim when possible
    marker = "\n# Never Claim\n"
    if marker in text:
        text = text.replace(marker, "\n" + line + "\n" + marker, 1)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    FACTS_PATH.write_text(text, encoding="utf-8")


def haiku_map(facts: str, questions: list[str], api_key: str) -> list[dict]:
    """Return list of {i, answer?} or {i, missing: true}. 1-based i."""
    if not questions:
        return []
    numbered = "\n".join("%d. %s" % (i + 1, q) for i, q in enumerate(questions))
    system = (
        "You map Candidate notes questions to secrets/facts.md. "
        "Answer ONLY with facts present in FACTS (including Never claim). "
        "If FACTS already answers the question (including an explicit Never claim / No), "
        "return that answer — do not mark missing. "
        "Mark missing only when FACTS has no clear answer. "
        "Never invent employers, metrics, tools, or stories. "
        "Return JSON only: {\"items\":[{\"i\":1,\"answer\":\"...\"}|{\"i\":1,\"missing\":true},...]}"
    )
    user = "FACTS:\n%s\n\nQUESTIONS:\n%s" % (facts, numbered)
    body = {
        "model": HAIKU,
        "max_tokens": 2000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode())
    text = ""
    for block in payload.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text") or ""
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return [{"i": i + 1, "missing": True} for i in range(len(questions))]
    parsed = json.loads(match.group(0))
    items = parsed.get("items") or []
    by_i = {int(it["i"]): it for it in items if "i" in it}
    out = []
    for i in range(len(questions)):
        n = i + 1
        it = by_i.get(n) or {"i": n, "missing": True}
        ans = str(it.get("answer") or "").strip()
        if it.get("missing") or not ans:
            out.append({"i": n, "missing": True})
        else:
            out.append({"i": n, "answer": ans})
    return out


def ask_terminal(company: str, title: str, n: int, question: str) -> str:
    print()
    print("=" * 72)
    print("%s | %s" % (company, title))
    print("Q%d: %s" % (n, question))
    print("Not in secrets/facts.md. Type the fact (one short line). Empty = skip claim.")
    try:
        return input("A%d> " % n).strip()
    except EOFError:
        return ""


def format_answers(questions: list[str], answers: list[str]) -> str:
    if not questions:
        return ""
    parts = []
    for i, (q, a) in enumerate(zip(questions, answers), 1):
        parts.append("%d. Q: %s\nA: %s" % (i, q, a))
    return "\n\n".join(parts)


# --- Main loop ---

def fetch_rows(token: str, db_id: str) -> list[dict]:
    rows = []
    cursor = None
    while True:
        body = {
            "filter": {"property": "Status", "select": {"equals": "Needs Context"}},
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor
        res = notion(token, "/databases/%s/query" % db_id, body)
        for page in res.get("results") or []:
            props = page["properties"]
            if prop_text(props.get("Candidate Answers")).strip():
                continue
            rows.append(
                {
                    "id": page["id"],
                    "title": prop_text(props.get("Job Title")),
                    "company": prop_text(props.get("Company")),
                    "notes": prop_text(props.get("Candidate notes")),
                }
            )
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")
    return rows


def process_row(row: dict, token: str, api_key: str) -> dict:
    facts = load_facts()
    questions = parse_questions(row["notes"])
    if not questions:
        notion(
            token,
            "/pages/%s" % row["id"],
            {
                "properties": {
                    "Candidate Answers": {"rich_text": rich_text("")},
                    "Status": {"select": {"name": "Proceed Phase 2"}},
                }
            },
            method="PATCH",
        )
        return {"company": row["company"], "title": row["title"], "asked": 0, "from_facts": 0}

    mapped = haiku_map(facts, questions, api_key)
    answers = [""] * len(questions)
    asked = 0
    from_facts = 0
    for item in mapped:
        i = int(item["i"]) - 1
        q = questions[i]
        if not item.get("missing") and item.get("answer"):
            answers[i] = item["answer"]
            from_facts += 1
            continue
        # Haiku already checked FACTS; only then ask in the terminal.
        user_ans = ask_terminal(row["company"], row["title"], i + 1, q)
        asked += 1
        if user_ans:
            answers[i] = user_ans
            append_fact(user_ans)
            facts = load_facts()
        else:
            answers[i] = "No additional claim (not in fact card)."

    body = {
        "properties": {
            "Candidate Answers": {"rich_text": rich_text(format_answers(questions, answers))},
            "Status": {"select": {"name": "Proceed Phase 2"}},
        }
    }
    notion(token, "/pages/%s" % row["id"], body, method="PATCH")
    return {
        "company": row["company"],
        "title": row["title"],
        "asked": asked,
        "from_facts": from_facts,
    }


def check() -> None:
    qs = parse_questions("1. Foo?\n2. Bar baz?\n")
    assert qs == ["Foo?", "Bar baz?"], qs
    assert parse_questions("- none") == []
    assert parse_questions("") == []
    sample = "# Facts\n\n* Hello\n\n# Never Claim\n\n* Nope\n"
    path = FACTS_PATH
    prev = path.read_text(encoding="utf-8") if path.is_file() else None
    try:
        path.write_text(sample, encoding="utf-8")
        append_fact("New durable fact about X")
        text = path.read_text(encoding="utf-8")
        assert "New durable fact about X" in text
        assert text.index("New durable fact") < text.index("# Never Claim")
        append_fact("New durable fact about X")  # dedupe
        assert text.count("New durable fact about X") == path.read_text(encoding="utf-8").count(
            "New durable fact about X"
        )
    finally:
        if prev is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(prev, encoding="utf-8")
    print("check ok")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        check()
        return
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)

    token = notion_token()
    db_id = applications_db_id()
    api_key = anthropic_key()
    rows = fetch_rows(token, db_id)
    if not rows:
        print("No Needs Context rows with empty Candidate Answers.")
        return

    print("Jobs to fill: %d (stops at Proceed Phase 2; no job-resume)" % len(rows))
    summary = []
    for row in rows:
        print("\n--- %s | %s ---" % (row["company"], row["title"]))
        summary.append(process_row(row, token, api_key))
        time.sleep(0.3)

    print("\nDone. Leave exactly one Proceed Phase 2 row before Continue Phase 2.")
    for item in summary:
        print(
            "- %s | %s | from_facts=%s asked=%s"
            % (item["company"], item["title"], item["from_facts"], item["asked"])
        )


if __name__ == "__main__":
    main()
