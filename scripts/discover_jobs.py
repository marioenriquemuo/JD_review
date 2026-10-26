#!/usr/bin/env python3
"""Poll Greenhouse, Lever, Ashby, JazzHR, and remote feeds. Write a local job list."""

import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARDS_PATH = ROOT / "data" / "boards.json"
SEEN_PATH = ROOT / "secrets" / "discovery_seen.json"
REPORT_PATH = ROOT / "secrets" / "discovery_latest.md"
DAYS = 7
LIMIT = 10
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
UA = {"User-Agent": "discover-jobs"}

# --- Filters ---

TITLE_RES = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bad\s*ops\b",
        r"\bad operations\b",
        r"\badvertising operations\b",
        r"\bad[- ]?tech\b",
        r"\bmar-?tech\b",
        r"\bmops\b",
        r"\bmarketing operations\b",
        r"\bmarketing ops\b",
        r"\bmedia operations\b",
        r"\bmedia ops\b",
        r"\bgrowth operations\b",
        r"\bcampaign operations\b",
        r"\bcampaign delivery\b",
        r"\bcampaign (qa|quality)\b",
        r"\bcampaign lead\b",
        r"\bad verification\b",
        r"\bqa operations\b",
        r"\btraffick\w*\b",
        r"\btagg?ing governance\b",
        r"\bpaid media\b",
        r"\bperformance marketing\b",
        r"\btracking (implementation|governance)\b",
        r"\bga4\b",
        r"\be-?commerce growth\b",
        r"\be-?commerce\b.{0,40}\boperations\b",
        r"\banalytics delivery\b",
        r"\banalytics (manager|director|lead)\b",
        r"\b(manager|director|lead) of analytics\b",
        r"\bdigital analytics\b",
        r"\bmarketing effectiveness\b",
        r"\bmeasurement\b.{0,40}\b(?:operations|marketing)\b",
        r"\b(?:operations|marketing)\b.{0,40}\bmeasurement\b",
        r"\battribution\b",
        r"\bmarketing reporting\b",
        r"\bdata operations\b",
        r"\bmarketing data\b",
        r"\b(marketing|media) (program|project) manager\b",
        r"\b(program|project) manager\b.{0,50}\b(marketing|media|ad\s*ops|mops)\b",
        r"\b(ad\s*ops|marketing operations|media operations)\b.{0,50}\b(program|project) manager\b",
        r"\bagency delivery\b",
        r"\bclient delivery\b",
        r"\bdigital agency\b",
        r"\bdigital production\b",
        r"\bworkflow (consultant|automation)\b",
        r"\bmarketing workflow\b",
        r"\bfractional\b.{0,40}\b(media|marketing|ad)\b",
        r"\b(cac|ltv)\b",
        r"\btraffic manager\b",
        r"\bmedia implementation\b",
        r"\binsights operations\b",
        r"\bmarketing bi\b",
        r"\bconversion rate optimization\b",
        r"\bcro\b.{0,20}\boperations\b",
        r"\bgrowth marketing\b.{0,40}\boperations\b",
        r"\boperations\b.{0,40}\bgrowth marketing\b",
        r"\bretention operations\b",
        r"\bmedia planning (manager|director|lead)\b",
        r"\bmedia strategy\b.{0,30}\boperations\b",
        r"\bmedia buyer\b.{0,40}\boperations\b",
        r"\boperations\b.{0,40}\bmedia buyer\b",
        r"\bmarketing infrastructure\b",
    )
)
KEEP_RE = re.compile(
    r"\b(contractor|freelance\w*|consultant|worldwide|anywhere|latam|latin america|americas|eor)\b",
    re.I,
)
DROP_RE = re.compile(
    r"("
    r"authori[sz]ed to work"
    r"|work authori[sz]ation"
    r"|security clearance"
    r"|\b(u\.s\.|us|united states)\b.{0,40}\b(citizen|citizenship)\b"
    r"|\b(citizen|citizenship)\b.{0,40}\b(u\.s\.|us|united states)\b"
    r"|anywhere in the (united states|u\.s\.a\.|u\.s\.|usa|us)\b"
    r"|\bmust (?:be )?(?:located|based|reside|live) in the (united states|u\.s\.|usa|us)\b"
    r")",
    re.I,
)
HYBRID_LOC_RE = re.compile(r"\bhybrid\b", re.I)
HYBRID_TEXT_RE = re.compile(
    r"(\bhybrid\b.{0,50}\b(office|on-?site|in[- ]office)\b"
    r"|\b\d+\s+days?\s+(a|per)\s+week\b.{0,30}\b(office|hybrid|on-?site)\b)",
    re.I,
)
CONTRACT_RE = re.compile(r"\b(contractor|freelance\w*|consultant|eor|1099)\b", re.I)
PAY_RE = re.compile(
    r"(\$\s?\d[\d,]*(?:\s*[kK])?(?:\s*[-–]\s*\$?\s?\d[\d,]*(?:\s*[kK])?)?)",
)


