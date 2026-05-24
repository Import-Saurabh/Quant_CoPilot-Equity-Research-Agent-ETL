"""
mysql_pipeline.py  –  Full Screener ETL Pipeline  (v2)
========================================================
Orchestrates extraction + loading for ALL financial sections:
  • Balance Sheet       (bs_loader)
  • Profit & Loss       (pl_loader)
  • Cash Flow           (cf_loader)
  • Quarterly Results   (qr_loader)
  • Shareholding        (sh_loader)

Usage
-----
    python mysql_pipeline.py                        # interactive prompt
    python mysql_pipeline.py HAL                    # single ticker
    python mysql_pipeline.py HAL ADANIPORTS.BO TCS  # multiple tickers
    python mysql_pipeline.py HAL --sections bs pl   # selective sections

Sections shorthand:
    bs  = Balance Sheet
    pl  = Profit & Loss
    cf  = Cash Flow
    qr  = Quarterly Results
    sh  = Shareholding

File layout expected in the same directory:
    balance_sheet_extractor.py   ← original BS scraper (renamed)
    cash_flow_mysql.py           ← cash flow scraper
    pL_mysql.py                  ← P&L scraper
    quarterly_result_mysql.py    ← quarterly results scraper
    shareholding_mysql.py        ← shareholding scraper
    bs_loader.py
    cf_loader.py
    pl_loader.py
    qr_loader.py
    sh_loader.py

Dependencies:  pip install requests beautifulsoup4 mysql-connector-python
"""

import sys
import traceback
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Shared scraper utilities (from the balance sheet extractor) ──
from extract.balance_sheet_extractor import (
    clean_ticker_for_screener,
    get_screener_id_and_slug,
    parse_html_table,
)

# ── Loaders ──────────────────────────────────────────────────────
from load.bs_loader import load_balance_sheet
from load.pl_loader import load_profit_loss
from load.cf_loader import load_cash_flow
from load.qr_loader import load_quarterly_results
from load.sh_loader import load_shareholding

# ─────────────────────────────────────────────────────────────────
# ❶  MySQL connection config  –  edit before running
# ─────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":       "localhost",
    "port":       3306,
    "database":   "ai_hedge_fund",
    "user":       "root",           # ← change
    "password":   "Avinash18",  # ← change
    "charset":    "utf8mb4",
    "autocommit": False,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

ALL_SECTIONS = ["bs", "pl", "cf", "qr", "sh"]

SECTION_LABELS = {
    "bs": "Balance Sheet",
    "pl": "Profit & Loss",
    "cf": "Cash Flow",
    "qr": "Quarterly Results",
    "sh": "Shareholding",
}


# ─────────────────────────────────────────────────────────────────
# ❷  Shared page resolver
# ─────────────────────────────────────────────────────────────────

def _resolve(ticker: str):
    """
    Returns (screener_id, slug, is_consolidated, soup) or
            (None, None, None, None) on failure.
    """
    screener_id, slug = get_screener_id_and_slug(ticker)
    if not screener_id or not slug:
        return None, None, None, None

    is_consolidated = 1
    url  = f"https://www.screener.in/company/{slug}/consolidated/"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code == 404:
        url  = f"https://www.screener.in/company/{slug}/"
        resp = requests.get(url, headers=HEADERS)
        is_consolidated = 0

    if resp.status_code != 200:
        print(f"  [ERROR] HTTP {resp.status_code} fetching {url}")
        return None, None, None, None

    soup = BeautifulSoup(resp.content, "html.parser")
    return screener_id, slug, is_consolidated, soup


def _section_table(soup, section_id, ticker):
    section = soup.find("section", id=section_id)
    if not section:
        print(f"  [ERROR] Section '#{section_id}' not found for {ticker}")
        return None, None
    table = section.find("table")
    if not table:
        print(f"  [ERROR] No table inside '#{section_id}' for {ticker}")
        return None, None
    return parse_html_table(table)


def _fetch_schedule(screener_id, parent_name, section):
    """Call the Screener schedules API for any section."""
    import urllib.parse
    encoded = urllib.parse.quote_plus(parent_name)
    url = (
        f"https://www.screener.in/api/company/{screener_id}/schedules/"
        f"?parent={encoded}&section={section}&consolidated="
    )
    try:
        res  = requests.get(url, headers=HEADERS)
        res.raise_for_status()
        data = res.json()

        if isinstance(data, dict) and "html" in data:
            html = data.get("html", "")
            if not html.strip():
                return {}
            soup = BeautifulSoup(f"<table>{html}</table>", "html.parser")
            _, rows = parse_html_table(soup)
            return rows
        elif isinstance(data, dict):
            result = {}
            for k, v in data.items():
                result[k.strip()] = [v[kk] for kk in sorted(v.keys())]
            return result
        return {}
    except Exception as e:
        print(f"  [WARN] Schedule fetch failed '{parent_name}': {e}")
        return {}


def _collect_children(screener_id, parents, section):
    child_items = {}
    for parent in parents:
        rows = _fetch_schedule(screener_id, parent, section)
        if rows:
            child_items[parent] = rows
        else:
            print(f"  [INFO] No child breakdown for '{parent}' in {section}")
    return child_items


