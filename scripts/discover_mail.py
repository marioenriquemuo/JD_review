#!/usr/bin/env python3
"""Scan mail-drop JSON files. Append title-matching jobs (title or nearby description) to discovery files."""

import html.parser
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from discover_jobs import (
    REPORT_PATH,
    SEEN_PATH,
    block_role_keys,
    block_urls,
    contractor_flag,
    kept_blocks,
    load_json,
    title_ok,
    to_plain,
    write_json,
    write_report,
)

# Real postings only — not /jobs/alerts, search pages, or bare /jobs/ paths.
JOB_HOST_RE = re.compile(
    r"("
    r"(?:boards\.)?greenhouse\.io/[^/]+/jobs/\d+"
    r"|jobs\.lever\.co/[^/]+/[0-9a-f-]+"
    r"|jobs\.ashbyhq\.com/[^/]+/[0-9a-f-]+"
    r"|jobs\.workable\.com/view/"
    r"|applytojob\.com/apply/"
    r"|weworkremotely\.com/remote-jobs/"
    r")",
    re.I,
)
# Job id lives in the query, so the query must be kept.
QUERY_ID_RE = re.compile(r"glassdoor\.[a-z.]+/partner/jobListing\.htm", re.I)
LINKEDIN_ID_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.I)
JUNK_URL_RE = re.compile(
    r"(linkedin\.com/(?:comm/)?jobs/(?:alerts|search|collections)\b"
    r"|unsubscribe|opt-?out|emailsettings|/privacy|preferences)",
    re.I,
)
# Link labels that are buttons, not job titles.
NAV_RE = re.compile(
    r"^(?:ver empleo|ver oferta|view jobs?|apply(?: now)?|easy apply|aplicar(?: ahora)?|postular(?:me)?"
    r"|see (?:more|all) jobs|search for more jobs\.?|more jobs|i'?m interested|browse vacancies now.*"
    r"|jobs similar to)$",
    re.I,
)
VIEW_JOB_RE = re.compile(
    r"^(?:ver empleo|ver oferta|view job|apply(?: now)?|aplicar(?: ahora)?|postular(?:me)?)$",
    re.I,
)
RATING_RE = re.compile(r"^\d(?:\.\d)?\s*★$")
NOISE_RE = re.compile(
    r"^(?:\d(?:\.\d)?\s*★|\d+\s*[hdwm]|just posted|easy apply|actively recruiting|promoted)$",
    re.I,
)
DOT_RE = re.compile(r"^(.+?)\s+·\s+(.+)$")
WORK_MODE = r"\((?:remote|hybrid|on-site|remoto|h[íi]brido|presencial)\)"
SUBJECT_AT_RE = re.compile(
    r"^(.+?)\s+(?:at|en)\s+(.+?)(?:\s+and\s+\d+\s+more\b.*)?$",
    re.I,
)
LOC_RE = re.compile(
    r"\b(colombia|bogot[aá]|remote|remoto|worldwide|anywhere|latam)\b",
    re.I,
)
ZW_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]+")


def clean_title(text):
    cleaned = ZW_RE.sub("", text or "")
    # The report is pipe-delimited.
    cleaned = re.sub(r"\s*\|\s*", " / ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rsplit(" ", 1)[0].strip()
    return cleaned


# --- HTML ---

class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._parts = []
        self._alts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href = attrs["href"].strip()
            self._parts = []
            self._alts = []
        elif tag == "img" and self._href is not None and attrs.get("alt"):
            self._alts.append(attrs["alt"])

    def handle_data(self, data):
        if self._href is not None and data.strip():
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, self._parts, self._alts))
            self._href = None


def parse_links(raw_html):
    parser = LinkParser()
    try:
        parser.feed(raw_html or "")
        parser.close()
    except Exception:
        return []
    links = []
    for href, parts, alts in parser.links:
        parts = [clean_title(part) for part in parts]
        alts = [clean_title(alt) for alt in alts]
        links.append((href, [part for part in parts if part], [alt for alt in alts if alt]))
    return links


# --- URLs ---