def title_ok(title):
    text = title or ""
    return any(pattern.search(text) for pattern in TITLE_RES)


def hybrid_city(location, text):
    if HYBRID_LOC_RE.search(location or ""):
        return True
    return bool(HYBRID_TEXT_RE.search(text or ""))


def colombia_ok(location, text):
    blob = f"{location or ''}\n{text or ''}"
    if DROP_RE.search(blob) or hybrid_city(location, blob):
        return False
    return bool(KEEP_RE.search(blob))


def contractor_flag(location, text):
    return bool(CONTRACT_RE.search(f"{location or ''}\n{text or ''}"))


def pay_label(text, structured=""):
    if structured:
        return structured[:160]
    matches = PAY_RE.findall(text or "")
    if not matches:
        return "unknown"

    def amount(raw):
        nums = re.findall(r"\d[\d,]*", raw)
        return float(nums[0].replace(",", "")) if nums else 0

    sized = [match for match in matches if amount(match) >= 1000]
    return (sized or matches)[0].strip()


def pay_note(pay):
    text = (pay or "").strip()
    if not text or text == "unknown":
        return "unknown"
    nums = [float(raw.replace(",", "")) for raw in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
    if not nums:
        return text
    amount = nums[0]
    if amount > 20000:
        amount /= 12
    if amount < 3500 and "below 3500" not in text:
        return f"{text} below 3500"
    return text


def fit_rank(location, text):
    blob = f"{location or ''}\n{text or ''}"
    blocked = DROP_RE.search(blob) or hybrid_city(location, blob)
    # Location only. JazzHR descriptions mention every country they hire in.
    if not blocked and re.search(r"\bcolombia\b", location or "", re.I):
        return 3
    if colombia_ok(location, text):
        return 2
    remote = re.search(r"\bremote\b", blob, re.I)
    if remote and not blocked:
        return 1
    return 0


def role_key(row):
    title = re.sub(r"\s+", " ", (row.get("title") or "").strip().lower())
    company = (row.get("company") or "").strip().lower()
    if not title and not company:
        return ("url", row.get("url") or "")
    return (company, title)


def select_rows(rows):
    def key(row):
        posted = row.get("posted") or EPOCH
        return (fit_rank(row.get("location"), row.get("text")), posted, row.get("url") or "")

    best = {}
    for row in rows:
        group = role_key(row)
        current = best.get(group)
        if current is None or key(row) > key(current):
            best[group] = row
    return sorted(best.values(), key=key, reverse=True)[:LIMIT]


def within_days(posted, now, days=DAYS):
    if posted is None or posted > now + timedelta(days=1):
        return False
    # Calendar days, so a job posted on the morning of day 7 still counts.
    return (now.date() - posted.astimezone(timezone.utc).date()).days <= days


def to_plain(raw):
    text = raw or ""
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        secs = float(value)
        if secs > 10_000_000_000:
            secs /= 1000.0
        return datetime.fromtimestamp(secs, timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# --- Boards ---

def get_json(url):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url):
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def jazzhr_fields(plain, page):
    posted = None
    dated = re.search(r'"datePosted"\s*:\s*"([^"]+)"', page)
    if dated:
        posted = parse_dt(dated.group(1))
    title = ""
    named = re.search(
        r'"@type"\s*:\s*"JobPosting".{0,500}?"title"\s*:\s*"([^"]+)"',
        page,
        re.S,
    )
    if named:
        title = html.unescape(named.group(1)).strip()
    located = re.search(
        r"Location\s*:?\s*(.+?)(?:\s+Work Arrangement|\s+Employment Type|\s+Industry|\s+Compensation|$)",
        plain,
        re.I,
    )
    location = located.group(1).strip(" ,.;") if located else ""
    compensated = re.search(
        r"Compensation\s*:?\s*(\$[0-9,]+(?:\s*[–—-]\s*\$?[0-9,]+)?(?:\s*USD(?:\s*/\s*month)?)?)",
        plain,
        re.I,
    )
    pay = pay_label(plain, compensated.group(1).strip() if compensated else "")
    return title, posted, location, pay


def jazzhr_jobs(board):
    slug = board["slug"]
    page = get_text(f"https://{slug}.applytojob.com/apply")
    found = set(re.findall(r"/apply/([A-Za-z0-9]+)/([A-Za-z0-9][^\"'#?<\s]*)", page))
    rows = []
    for job_id, title_slug in sorted(found):
        title = title_slug.replace("-", " ").strip()
        if not title_ok(title):
            continue
        url = f"https://{slug}.applytojob.com/apply/{job_id}/{title_slug}"
        rows.append({
            "title": title,
            "company": board["name"],
            "url": url,
            "posted": None,
            "location": "",
            "text": None,
            "pay": "unknown",
            "detail_url": url,
            "ats": "jazzhr",
        })
    return rows


def fill_jazzhr(row):
    if row["text"] is not None:
        return
    page = get_text(row["detail_url"])
    block = re.search(r'id="job-description"[^>]*>(.*?)</div>', page, re.S | re.I)
    plain = to_plain(block.group(1) if block else page)
    title, posted, location, pay = jazzhr_fields(plain, page)
    if title:
        row["title"] = title
    row["posted"] = posted
    row["location"] = location
    row["text"] = plain
    row["pay"] = pay


def greenhouse_jobs(board):
    slug = board["slug"]
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise RuntimeError("unexpected greenhouse payload")
    rows = []
    for job in data["jobs"]:
        url = str(job.get("absolute_url") or "").strip()
        if not url:
            continue
        rows.append({
            "title": str(job.get("title") or "").strip(),
            "company": str(job.get("company_name") or board["name"]).strip(),
            "url": url,
            "posted": parse_dt(job.get("first_published")),
            "location": str((job.get("location") or {}).get("name") or "").strip(),
            "text": None,
            "pay": "unknown",
            "detail_url": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job.get('id')}",
            "ats": "greenhouse",
        })
    return rows