# ─────────────────────────────────────────────────────────────────
# ❸  Print helpers
# ─────────────────────────────────────────────────────────────────

def _print_fetched(section_name, symbol, is_consolidated, dates, main_rows):
    variant = "Consolidated" if is_consolidated else "Standalone"
    print(f"\n  {'─'*56}")
    print(f"  FETCHED  ·  {section_name}  ·  {symbol}  ({variant})")
    print(f"  {'─'*56}")
    print(f"  Periods  : {dates}")
    print(f"  {'Label':<35}  Values")
    print(f"  {'─'*33}  {'─'*20}")
    for label, values in main_rows.items():
        print(f"  {label:<35}  {values}")


def _print_children(child_items, dates):
    if not child_items:
        return
    print(f"\n  Child Breakdowns:")
    for parent_label, rows in child_items.items():
        print(f"\n  [{parent_label}]")
        for child_label, vals in rows.items():
            padded = (vals + [None] * len(dates))[:len(dates)]
            print(f"    ↳ {child_label:<38} {padded}")


# ─────────────────────────────────────────────────────────────────
# ❹  Per-section extractors  (return structured dicts for loaders)
# ─────────────────────────────────────────────────────────────────

def extract_balance_sheet(ticker):
    print(f"\n  ▶ Extracting Balance Sheet …")
    screener_id, slug, is_consolidated, soup = _resolve(ticker)
    if soup is None:
        return None

    dates, main_rows = _section_table(soup, "balance-sheet", ticker)
    if dates is None:
        return None

    symbol = clean_ticker_for_screener(ticker)
    _print_fetched("Balance Sheet", symbol, is_consolidated, dates, main_rows)

    child_items = _collect_children(
        screener_id,
        ["Borrowings", "Other Liabilities", "Other Assets", "Fixed Assets"],
        "balance-sheet",
    )
    _print_children(child_items, dates)

    return dict(symbol=symbol, is_consolidated=is_consolidated,
                dates=dates, main_rows=main_rows, child_items=child_items)


def extract_profit_loss(ticker):
    print(f"\n  ▶ Extracting Profit & Loss …")
    screener_id, slug, is_consolidated, soup = _resolve(ticker)
    if soup is None:
        return None

    dates, main_rows = _section_table(soup, "profit-loss", ticker)
    if dates is None:
        return None

    symbol = clean_ticker_for_screener(ticker)
    _print_fetched("Profit & Loss", symbol, is_consolidated, dates, main_rows)

    child_items = _collect_children(
        screener_id,
        ["Expenses", "Other Income", "Net Profit"],
        "profit-loss",
    )
    _print_children(child_items, dates)

    return dict(symbol=symbol, is_consolidated=is_consolidated,
                dates=dates, main_rows=main_rows, child_items=child_items)


def extract_cash_flow(ticker):
    print(f"\n  ▶ Extracting Cash Flow …")
    screener_id, slug, is_consolidated, soup = _resolve(ticker)
    if soup is None:
        return None

    dates, main_rows = _section_table(soup, "cash-flow", ticker)
    if dates is None:
        return None

    symbol = clean_ticker_for_screener(ticker)
    _print_fetched("Cash Flow", symbol, is_consolidated, dates, main_rows)

    child_items = _collect_children(
        screener_id,
        [
            "Cash from Operating Activity",
            "Cash from Investing Activity",
            "Cash from Financing Activity",
        ],
        "cash-flow",
    )
    _print_children(child_items, dates)

    return dict(symbol=symbol, is_consolidated=is_consolidated,
                dates=dates, main_rows=main_rows, child_items=child_items)


def extract_quarterly_results(ticker):
    print(f"\n  ▶ Extracting Quarterly Results …")
    screener_id, slug, is_consolidated, soup = _resolve(ticker)
    if soup is None:
        return None

    dates, main_rows = _section_table(soup, "quarters", ticker)
    if dates is None:
        return None

    # Drop Raw PDF row — not financial data
    main_rows = {k: v for k, v in main_rows.items() if "Raw PDF" not in k}

    symbol = clean_ticker_for_screener(ticker)
    _print_fetched("Quarterly Results", symbol, is_consolidated, dates, main_rows)

    child_items = _collect_children(
        screener_id,
        ["Expenses", "Other Income", "Net Profit"],
        "quarters",
    )
    _print_children(child_items, dates)

    return dict(symbol=symbol, is_consolidated=is_consolidated,
                dates=dates, main_rows=main_rows, child_items=child_items)


def extract_shareholding(ticker):
    print(f"\n  ▶ Extracting Shareholding Pattern …")
    screener_id, slug, is_consolidated, soup = _resolve(ticker)
    if soup is None:
        return None

    dates, rows = _section_table(soup, "shareholding", ticker)
    if dates is None:
        return None

    symbol = clean_ticker_for_screener(ticker)
    print(f"\n  {'─'*56}")
    print(f"  FETCHED  ·  Shareholding  ·  {symbol}")
    print(f"  {'─'*56}")
    print(f"  Periods  : {dates}")
    for label, values in rows.items():
        print(f"  {label:<35} {values}")

    # No child schedules for shareholding
    return dict(symbol=symbol, dates=dates, shareholding_rows=rows)