def canon_url(url):
    original = str(url or "").strip()
    raw = unquote(original)
    if not raw:
        return ""
    match = LINKEDIN_ID_RE.search(raw)
    if match:
        return "https://www.linkedin.com/jobs/view/" + match.group(1)
    path_id = bool(JOB_HOST_RE.search(raw))
    try:
        parsed = urlparse(raw if path_id else original)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    if path_id:
        parsed = parsed._replace(query="")
    return parsed._replace(fragment="").geturl().rstrip("/")


def is_job_url(url):
    text = url or ""
    if JUNK_URL_RE.search(text):
        return False
    if LINKEDIN_ID_RE.search(text):
        return True
    return bool(JOB_HOST_RE.search(text) or QUERY_ID_RE.search(text))


def job_key(url):
    """Stable id for one job, or None when the link is a per-email tracker."""
    text = url or ""
    match = LINKEDIN_ID_RE.search(text)
    if match:
        return "linkedin:" + match.group(1)
    if QUERY_ID_RE.search(text):
        try:
            ids = parse_qs(urlparse(text).query).get("jobListingId")
        except ValueError:
            ids = None
        return "glassdoor:" + ids[0] if ids else text
    if JOB_HOST_RE.search(text):
        return text
    return None


def host(url):
    return urlparse(url).netloc.lower()


# --- Listings ---