def fill_greenhouse(row):
    if row["text"] is not None:
        return
    detail = get_json(row["detail_url"])
    if not isinstance(detail, dict):
        raise RuntimeError("unexpected greenhouse job payload")
    row["text"] = to_plain(detail.get("content") or "")
    row["pay"] = pay_label(row["text"], structured_pay(detail.get("metadata")))


def structured_pay(metadata):
    if not isinstance(metadata, list):
        return ""
    for item in metadata:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").lower()
        if "salary" in name or "compensation" in name or name == "pay":
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def lever_pay(salary):
    if not isinstance(salary, dict):
        return ""
    low, high = salary.get("min"), salary.get("max")
    if low is None and high is None:
        return ""
    currency = salary.get("currency") or ""
    interval = salary.get("interval") or ""
    return f"{currency} {low}-{high} {interval}".strip()


def lever_jobs(board):
    slug = board["slug"]
    rows = []
    seen_urls = set()
    skip = 0
    # ponytail: 1000-posting cap, raise it if a Lever board is larger than that
    while skip <= 1000:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json&skip={skip}&limit=100"
        data = get_json(url)
        if not isinstance(data, list):
            raise RuntimeError("unexpected lever payload")
        fresh = 0
        for job in data:
            hosted = str(job.get("hostedUrl") or "").strip()
            if not hosted or hosted in seen_urls:
                continue
            seen_urls.add(hosted)
            fresh += 1
            categories = job.get("categories") or {}
            text = to_plain(job.get("descriptionPlain") or job.get("description") or "")
            rows.append({
                "title": str(job.get("text") or "").strip(),
                "company": board["name"],
                "url": hosted,
                "posted": parse_dt(job.get("createdAt")),
                "location": str(categories.get("location") or "").strip(),
                "text": text,
                "pay": pay_label(text, lever_pay(job.get("salaryRange"))),
                "detail_url": "",
                "ats": "lever",
            })
        if fresh == 0 or len(data) < 100:
            break
        skip += 100
    return rows