# ─────────────────────────────────────────────────────────────────
# ❺  Section dispatch maps
# ─────────────────────────────────────────────────────────────────

SECTION_EXTRACT = {
    "bs": extract_balance_sheet,
    "pl": extract_profit_loss,
    "cf": extract_cash_flow,
    "qr": extract_quarterly_results,
    "sh": extract_shareholding,
}


def _load_result(section: str, result: dict):
    """Route result dict to the correct loader."""
    if section == "bs":
        load_balance_sheet(
            DB_CONFIG, result["symbol"], result["dates"],
            result["main_rows"], result["child_items"], result["is_consolidated"],
        )
    elif section == "pl":
        load_profit_loss(
            DB_CONFIG, result["symbol"], result["dates"],
            result["main_rows"], result["child_items"], result["is_consolidated"],
        )
    elif section == "cf":
        load_cash_flow(
            DB_CONFIG, result["symbol"], result["dates"],
            result["main_rows"], result["child_items"], result["is_consolidated"],
        )
    elif section == "qr":
        load_quarterly_results(
            DB_CONFIG, result["symbol"], result["dates"],
            result["main_rows"], result["child_items"], result["is_consolidated"],
        )
    elif section == "sh":
        load_shareholding(
            DB_CONFIG, result["symbol"], result["dates"],
            result["shareholding_rows"],
        )


# ─────────────────────────────────────────────────────────────────
# ❻  Per-ticker pipeline runner
# ─────────────────────────────────────────────────────────────────

def run_pipeline(ticker: str, sections: list):
    start  = datetime.now()
    symbol = clean_ticker_for_screener(ticker)

    print(f"\n{'═'*60}")
    print(f"  PIPELINE  ·  {symbol}")
    print(f"  Sections : {[SECTION_LABELS[s] for s in sections]}")
    print(f"{'═'*60}")

    success, failed = [], []

    for sec in sections:
        label = SECTION_LABELS[sec]
        try:
            result = SECTION_EXTRACT[sec](ticker)

            if result is None:
                print(f"\n  [PIPELINE] ✗ Extraction failed — {label}")
                failed.append(sec)
                continue

            print(f"\n  [PIPELINE] Loading {label} into MySQL …")
            _load_result(sec, result)
            success.append(sec)

        except KeyboardInterrupt:
            raise
        except Exception:
            print(f"\n  [PIPELINE] ✗ Error in section '{label}':")
            traceback.print_exc()
            failed.append(sec)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'─'*60}")
    print(f"  SUMMARY  ·  {symbol}  ({elapsed:.1f}s)")
    print(f"  ✓ OK    : {[SECTION_LABELS[s] for s in success]}")
    if failed:
        print(f"  ✗ FAILED: {[SECTION_LABELS[s] for s in failed]}")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────
# ❼  CLI entry point
# ─────────────────────────────────────────────────────────────────

def parse_args():
    """
    Split sys.argv into tickers and optional --sections flag.
    Example:
        python mysql_pipeline.py HAL TCS --sections bs pl cf
    """
    args     = sys.argv[1:]
    sections = ALL_SECTIONS
    tickers  = []

    if "--sections" in args:
        idx      = args.index("--sections")
        raw_secs = [s.lower() for s in args[idx + 1:]]
        sections = [s for s in raw_secs if s in ALL_SECTIONS]
        args     = args[:idx]
        if not sections:
            print(f"[ERROR] No valid section codes after --sections.")
            print(f"        Valid codes: {ALL_SECTIONS}")
            sys.exit(1)

    tickers = [a for a in args if not a.startswith("--")]
    return tickers, sections


def main():
    tickers, sections = parse_args()

    # Interactive ticker input if none given via CLI
    if not tickers:
        raw     = input("Enter ticker symbol(s) separated by spaces: ").strip()
        tickers = [t.strip() for t in raw.split() if t.strip()]

    if not tickers:
        print("[ERROR] No tickers provided. Exiting.")
        sys.exit(1)

    # Interactive section selection if none given via CLI
    if sections == ALL_SECTIONS:
        raw_sec = input(
            f"Sections to run {ALL_SECTIONS} "
            f"(space-separated codes, or Enter for ALL): "
        ).strip()
        if raw_sec:
            chosen = [s.lower() for s in raw_sec.split() if s.lower() in ALL_SECTIONS]
            if chosen:
                sections = chosen

    print(f"\n[PIPELINE] Tickers   : {tickers}")
    print(f"[PIPELINE] Sections  : {[SECTION_LABELS[s] for s in sections]}")
    print(f"[PIPELINE] Timestamp : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for ticker in tickers:
        try:
            run_pipeline(ticker, sections)
        except KeyboardInterrupt:
            print("\n[PIPELINE] Interrupted by user.")
            break
        except Exception:
            print(f"[PIPELINE] Unexpected error for '{ticker}':")
            traceback.print_exc()

    print("[PIPELINE] All done.")


if __name__ == "__main__":
    main()