def parse_posted(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def guess_location(blob):
    match = LOC_RE.search(blob or "")
    if not match:
        return ""
    word = match.group(1)
    if word.lower().startswith("bogot"):
        return "Bogotá"
    if word.lower() in ("remote", "remoto"):
        return "Remote"
    return word[:1].upper() + word[1:]


def company_from_subject(subject, title):
    # Subject company only belongs to the job the subject names, not to a digest's other jobs.
    match = SUBJECT_AT_RE.match(subject or "")
    if match and clean_title(match.group(1)).lower() == (title or "").lower():
        return clean_title(match.group(2))
    return ""


def title_from_subject(subject):
    match = SUBJECT_AT_RE.match(subject or "")
    if match:
        return clean_title(match.group(1))
    return subject if title_ok(subject) else ""


def apply_url_at(index, anchors):
    _href, url, _parts, _alts = anchors[index]
    if index + 1 >= len(anchors):
        return url
    _next_href, next_url, next_parts, _next_alts = anchors[index + 1]
    if VIEW_JOB_RE.match(" ".join(next_parts)) and host(next_url) == host(url):
        return next_url
    return url


def is_listing(index, anchors):
    href, url, parts, _alts = anchors[index]
    if is_job_url(href) and is_job_url(url):
        return True
    text = " ".join(parts)
    if not text or NAV_RE.match(text):
        return False
    if title_ok(text):
        return True
    # Tracker links: a title link followed by its "Ver Empleo" / "View job" button.
    return apply_url_at(index, anchors) != url


def card_desc(title, plain):
    if not title or not plain:
        return ""
    i = plain.lower().find(title.lower())
    if i < 0:
        return ""
    after = plain[i + len(title): i + len(title) + 700]
    after = re.split(
        r"\b(?:ver empleo|ver oferta|view jobs?|apply now|aplicar ahora)\b",
        after,
        maxsplit=1,
        flags=re.I,
    )[0]
    return re.sub(r"\s+", " ", (title + " " + after)).strip()


def aligned(title, desc):
    return title_ok(title) or title_ok(desc) or title_ok("%s %s" % (title, desc))


def listing_fields(url, parts, alts, subject, plain):
    parts = [part for part in parts if not NAV_RE.match(part)]
    if QUERY_ID_RE.search(url) and len(parts) >= 2:
        # Glassdoor: company, [rating], title, location, ...
        index = 2 if len(parts) > 2 and RATING_RE.match(parts[1]) else 1
        if index >= len(parts):
            return "", parts[0], ""
        rest = [part for part in parts[index + 1:] if not NOISE_RE.match(part) and "$" not in part]
        return parts[index], parts[0], rest[0] if rest else ""

    company = alts[0] if alts else ""
    location = ""
    titles = []
    for part in parts:
        if NOISE_RE.match(part):
            continue
        dot = DOT_RE.match(part)
        if dot:
            company = company or dot.group(1)
            location = dot.group(2)
            continue
        titles.append(part)
    lowered = [part.lower() for part in titles]
    if "at" in lowered:
        cut = lowered.index("at")
        title = " ".join(titles[:cut])
        company = " ".join(titles[cut + 1:]) or company
    else:
        title = next((part for part in titles if part.lower() != company.lower()), "")
    if title and company and not location:
        # LinkedIn prints "Company · City (Hybrid)" after each title; prefer the line after this title.
        place = re.escape(company) + r"\s+·\s+([^·]{2,60}?" + WORK_MODE + ")"
        match = (re.search(re.escape(title) + r"\s+" + place, plain, re.I)
                 or re.search(place, plain, re.I))
        location = match.group(1).strip() if match else ""
    if title and not company:
        company = company_from_subject(subject, title)
    return title, company, location


def listings_from(msg):
    subject = clean_title(str(msg.get("subject") or ""))
    raw_html = str(msg.get("html") or "")
    plain = to_plain(raw_html)
    blob = subject + "\n" + plain
    posted = parse_posted(msg.get("date"))

    anchors = []
    for href, parts, alts in parse_links(raw_html):
        url = canon_url(href)
        if url and not JUNK_URL_RE.search(href):
            anchors.append((href, url, parts, alts))
    if not anchors:
        # plain-text mail: bare job URLs only
        for match in re.finditer(r"https?://[^\s\"'<>]+", plain):
            raw = match.group(0).rstrip(").,;")
            url = canon_url(raw)
            if url and is_job_url(raw) and is_job_url(url):
                anchors.append((raw, url, [], []))

    groups = {}
    for index, (_href, url, parts, alts) in enumerate(anchors):
        if not is_listing(index, anchors):
            continue
        apply_url = apply_url_at(index, anchors)
        group = groups.setdefault(job_key(apply_url) or apply_url, {"url": apply_url, "parts": [], "alts": []})
        group["parts"].extend(parts)
        group["alts"].extend(alts)

    rows = []
    for group in groups.values():
        title, company, location = listing_fields(
            group["url"], group["parts"], group["alts"], subject, plain
        )
        if not title and len(groups) == 1:
            title = title_from_subject(subject)
            company = company or company_from_subject(subject, title)
        desc = card_desc(title, plain)
        if not title or not aligned(title, desc):
            continue
        location = location or guess_location(blob)
        rows.append({
            "title": title,
            "company": company or "unknown",
            "location": location,
            "url": group["url"],
            "ats": "email",
            "pay": "unknown",
            "posted": posted,
            "text": blob[:2000],
            "contractor": contractor_flag(location, blob),
            "new": True,
        })
    return rows


# --- Discovery files ---

def append_rows(rows):
    if not rows:
        return 0
    previous = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else ""
    kept = kept_blocks(previous)
    seen = load_json(SEEN_PATH, "seen") if SEEN_PATH.exists() else {}
    keys = {job_key(url) or url for url in list(block_urls(kept)) + list(seen)}
    roles = block_role_keys(kept)
    fresh = []
    for row in rows:
        key = job_key(row["url"])
        role = (row["company"].lower(), row["title"].lower())
        # Tracker links change every email, so title + company is their only stable identity.
        if (key or row["url"]) in keys or (key is None and role in roles):
            continue
        keys.add(key or row["url"])
        roles.add(role)
        fresh.append(row)
        seen[row["url"]] = row["posted"].date().isoformat() if row["posted"] else "unknown"
    if not fresh:
        return 0
    new_marks = sum(1 for block in kept if block.splitlines()[0].startswith("- NEW |"))
    write_report(fresh, new_marks + len(fresh), len(seen), kept)
    write_json(SEEN_PATH, seen)
    return len(fresh)


def emit(msg_id, box, mark, added):
    print(json.dumps({"id": msg_id, "box": box, "mark": mark, "added": added}, ensure_ascii=False))


# --- Run ---

def run_dir(folder):
    path = Path(folder)
    files = sorted(path.glob("*.json")) if path.is_dir() else []
    for file_path in files:
        msg_id, box = "", path.name
        try:
            msg = json.loads(file_path.read_text(encoding="utf-8"))
            msg_id = str(msg.get("id") or "")
            box = str(msg.get("box") or path.name)
            listings = listings_from(msg)
        except Exception as exc:
            # One bad email must not stop the batch; it stays unread for the next run.
            print("skip %s: %s: %s" % (file_path.name, type(exc).__name__, exc), file=sys.stderr)
            listings = []
        added = append_rows(listings)
        if msg_id:
            emit(msg_id, box, bool(listings), added)
        try:
            file_path.unlink()
        except OSError:
            pass


def check():
    def mail(subject, html, box="gmail", sender="jobs-noreply@linkedin.com"):
        return {"id": "x", "box": box, "date": "2026-10-28T12:00:00Z",
                "subject": subject, "from": sender, "html": html}

    eng = listings_from(mail(
        "Head of Performance Marketing at AvantStay",
        '<p><a href="https://www.linkedin.com/jobs/view/4483854812">'
        "Head of Performance Marketing</a> Colombia</p>",
    ))
    assert [(r["title"], r["company"], r["url"]) for r in eng] == [(
        "Head of Performance Marketing", "AvantStay", "https://www.linkedin.com/jobs/view/4483854812",
    )], eng

    promo = mail("Spoil yourself with Black",
                 "<p>Upgrade to Uber One. <a href='https://uber.com/x'>Open app</a></p>",
                 sender="uber@uber.com")
    assert listings_from(promo) == []

    # single job link with a button label: title + company from the subject
    fallback = listings_from(mail(
        "Marketing Operations Partner - Remote Work at BairesDev",
        '<p>Apply now <a href="https://www.linkedin.com/jobs/view/4483699049">view job</a></p>',
    ))
    assert [(r["title"], r["company"]) for r in fallback] == [
        ("Marketing Operations Partner - Remote Work", "BairesDev")], fallback

    # LinkedIn digest: logo + title share one job id; keep only titles that align
    digest = listings_from(mail(
        "Jobs that may be a fit",
        "<a href='https://www.linkedin.com/comm/jobs/view/5?trk=a'><img alt='Cirion Technologies'></a>"
        "<a href='https://www.linkedin.com/comm/jobs/view/5?trk=b'>"
        "Digital Analytics Manager</a>"
        "<p>Cirion Technologies · Bogota, D.C. (Hybrid)</p>"
        "<a href='https://www.linkedin.com/comm/jobs/view/6'><img alt='Omnicom Media Colombia'></a>"
        "<a href='https://www.linkedin.com/comm/jobs/view/6'>"
        "Account Manager</a>"
        "<p>Omnicom Media Colombia · Bogota, D.C. (Hybrid)</p>"
        "<a href='https://www.linkedin.com/comm/jobs/alerts'>Manage alert</a>"
        "<a href='https://www.linkedin.com/comm/jobs/search'>See all jobs</a>",
    ))
    assert [(r["title"], r["company"], r["location"], r["url"]) for r in digest] == [
        ("Digital Analytics Manager", "Cirion Technologies",
         "Bogota, D.C. (Hybrid)", "https://www.linkedin.com/jobs/view/5"),
    ], digest

    # header link whose title does not align stays out
    similar = listings_from(mail(
        "New jobs similar to Account Manager",
        "<a href='https://www.linkedin.com/comm/jobs/view/7'><span>Jobs similar to</span>"
        "<span>Account Manager - E-commerce Marketing Agency</span><span>at</span>"
        "<span>Hustler Marketing</span></a>",
    ))
    assert similar == [], similar

    # subject company only for the job the subject names
    named = listings_from(mail(
        "Head of Performance Marketing at AvantStay",
        "<a href='https://www.linkedin.com/comm/jobs/view/1'>Head of Performance Marketing</a>"
        "<a href='https://www.linkedin.com/comm/jobs/view/2'>Marketing Operations Partner</a>",
    ))
    assert {r["url"]: r["company"] for r in named} == {
        "https://www.linkedin.com/jobs/view/1": "AvantStay",
        "https://www.linkedin.com/jobs/view/2": "unknown",
    }, named

    # Glassdoor: company, [rating], title, location, ...; job id is jobListingId
    glassdoor = listings_from(mail(
        "Sezzle, Visa Inc. and others are hiring in Bogota",
        "<a href='https://www.glassdoor.com/partner/jobListing.htm?pos=101&guid=a&jobListingId=11'>"
        "<span>adidas</span><span>3.9 ★</span><span>Marketing Operations Manager</span>"
        "<span>Bogota</span><span>2d</span></a>"
        "<a href='https://www.glassdoor.com/partner/jobListing.htm?pos=102&guid=a&jobListingId=12'>"
        "<span>Thirteenth</span><span>Brand Campaign Team II</span><span>Remote</span>"
        "<span>$85K - $105K (Employer est.)</span><span>Easy Apply</span></a>"
        "<a href='https://www.glassdoor.com/Job/bogota-jobs-SRCH_IL.0,6.htm'>See more jobs</a>",
        sender='"Glassdoor Jobs" <noreply@glassdoor.com>',
    ))
    assert [(r["title"], r["company"], r["location"]) for r in glassdoor] == [
        ("Marketing Operations Manager", "adidas", "Bogota"),
    ], glassdoor
    assert job_key("https://www.glassdoor.com/partner/jobListing.htm?pos=1&guid=a&jobListingId=11") == (
        job_key("https://www.glassdoor.com/partner/jobListing.htm?pos=9&guid=b&jobListingId=11"))

    # tracker links (Michael Page): title link followed by "Ver Empleo"
    tracker = listings_from(mail(
        "Vacantes nuevas para:  Information Technology : Colombia",
        "<a href='https://click.em.page.com/?qs=AAA'>Desarrollador Fullstack</a>"
        "<a href='https://click.em.page.com/?qs=BBB'>Ver Empleo</a>"
        "<a href='https://click.em.page.com/?qs=CCC'>Coordinador de Data y Analítica</a>"
        "<a href='https://click.em.page.com/?qs=DDD'>Ver Empleo</a>"
        "<a href='https://click.em.page.com/unsubscribe?qs=EEE'>Marketing Operations</a>"
        "<a href='https://click.em.page.com/?qs=FFF'>Leer más</a>",
        box="outlook", sender="noreply@mail.michaelpage.com.co",
    ))
    assert [(r["title"], r["company"], r["url"]) for r in tracker] == [
        ("Coordinador de Data y Analítica", "unknown", "https://click.em.page.com/?qs=DDD"),
    ], tracker

    # description (not the title) aligns → keep the apply link
    desc_mail = listings_from(mail(
        "Vacantes nuevas",
        "<a href='https://click.em.page.com/?qs=111'>Service Delivery Manager</a>"
        "<p>Como Coordinador de Data y Analítica, lideras dashboards y analítica digital.</p>"
        "<a href='https://click.em.page.com/?qs=222'>Ver Empleo</a>",
        box="outlook", sender="noreply@mail.michaelpage.com.co",
    ))
    assert [(r["title"], r["url"]) for r in desc_mail] == [
        ("Service Delivery Manager", "https://click.em.page.com/?qs=222"),
    ], desc_mail

    # malformed href must not crash the scan
    assert canon_url("http://[tracking_link]/x") == ""
    assert listings_from(dict(promo, html="<a href='http://[tracking_link]/x'>Marketing Operations</a>")) == []

    assert canon_url("https://www.linkedin.com/jobs/view/1?refId=abc") == "https://www.linkedin.com/jobs/view/1"
    assert canon_url("https://www.linkedin.com/comm/jobs/view/4483854812") == (
        "https://www.linkedin.com/jobs/view/4483854812")
    glassdoor_url = "https://www.glassdoor.com/partner/jobListing.htm?pos=101&guid=abc"
    assert is_job_url(glassdoor_url) and canon_url(glassdoor_url) == glassdoor_url
    assert not is_job_url("https://www.linkedin.com/comm/jobs/alerts")
    assert job_key("https://click.em.page.com/?qs=AAA") is None
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    elif "--dir" in sys.argv:
        idx = sys.argv.index("--dir")
        if idx + 1 >= len(sys.argv):
            sys.exit("usage: discover_mail.py --dir <path>")
        run_dir(sys.argv[idx + 1])
    else:
        sys.exit("usage: discover_mail.py --dir <path> | --check")
