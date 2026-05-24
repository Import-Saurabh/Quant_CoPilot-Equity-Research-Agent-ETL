"""
mysql_pipeline.py  –  Balance Sheet ETL Pipeline
==================================================
Entry point. Takes ticker input from the user, calls the scraper,
prints the fetched data, then calls the loader to insert into MySQL.

Usage:
    python mysql_pipeline.py                   # prompts interactively
    python mysql_pipeline.py HAL ADANIPORTS    # pass tickers as CLI args

Dependencies:  pip install requests beautifulsoup4 mysql-connector-python
"""

import sys
import traceback
from datetime import datetime

# ── Local modules ────────────────────────────────────────────
# scraper lives in balance_sheet_extractor.py (the file you provided,
# renamed for clarity)
from extract.balance_sheet_extractor import (
    clean_ticker_for_screener,
    get_screener_id_and_slug,
    parse_html_table,
    fetch_schedule_item,
)
from bs4 import BeautifulSoup
import requests

from load.bs_loader import load_balance_sheet

# ─────────────────────────────────────────────────────────────
# ❶  MySQL connection config  –  edit before running
# ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "database": "ai_hedge_fund",
    "user":     "root",          # ← change
    "password": "your_password", # ← change
    "charset":  "utf8mb4",
    "autocommit": False,
}

# Schedule parents to fetch child breakdowns for
SCHEDULE_PARENTS = [
    "Borrowings",
    "Other Liabilities",
    "Other Assets",
    "Fixed Assets",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


# ─────────────────────────────────────────────────────────────
# ❷  Extraction  (wraps the scraper into structured dicts)
# ─────────────────────────────────────────────────────────────
def extract_balance_sheet(ticker: str) -> dict | None:
    """
    Returns a result dict:
    {
        "symbol":         str,
        "is_consolidated":int,
        "dates":          list[str],
        "main_rows":      dict,        # {label: [val, …]}
        "child_items":    dict,        # {parent_label: {child_label: [val, …]}}
    }
    or None on failure.
    """
    print(f"\n{'═'*60}")
    print(f"  PIPELINE  ·  Extracting: {ticker}")
    print(f"{'═'*60}")

    screener_id, slug = get_screener_id_and_slug(ticker)
    if not screener_id or not slug:
        print(f"[ABORT] Could not resolve Screener identity for '{ticker}'.")
        return None

    clean_symbol = clean_ticker_for_screener(ticker)
    print(f"[INFO]  Screener ID: {screener_id}  |  Slug: {slug}")

    # ── Fetch main page ──────────────────────────────────────
    is_consolidated = 1
    company_url = f"https://www.screener.in/company/{slug}/consolidated/"
    response    = requests.get(company_url, headers=HEADERS)

    if response.status_code == 404:
        company_url = f"https://www.screener.in/company/{slug}/"
        response    = requests.get(company_url, headers=HEADERS)
        is_consolidated = 0

    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code} for {company_url}")
        return None

    soup       = BeautifulSoup(response.content, "html.parser")
    bs_section = soup.find("section", id="balance-sheet")

    if not bs_section:
        print("[ERROR] Balance Sheet section not found on the page.")
        return None

    table = bs_section.find("table")
    dates, main_rows = parse_html_table(table)

    # ── Print fetched parent rows ────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  FETCHED DATA  ·  {clean_symbol}  ({'Consolidated' if is_consolidated else 'Standalone'})")
    print(f"{'─'*60}")
    print(f"  Periods  : {dates}")
    print(f"  {'Label':<30}  Values")
    print(f"  {'─'*28}  {'─'*30}")
    for label, values in main_rows.items():
        print(f"  {label:<30}  {values}")

    # ── Fetch child schedule breakdowns ─────────────────────
    print(f"\n  Child Schedule Breakdowns:")
    child_items: dict = {}

    for parent in SCHEDULE_PARENTS:
        rows = fetch_schedule_item(screener_id, parent)
        if rows:
            child_items[parent] = rows
            print(f"\n  [{parent}]")
            for child_label, vals in rows.items():
                padded = (vals + [None] * len(dates))[:len(dates)]
                print(f"    ↳ {child_label:<35} {padded}")
        else:
            print(f"\n  [{parent}]  — no breakdown available on Screener")

    return {
        "symbol":          clean_symbol,
        "is_consolidated": is_consolidated,
        "dates":           dates,
        "main_rows":       main_rows,
        "child_items":     child_items,
    }


# ─────────────────────────────────────────────────────────────
# ❸  Pipeline: extract → load
# ─────────────────────────────────────────────────────────────
def run_pipeline(ticker: str):
    start = datetime.now()

    # Step 1: Extract
    result = extract_balance_sheet(ticker)
    if result is None:
        print(f"[PIPELINE] ✗ Extraction failed for '{ticker}'. Skipping load.\n")
        return

    # Step 2: Load into MySQL
    print(f"\n[PIPELINE] Loading '{result['symbol']}' into MySQL …")
    try:
        load_balance_sheet(
            db_config      = DB_CONFIG,
            symbol         = result["symbol"],
            dates          = result["dates"],
            main_rows      = result["main_rows"],
            child_items    = result["child_items"],
            is_consolidated= result["is_consolidated"],
        )
    except Exception as exc:
        print(f"[PIPELINE] ✗ Load failed for '{ticker}':")
        traceback.print_exc()
        return

    elapsed = (datetime.now() - start).total_seconds()
    print(f"[PIPELINE] ✓ Done — {result['symbol']}  ({elapsed:.1f}s)\n")


# ─────────────────────────────────────────────────────────────
# ❹  Entry point
# ─────────────────────────────────────────────────────────────
def main():
    # Accept tickers from CLI args OR interactive prompt
    if len(sys.argv) > 1:
        tickers = [t.strip() for t in sys.argv[1:] if t.strip()]
    else:
        raw = input("Enter ticker symbol(s) separated by spaces: ").strip()
        tickers = [t.strip() for t in raw.split() if t.strip()]

    if not tickers:
        print("[ERROR] No tickers provided. Exiting.")
        sys.exit(1)

    print(f"\n[PIPELINE] Starting run for {len(tickers)} ticker(s): {tickers}")
    print(f"[PIPELINE] Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    for ticker in tickers:
        try:
            run_pipeline(ticker)
        except KeyboardInterrupt:
            print("\n[PIPELINE] Interrupted by user.")
            break
        except Exception:
            print(f"[PIPELINE] Unexpected error for '{ticker}':")
            traceback.print_exc()

    print("[PIPELINE] All tickers processed.")


if __name__ == "__main__":
    main()