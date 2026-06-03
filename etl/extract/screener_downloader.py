import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.screener.in"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Keywords for annual-report classification (concalls use dedicated parser).
ANNUAL_KW = [
    "annual report",
    "financial year",
    "fy",
    "integrated report",
    "annual accounts",
]

CONCALL_KW = [
    "transcript",
    "earnings call",
    "concall",
    "con call",
    "conference call",
    "analyst meet",
    "q&a",
]

_MONTH_YEAR_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})\b",
    re.I,
)


# ─────────────────────────────────────────────
# Fetch page
# ─────────────────────────────────────────────
def fetch_page(session, symbol):
    for path in [f"/company/{symbol}/consolidated/", f"/company/{symbol}/"]:
        url = BASE_URL + path
        print(f"  -> GET {url}")
        r = session.get(url, timeout=30)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "lxml"), url
    raise SystemExit("Failed to fetch company page")


# ─────────────────────────────────────────────
# Extract year
# ─────────────────────────────────────────────
def extract_year(text):
    t = text.lower()

    m = re.search(r"q[1-4][\s\-]*fy[\s\-]*(\d{2,4})", t)
    if m:
        yr = int(m.group(1))
        return 2000 + yr if yr < 100 else yr

    m = re.search(r"\bfy[\s\-]*(\d{2,4})", t)
    if m:
        yr = int(m.group(1))
        return 2000 + yr if yr < 100 else yr

    m = re.search(r"(20\d{2})[–\-/](\d{2,4})", t)
    if m:
        return int(m.group(1)) + 1

    m = re.search(r"(20\d{2})", t)
    if m:
        return int(m.group(1))

    return None


def extract_year_from_period(period: str) -> int | None:
    """Parse fiscal year from Screener concall row label, e.g. 'Apr 2026'."""
    m = _MONTH_YEAR_RE.search(period)
    if m:
        return int(m.group(2))
    return extract_year(period)


# ─────────────────────────────────────────────
# Classification (annual reports only)
# ─────────────────────────────────────────────
def classify_doc(title, url):
    text = (title + " " + url).lower()

    if any(k in text for k in CONCALL_KW):
        if "board meeting" not in text:
            return "concall"

    if any(k in text for k in ANNUAL_KW):
        return "annual_report"

    return "other"


def _normalize_url(href: str, page_url: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    if href.startswith("/"):
        href = urljoin(BASE_URL, href)
    if not href.startswith("http"):
        return None
    return href


def _period_from_concall_row(li) -> str:
    label = li.find("div", class_=lambda c: c and "ink-600" in c)
    if label:
        return label.get_text(" ", strip=True)
    text = li.get_text(" ", strip=True)
    for token in ("Transcript", "AI Summary", "PPT", "REC"):
        if token in text:
            text = text.split(token, 1)[0].strip()
    return text


def _is_transcript_anchor(tag) -> bool:
    if tag.name != "a" or not tag.get("href"):
        return False
    label = tag.get_text(strip=True)
    if label == "Transcript":
        return True
    return tag.get("title", "").strip().lower() == "raw transcript"


def resolve_pdf_url(url: str, session: requests.Session | None = None) -> str | None:
    """
    Return a direct PDF URL when possible.

    Handles TCS investor-relations overlay links (#type=overlay&page=...)
    by fetching the overlay HTML and locating embedded PDF anchors.
    """
    if not url:
        return None

    lowered = url.lower()
    if "#type=overlay" in lowered:
        parsed = urlparse(url)
        page = None
        for part in parsed.fragment.split("&"):
            if part.startswith("page="):
                page = unquote(part[5:])
                break
        if not page:
            return None

        base = f"{parsed.scheme}://{parsed.netloc}"
        overlay_url = urljoin(base + "/", page.lstrip("/"))
        sess = session or requests.Session()
        try:
            resp = sess.get(
                overlay_url,
                timeout=30,
                headers={
                    **HEADERS,
                    "Referer": base + "/",
                },
            )
            if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "").lower():
                return None
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = _normalize_url(a["href"], overlay_url)
                if href and ".pdf" in href.lower():
                    return href
        except Exception:
            return None
        return None

    if ".pdf" in lowered or "bseindia.com" in lowered or "nseindia.com" in lowered:
        return url

    return url