def ashby_pay(comp):
    if not isinstance(comp, dict):
        return ""
    for key in ("compensationTierSummary", "scrapeableCompensationSalarySummary"):
        value = comp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def ashby_jobs(board):
    slug = board["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    data = get_json(url)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise RuntimeError("unexpected ashby payload")
    rows = []
    for job in data["jobs"]:
        if job.get("isListed") is False:
            continue
        hosted = str(job.get("jobUrl") or "").strip()
        if not hosted:
            continue
        text = to_plain(job.get("descriptionPlain") or job.get("descriptionHtml") or "")
        location = job.get("location")
        location = location.strip() if isinstance(location, str) else ""
        rows.append({
            "title": str(job.get("title") or "").strip(),
            "company": board["name"],
            "url": hosted,
            "posted": parse_dt(job.get("publishedAt")),
            "location": location,
            "text": text,
            "pay": pay_label(text, ashby_pay(job.get("compensation"))),
            "detail_url": "",
            "ats": "ashby",
        })
    return rows


def workable_location(location):
    if isinstance(location, str):
        return location.strip()
    if not isinstance(location, dict):
        return ""
    parts = [location.get("city"), location.get("countryName")]
    return ", ".join(str(part).strip() for part in parts if part)


def workable_jobs(board):
    rows = []
    seen = set()
    queries = (
        "marketing operations",
        "media operations",
        "ad operations",
        "campaign delivery",
        "marketing analytics",
        "paid media",
        "growth marketing",
        "media planning",
        "marketing workflow",
    )
    for query in queries:
        token = ""
        # ponytail: 3 pages per query, raise if a search is still paging
        for _ in range(3):
            params = {"query": query, "workplace": "remote", "day_range": "30"}
            if token:
                params["pageToken"] = token
            url = "https://jobs.workable.com/api/v1/jobs?" + urllib.parse.urlencode(params)
            data = get_json(url)
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise RuntimeError("unexpected workable payload")
            for job in data["jobs"]:
                title = str(job.get("title") or "").strip()
                link = str(job.get("url") or "").strip()
                if not title or not link or link in seen or not title_ok(title):
                    continue
                seen.add(link)
                company = job.get("company") or {}
                name = company.get("title") if isinstance(company, dict) else ""
                text = to_plain(job.get("description") or "")
                rows.append({
                    "title": title,
                    "company": str(name or board["name"]).strip(),
                    "url": link,
                    "posted": parse_dt(job.get("posted")),
                    "location": workable_location(job.get("location")),
                    "text": text,
                    "pay": pay_label(text),
                    "detail_url": "",
                    "ats": "workable",
                })
            token = str(data.get("nextPageToken") or "")
            if not token:
                break
    print(f"workable: {len(rows)}")
    return rows


def parse_rss_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return parse_dt(text)


def rss_text(item, tag):
    found = item.find(tag)
    return (found.text or "").strip() if found is not None else ""


def wwr_jobs(board):
    feeds = (
        "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
        "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    )
    rows = []
    seen = set()
    for feed in feeds:
        root = ET.fromstring(get_text(feed))
        for item in root.iter("item"):
            raw = rss_text(item, "title")
            link = rss_text(item, "link")
            if not raw or not link or link in seen:
                continue
            company, title = (raw.split(": ", 1) + [""])[:2] if ": " in raw else (board["name"], raw)
            title = title.strip() or raw
            if not title_ok(title):
                continue
            seen.add(link)
            text = to_plain(rss_text(item, "description"))
            rows.append({
                "title": title,
                "company": company.strip() or board["name"],
                "url": link,
                "posted": parse_rss_date(rss_text(item, "pubDate")),
                "location": rss_text(item, "region"),
                "text": text,
                "pay": pay_label(text),
                "detail_url": "",
                "ats": "wwr",
            })
    print(f"wwr: {len(rows)}")
    return rows


def remotive_jobs(board):
    rows = []
    seen = set()
    for term in ("marketing", "operations", "media"):
        data = get_json("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"search": term}))
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            raise RuntimeError("unexpected remotive payload")
        for job in jobs:
            title = str(job.get("title") or "").strip()
            link = str(job.get("url") or "").strip()
            if not title or not link or link in seen or not title_ok(title):
                continue
            seen.add(link)
            text = to_plain(job.get("description") or "")
            salary = job.get("salary")
            rows.append({
                "title": title,
                "company": str(job.get("company_name") or board["name"]).strip(),
                "url": link,
                "posted": parse_dt(job.get("publication_date")),
                "location": str(job.get("candidate_required_location") or "").strip(),
                "text": text,
                "pay": pay_label(text, salary if isinstance(salary, str) else ""),
                "detail_url": "",
                "ats": "remotive",
            })
    print(f"remotive: {len(rows)}")
    return rows


def fetch_board(board):
    ats = board["ats"]
    if ats == "greenhouse":
        return greenhouse_jobs(board)
    if ats == "lever":
        return lever_jobs(board)
    if ats == "ashby":
        return ashby_jobs(board)
    if ats == "jazzhr":
        return jazzhr_jobs(board)
    if ats == "workable":
        return workable_jobs(board)
    if ats == "wwr":
        return wwr_jobs(board)
    if ats == "remotive":
        return remotive_jobs(board)
    raise RuntimeError(f"unknown ats {ats}")


# --- Report ---

def load_json(path, kind):
    if not path.exists():
        if kind == "seen":
            return {}
        raise SystemExit(f"missing {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if kind == "seen":
        if not isinstance(data, dict):
            raise SystemExit(f"{path} is not an object")
        return data
    if not isinstance(data, list):
        raise SystemExit(f"{path} is not a list")
    return data


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def kept_blocks(text):
    blocks = []
    chunk = []
    for line in text.splitlines():
        if line.startswith("- "):
            if chunk:
                blocks.append("\n".join(chunk).rstrip())
            chunk = [line]
        elif chunk and line.strip():
            chunk.append(line)
        elif chunk and not line.strip():
            blocks.append("\n".join(chunk).rstrip())
            chunk = []
    if chunk:
        blocks.append("\n".join(chunk).rstrip())
    return blocks


def block_role_keys(blocks):
    keys = set()
    for block in blocks:
        first = block.splitlines()[0]
        match = re.search(r"\*\*(.+?)\*\*\s*\|\s*(.+)$", first)
        if not match:
            continue
        title = re.sub(r"\s+", " ", match.group(1).strip().lower())
        company = match.group(2).strip().lower()
        keys.add((company, title))
    return keys


def block_urls(blocks):
    urls = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("http"):
                urls.append(stripped)
    return urls


def write_report(rows, new_count, seen_count, kept=()):
    lines = [
        "# Job discovery",
        "",
        f"New: {new_count}",
        f"Shown: {len(kept) + len(rows)}",
        f"Seen: {seen_count}",
        "",
    ]
    if not kept and not rows:
        lines.append("No open title matches.")
        lines.append("")
    for block in kept:
        lines.append(block)
        lines.append("")
    for row in rows:
        flag = "contractor" if row["contractor"] else "not-contractor"
        mark = "NEW" if row["new"] else "already"
        posted = row["posted"].date().isoformat() if row["posted"] else "date unknown"
        lines.append(
            f"- {mark} | {flag} | {posted} | pay {pay_note(row['pay'])} | {row['ats']} | "
            f"**{row['title']}** | {row['company']}"
        )
        lines.append(f"  {row['location'] or 'location unknown'}")
        lines.append(f"  {row['url']}")
        lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def fill_some(jobs, fill):
    kept = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fill, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                future.result()
            except (urllib.error.URLError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError) as exc:
                print(f"skip {job['ats']} {job['url']}: {exc}", file=sys.stderr)
                continue
            kept.append(job)
    return kept


def match_rows(boards, exclude=(), exclude_keys=()):
    found = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_board, board): board for board in boards}
        for future in as_completed(futures):
            board = futures[future]
            label = f"{board['ats']}:{board['slug']}"
            try:
                jobs = future.result()
            except (urllib.error.URLError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError) as exc:
                print(f"skip {label}: {exc}", file=sys.stderr)
                continue
            for job in jobs:
                if title_ok(job["title"]) and job["url"]:
                    found.append(job)
    # JazzHR list rows have no location. Rank needs the job page.
    jazz = [job for job in found if job["ats"] == "jazzhr"]
    rest = [job for job in found if job["ats"] != "jazzhr"]
    rows = rest + fill_some(jazz, fill_jazzhr)
    deduped = []
    seen_urls = set()
    for row in rows:
        if row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        deduped.append(row)
    if exclude or exclude_keys:
        deduped = [
            row for row in deduped
            if row["url"] not in exclude and role_key(row) not in exclude_keys
        ]
    picked = select_rows(deduped)
    # Greenhouse list already has location and date. Body is only for the 10 shown.
    fill_some([job for job in picked if job["ats"] == "greenhouse"], fill_greenhouse)
    for job in picked:
        job["contractor"] = contractor_flag(job["location"], job["text"])
    return picked


def run():
    boards = load_json(BOARDS_PATH, "boards")
    seen = load_json(SEEN_PATH, "seen")
    previous = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
    kept = kept_blocks(previous)
    rows = match_rows(boards, set(block_urls(kept)), block_role_keys(kept))
    new_count = 0
    for row in rows:
        row["new"] = row["url"] not in seen
        if row["new"]:
            posted = row["posted"].date().isoformat() if row["posted"] else "unknown"
            seen[row["url"]] = posted
            new_count += 1
    write_json(SEEN_PATH, seen)
    write_report(rows, new_count, len(seen), kept)
    print(f"new: {new_count}")
    print(f"shown: {len(kept) + len(rows)}")
    print(f"seen: {len(seen)}")
    print(f"report: {REPORT_PATH}")


def check():
    targets = (
        "Head of Ad Operations",
        "Director of Ad Operations",
        "Regional AdTech & Operations Director",
        "Campaign Operations Director",
        "Head of Campaign Operations",
        "Media Operations Lead",
        "Global Media Operations Manager",
        "Ad Verification & QA Operations Manager",
        "Ad Trafficking & Analytics Director",
        "Marketing Operations Director",
        "Head of Marketing Operations",
        "Marketing Operations Manager (Enterprise / Digital Agency Accounts)",
        "Growth Operations Manager",
        "Director of Growth Operations",
        "MarTech Operations Manager",
        "Head of Campaign Delivery & Quality Assurance",
        "Regional Analytics Delivery Director",
        "Marketing Effectiveness Manager",
        "Marketing Effectiveness Director",
        "Measurement & Attribution Operations Lead",
        "Digital Analytics & Performance Director",
        "Marketing Reporting & Data Operations Manager",
        "Project Manager, Media Operations",
        "Marketing Operations Project Manager",
        "Senior MOps PM",
        "Senior Marketing Program Manager",
        "Digital Agency Delivery Manager",
        "Client Delivery Manager",
        "Campaign Delivery Manager",
        "Regional Campaign Lead",
        "Digital Production Manager",
        "Senior Paid Media Operations Manager",
        "Performance Marketing Operations Lead",
        "Marketing Data & Tracking Implementation Manager",
        "GA4 & Tracking Governance Manager",
        "E-Commerce Growth & Operations Manager",
        "AdOps Process & Campaign QA Auditor",
        "Agency Reporting & Measurement Workflow Consultant",
        "Campaign Trafficking & Tagging Governance Consultant",
        "Marketing Operations Workflow Automation Specialist",
        "Fractional Head of Media Operations",
        "CAC/LTV Analytics & Reporting Consultant",
        "Director Ad Ops",
        "MOps Lead",
        "Regional Analytics Manager",
        "Traffic Manager Advertising",
        "Media Implementation Manager",
        "Marketing Workflow & Process Optimization Manager",
        "Reporting & Insights Operations Lead",
        "Marketing BI & Data Governance Manager",
        "Conversion Rate Optimization (CRO) Operations Manager",
        "Growth Marketing Operations Manager",
        "Acquisition & Retention Operations Lead",
        "Full-Funnel Media Planning Manager",
        "Media Strategy & Operations Lead",
        "Media Buyer Operations",
        "Remote Marketing Infrastructure Consultant",
    )
    missed = [title for title in targets if not title_ok(title)]
    assert not missed, missed
    for title in (
        "Software Engineer",
        "Project Manager",
        "Marketing Manager",
        "Financial Reporting Manager",
        "Quality Assurance Engineer",
        "Operations Lead",
        "Associate, Growth Marketing",
        "Programmatic Operations Manager",
        "Staff Product Manager, Ads Measurement",
        "Senior Media Buyer",
        "Senior Paid Social Media Buyer",
        "Growth Marketing Manager",
        "Senior Growth Marketing Manager - Home Services",
        "Data Engineer",
    ):
        assert not title_ok(title), title

    assert colombia_ok("", "This is a contractor role and you can work from anywhere.")
    assert colombia_ok("", "Freelance consultant supporting LATAM and the Americas.")
    assert colombia_ok("", "Worldwide employment through an EOR.")
    assert colombia_ok("", to_plain("&lt;p&gt;contractor worldwide&lt;/p&gt;"))
    assert not colombia_ok("", "You must be authorized to work in the United States.")
    assert not colombia_ok("", "US citizen only. Security clearance required.")
    assert not colombia_ok("New York, NY (Hybrid)", "3 days a week in office")
    assert not colombia_ok("Remote", "Remote within the United States.")
    assert not colombia_ok("", "Work from anywhere. Must be a US citizen.")
    assert not colombia_ok("", "We mention theory and before.")

    assert contractor_flag("", "contractor role")
    assert not contractor_flag("", "worldwide team")

    assert pay_label("The salary range is $120,000 - $140,000") == "$120,000 - $140,000"
    assert pay_label("stipend $200 and salary $120,000") == "$120,000"
    assert pay_label("competitive pay") == "unknown"
    assert pay_label("", "USD 100-200 per-year-salary") == "USD 100-200 per-year-salary"

    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert within_days(now - timedelta(days=6), now)
    assert within_days(datetime(2026, 10, 19, 1, tzinfo=timezone.utc), now)
    assert not within_days(now - timedelta(days=8), now)
    assert not within_days(None, now)
    assert parse_dt(1787593981541).year == 2026
    assert parse_rss_date("Mon, 13 Oct 2026 12:00:00 +0000").date().isoformat() == "2026-10-13"

    page = '{"@type": "JobPosting", "title": "Project Manager, Media Operations", "datePosted": "2026-10-13"}'
    plain = (
        "Location : Remote – Colombia Work Arrangement: Fully Remote "
        "Employment Type: Independent Contractor "
        "Compensation: $2,167–$2,667 USD/month"
    )
    parsed_title, parsed_posted, parsed_location, parsed_pay = jazzhr_fields(plain, page)
    assert parsed_title == "Project Manager, Media Operations"
    assert parsed_posted.date().isoformat() == "2026-10-13"
    assert "Colombia" in parsed_location
    assert "2,167" in parsed_pay
    assert "below 3500" in pay_note(parsed_pay)
    assert "below 3500" not in pay_note("$120,000 - $140,000")
    assert pay_note("unknown") == "unknown"

    colombia = {
        "location": "Remote – Colombia",
        "text": "Employment Type: Independent Contractor. Fully Remote.",
        "posted": datetime(2026, 10, 13, tzinfo=timezone.utc),
        "url": "https://operatorequity.applytojob.com/apply/8HyCFctMzY/Project-Manager-Media-Operations",
    }
    office = {
        "location": "United States",
        "text": "On site in the office.",
        "posted": datetime(2026, 10, 21, tzinfo=timezone.utc),
        "url": "https://example.com/us",
    }
    chile = {
        "location": "Remote – Chile",
        "text": "Independent Contractor",
        "posted": datetime(2026, 10, 15, tzinfo=timezone.utc),
        "url": "https://example.com/cl",
    }
    assert not within_days(colombia["posted"], now)
    ranked = select_rows([office, chile, colombia])
    assert ranked[0]["url"] == colombia["url"]
    assert select_rows([colombia])[0]["posted"].date().isoformat() == "2026-10-13"
    clones = [
        {
            "title": "Project Manager, Marketing Operations (Senior)",
            "company": "Entrepreneur Cooperative",
            "location": loc,
            "text": "Independent Contractor. Open to Colombia, Mexico, or Chile.",
            "posted": datetime(2026, 10, 15, tzinfo=timezone.utc),
            "url": url,
        }
        for loc, url in (
            ("Remote – Mexico", "mx"),
            ("Remote – Chile", "cl2"),
            ("Remote – Colombia", "co"),
        )
    ]
    other = {
        "title": "Ad Operations Manager",
        "company": "Awin",
        "location": "São Paulo",
        "text": "office",
        "posted": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "url": "awin",
    }
    picked = select_rows(clones + [other])
    assert [row["url"] for row in picked] == ["co", "awin"]
    many = [
        {
            "location": "United States",
            "text": "office",
            "posted": datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "url": str(i),
        }
        for i in range(12)
    ]
    assert len(select_rows(many)) == LIMIT
    sample = "- already | x\n  Remote\n  https://example.com/a\n\n- NEW | y\n  https://example.com/b\n"
    assert block_urls(kept_blocks(sample)) == ["https://example.com/a", "https://example.com/b"]
    keyed = kept_blocks("- already | x | **Media Buyer Operations** | Acme\n  https://example.com/a\n")
    assert block_role_keys(keyed) == {("acme", "media buyer operations")}
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        run()