def extract_concalls(soup) -> list[dict]:
    """
    Parse the Screener 'Concalls' subsection.

    Each row lists period (e.g. Apr 2026) and a Transcript anchor when available.
    Placeholder <div class="concall-link">Transcript</div> rows have no PDF yet.
    """
    section = soup.find(id="documents")
    if not section:
        return []

    concalls_div = section.find(class_="concalls")
    if not concalls_div:
        return []

    docs: list[dict] = []
    seen_urls: set[str] = set()

    for li in concalls_div.find_all("li", recursive=True):
        period = _period_from_concall_row(li)
        if not period:
            continue

        transcript_url = None
        for a in li.find_all("a", href=True):
            if _is_transcript_anchor(a):
                transcript_url = _normalize_url(a["href"], BASE_URL)
                break

        if not transcript_url:
            continue

        transcript_url = resolve_pdf_url(transcript_url)
        if not transcript_url:
            continue

        norm = transcript_url.rstrip("/").lower()
        if norm in seen_urls:
            continue
        seen_urls.add(norm)

        title = f"{period} Transcript"
        year = extract_year_from_period(period) or extract_year(transcript_url)

        docs.append({
            "title": title,
            "url": transcript_url,
            "year": year,
            "doc_type": "concall",
        })

    return docs


def extract_annual_reports(soup, page_url: str) -> list[dict]:
    """Annual reports from #documents, excluding the concalls subsection."""
    section = soup.find(id="documents")
    if not section:
        return []

    concalls_div = section.find(class_="concalls")

    docs = []
    seen = set()

    for a in section.find_all("a", href=True):
        if concalls_div and a in concalls_div.find_all("a", href=True):
            continue

        href = _normalize_url(a["href"], page_url)
        if not href:
            continue

        title = a.get_text(" ", strip=True)
        full_text = f"{title} {href}"
        year = extract_year(full_text)
        doc_type = classify_doc(title, href)

        if doc_type != "annual_report":
            continue

        key = href.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)

        docs.append({
            "title": title or "document",
            "url": href,
            "year": year,
            "doc_type": doc_type,
        })

    return docs


# ─────────────────────────────────────────────
# Extract documents (annual + concalls)
# ─────────────────────────────────────────────
def extract_documents(soup, page_url):
    annual = extract_annual_reports(soup, page_url)
    concalls = extract_concalls(soup)
    return annual + concalls


# ─────────────────────────────────────────────
# Download (ROBUST)
# ─────────────────────────────────────────────
def safe_name(s):
    return re.sub(r"[^\w\-_. ]", "_", s)[:100]


def download_pdf(session, doc, out_root):
    url = resolve_pdf_url(doc["url"], session) or doc["url"]
    year = str(doc["year"] or "unknown")
    dtype = doc["doc_type"]
    title = safe_name(doc["title"])

    dest = out_root / dtype / year
    dest.mkdir(parents=True, exist_ok=True)

    fpath = dest / f"{year}_{title}.pdf"

    print(f"[↓] {dtype} {year} {title}")

    try:
        headers = session.headers.copy()

        if "bseindia.com" in url:
            headers["Referer"] = "https://www.bseindia.com/"
        elif "nseindia.com" in url:
            headers["Referer"] = "https://www.nseindia.com/"
        elif "tcs.com" in url:
            headers["Referer"] = "https://www.tcs.com/investor-relations/financial-statements"

        r = session.get(url, timeout=60, stream=True, headers=headers)
        r.raise_for_status()

        content_type = r.headers.get("Content-Type", "")
        if "html" in content_type.lower():
            print("    skipped (HTML page)")
            return False

        with open(fpath, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)

        size_kb = fpath.stat().st_size // 1024

        if size_kb < 10:
            fpath.unlink(missing_ok=True)
            print("    skipped (too small)")
            return False

        print(f"    saved ({size_kb} KB)")
        return True

    except Exception as e:
        print(f"    failed: {e}")
        return False


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    symbol = args.symbol.upper()

    session = requests.Session()
    session.headers.update(HEADERS)

    print("\n[1] Fetching page")
    soup, page_url = fetch_page(session, symbol)

    print("[2] Extracting documents")
    docs = extract_documents(soup, page_url)

    annual = [d for d in docs if d["doc_type"] == "annual_report"]
    concall = [d for d in docs if d["doc_type"] == "concall"]
    print(f"Clean docs found: {len(docs)} ({len(annual)} annual, {len(concall)} concall)\n")

    for d in docs:
        print(f"{d['doc_type']} | {d['year']} | {d['title']}")

    if args.dry_run:
        return

    out_dir = Path("./screener_docs") / symbol

    print("\n[3] Downloading...\n")

    success = 0
    fail = 0

    for doc in docs:
        if download_pdf(session, doc, out_dir):
            success += 1
        else:
            fail += 1
        time.sleep(1.5)

    print("\n==============================")
    print(f"Downloaded: {success}")
    print(f"Failed: {fail}")
    print("==============================\n")


if __name__ == "__main__":
    main()
