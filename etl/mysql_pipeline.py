"""
mysql_pipeline.py  –  Full Screener + yfinance ETL Pipeline  (v3)
==================================================================
Changes vs v2:
  • New sections added:  price (pr), technical (ti),
                         macro (mc)
  • All yfinance-backed loaders now use the *_mysql variants
    (price_loader_mysql, technical_loader_mysql,
     macro_loader_mysql) which target
     mysql_schema_v2.sql with correct MySQL syntax & column sets.
  • DB_CONFIG passed explicitly into every loader (no global
    get_connection() relying on a SQLite path).
  • Schema alignment notes kept inline so mismatches are obvious.

Usage
-----
    python mysql_pipeline.py                          # interactive
    python mysql_pipeline.py HAL                      # single ticker
    python mysql_pipeline.py HAL TCS --sections bs pl # selective

Section codes:
    bs  = Balance Sheet
    pl  = Profit & Loss
    cf  = Cash Flow
    qr  = Quarterly Results
    sh  = Shareholding
    pr  = Price Daily          (yfinance)
    ti  = Technical Indicators (yfinance + pandas_ta/manual)
    mc  = Macro (indices/forex/RBI/indicators)
    ca  = Corporate Actions    (yfinance — dividends & splits)

Dependencies:
    pip install requests beautifulsoup4 mysql-connector-python
    pip install yfinance pandas pandas_ta   # for yfinance sections
"""

import sys
import os
# ── Path fixes ─────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))   # project root (for extract\, load\ packages)
sys.path.insert(0, _HERE)                         # etl\ itself  (for stocks_mysql.py)
import traceback
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup

# ── Shared scraper utilities ──────────────────────────────────────
from extract.balance_sheet_extractor import (
    clean_ticker_for_screener,
    get_screener_id_and_slug,
    parse_html_table,
)

# ── Screener loaders (pass db_config as first arg) ────────────────
from load.bs_loader import load_balance_sheet
from load.pl_loader import load_profit_loss
from load.cf_loader import load_cash_flow
from load.qr_loader import load_quarterly_results
from load.sh_loader import load_shareholding
from load.gm_loader import load_growth_metrics
from load.stocks_loader_mysql import load_stock_master
from extract.stocks_mysql import scrape_stock_master_details

# ── yfinance / MySQL loaders ──────────────────────────────────────
from load.price_loader_mysql     import load_price
from load.technical_loader_mysql import load_technicals
from load.technical_loader       import compute_technicals   # DB-agnostic
from load.macro_loader_mysql import (
    load_market_indices,
    load_forex_commodities,
    load_rbi_rates,
    load_macro_indicators,
)
from load.ca_loader import load_corporate_actions
from extract.my_corporate_actions import scrape_corporate_actions

# ─────────────────────────────────────────────────────────────────
# ❶  MySQL connection config — edit before running
# ─────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":       os.getenv("DB_HOST",     "localhost"),
    "port":       int(os.getenv("DB_PORT", "3306")),
    "database":   os.getenv("DB_NAME",     "ai_hedge_fund"),
    "user":       os.getenv("DB_USER",     "root"),
    "password":   os.getenv("DB_PASSWORD", ""),
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


def _get_with_retry(url, headers=None, retries=4, backoff=5):
    """
    GET with exponential backoff on 429 Too Many Requests.
    Waits backoff * 2^attempt seconds before each retry.
    """
    import time
    headers = headers or HEADERS
    for attempt in range(retries + 1):
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429:
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                print(f"  [WARN] 429 Too Many Requests — retrying in {wait}s … (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
        return resp
    return resp  # return last response after exhausting retries

ALL_SECTIONS    = ["sm", "bs", "pl", "cf", "qr", "sh", "gm", "pr", "ti", "mc", "ca"]
SCREENER_SECTIONS = ["sm", "bs", "pl", "cf", "qr", "sh", "gm"]

SECTION_LABELS = {
    "sm": "Stock Master",
    "bs": "Balance Sheet",
    "pl": "Profit & Loss",
    "cf": "Cash Flow",
    "qr": "Quarterly Results",
    "sh": "Shareholding",
    "gm": "Growth Metrics",
    "pr": "Price Daily",
    "ti": "Technical Indicators",
    "mc": "Macro",
    "ca": "Corporate Actions",
}


# ─────────────────────────────────────────────────────────────────
# ❷  Shared page resolver  (Screener sections only)
# ─────────────────────────────────────────────────────────────────

def _resolve(ticker: str):
    screener_id, slug = get_screener_id_and_slug(ticker)
    if not screener_id or not slug:
        return None, None, None, None

    is_consolidated = 1
    url  = f"https://www.screener.in/company/{slug}/consolidated/"
    resp = _get_with_retry(url)

    if resp.status_code == 404:
        url  = f"https://www.screener.in/company/{slug}/"
        resp = _get_with_retry(url)
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
    import urllib.parse
    encoded = urllib.parse.quote_plus(parent_name)
    url = (
        f"https://www.screener.in/api/company/{screener_id}/schedules/"
        f"?parent={encoded}&section={section}&consolidated="
    )
    try:
        res  = _get_with_retry(url)
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
# ❹  Per-section extractors — Screener
# ─────────────────────────────────────────────────────────────────

def extract_stock_master(ticker):
    """
    Scrape master metadata for a stock: screener_id, sector hierarchy,
    market_cap_cr.  Uses stocks_mysql.scrape_stock_master_details().
    """
    print(f"\n  ▶ Extracting Stock Master …")
    try:
        data = scrape_stock_master_details(ticker)
        if not data:
            print(f"  ⚠  stock_master: no data returned for {ticker}")
            return None
        # Carry raw_ticker so the loader can infer exchange from suffix
        data["_raw_ticker"] = ticker
        return data
    except Exception as e:
        print(f"  [ERROR] extract_stock_master: {e}")
        return None


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
        [
            "Borrowings", "Other Liabilities", "Other Assets", "Fixed Assets",
            # Inventories, Trade Receivables, Loans & Advances have no parent
            # columns; stored entirely via balance_sheet_items.
            "Inventories", "Trade Receivables", "Loans & Advances",
        ],
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
        ["Expenses", "Other Income"],
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
    return dict(symbol=symbol, dates=dates, shareholding_rows=rows)


def extract_growth_metrics(ticker):
    print(f"\n  ▶ Extracting Growth Metrics …")
    symbol = clean_ticker_for_screener(ticker)
    try:
        from extract.growth_metrcis import scrape_growth_metrics
        metrics = scrape_growth_metrics(ticker)
        if not metrics:
            print(f"  ⚠  growth_metrics: no data returned for {ticker}")
            return None
        return dict(symbol=symbol, metrics=metrics)
    except Exception as e:
        print(f"  [ERROR] extract_growth_metrics: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# ❺  Per-section extractors — yfinance
# ─────────────────────────────────────────────────────────────────

def _resolve_yf_symbol(ticker: str) -> str:
    """
    Resolve a ticker string to a live Yahoo Finance symbol.

    Strategy (in order):
      1. If the caller already supplied an exchange suffix (e.g. 'HDFCBANK.NS',
         'RELIANCE.BO'), trust it and return as-is.
      2. Try  TICKER.NS  directly — if yfinance returns price data, use it.
      3. Fall back to Yahoo Finance's search API
         (query1.finance.yahoo.com/v1/finance/search) to find the correct
         current symbol.  Picks the first NSE (.NS) equity result; if none,
         picks the first BSE (.BO) equity result.
      4. If everything fails, return TICKER.NS and let the caller handle
         the empty-data case gracefully.

    This handles mergers / delistings / renames automatically — no static map
    needed regardless of how many tickers you run.
    """
    import yfinance as yf

    raw = ticker.upper().strip()

    # Strip exchange suffix to get the base symbol for searching.
    # e.g. 'HDFC.NS' -> base='HDFC', 'RELIANCE.BO' -> base='RELIANCE'
    if "." in raw:
        base = raw.rsplit(".", 1)[0]
        suffix_provided = True
    else:
        base = raw
        suffix_provided = False

    # ── Step 1: validate the supplied symbol is actually live ─────────────
    # Even if the user passed 'HDFC.NS', we must verify it has price data.
    # HDFC Ltd merged into HDFC Bank in 2023 — HDFC.NS is now dead.
    if suffix_provided:
        try:
            hist = yf.Ticker(raw).history(period="5d", auto_adjust=False)
            if not hist.empty:
                return raw          # suffix provided AND data exists — done
            print(f"  [YF] '{raw}' returned no price data — searching for live symbol …")
        except Exception:
            print(f"  [YF] '{raw}' lookup failed — searching for live symbol …")

    # ── Step 2: try BASE.NS directly (for no-suffix callers) ─────────────
    if not suffix_provided:
        candidate = base + ".NS"
        try:
            hist = yf.Ticker(candidate).history(period="5d", auto_adjust=False)
            if not hist.empty:
                return candidate
        except Exception:
            pass

    # ── Step 3: Yahoo Finance search API — handles mergers / renames ──────
    try:
        search_url = (
            "https://query1.finance.yahoo.com/v1/finance/search"
            f"?q={base}&lang=en-US&region=IN&quotesCount=10&newsCount=0"
        )
        resp = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])

        # Prefer NSE equity, then BSE equity
        ns_hits = [q["symbol"] for q in quotes
                   if q.get("quoteType") == "EQUITY" and q.get("symbol", "").endswith(".NS")]
        bo_hits = [q["symbol"] for q in quotes
                   if q.get("quoteType") == "EQUITY" and q.get("symbol", "").endswith(".BO")]

        resolved = (ns_hits or bo_hits or [None])[0]
        if resolved:
            print(f"  [YF] '{raw}' resolved via search → {resolved}")
            return resolved
    except Exception as e:
        print(f"  [YF] Search API failed for '{raw}': {e}")

    # ── Step 4: best-effort fallback ──────────────────────────────────────
    fallback = base + ".NS"
    print(f"  [YF] Could not resolve '{raw}'; falling back to {fallback}")
    return fallback


def _yf_ticker(ticker: str):
    """
    Return a yfinance Ticker object for the given ticker.
    Automatically resolves the correct current Yahoo Finance symbol
    (handles mergers, delistings, renames) via _resolve_yf_symbol().
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance not installed — run: pip install yfinance")
    sym = _resolve_yf_symbol(ticker)
    return yf.Ticker(sym)


def extract_price(ticker):
    """
    Fetch 5 years of daily OHLCV from yfinance.
    Returns dict with keys: symbol, df
    df columns: date, open, high, low, close, adj_close, volume
    """
    print(f"\n  ▶ Extracting Price Daily …")
    symbol = clean_ticker_for_screener(ticker)
    try:
        yt = _yf_ticker(ticker)
        hist = yt.history(period="5y", auto_adjust=False)
        if hist.empty:
            print(f"  ⚠  price_daily: yfinance returned no data for {ticker}")
            return None
        hist = hist.reset_index()
        # Normalise column names to lowercase
        hist.columns = [c.lower() for c in hist.columns]
        # yfinance returns 'adj close' (with space)
        if "adj close" in hist.columns:
            hist.rename(columns={"adj close": "adj_close"}, inplace=True)
        if "date" not in hist.columns and "datetime" in hist.columns:
            hist.rename(columns={"datetime": "date"}, inplace=True)
        hist["date"] = hist["date"].astype(str).str[:10]
        print(f"  ✔  price_daily: {len(hist)} rows fetched for {symbol}")
        return dict(symbol=symbol, df=hist)
    except Exception as e:
        print(f"  [ERROR] extract_price: {e}")
        return None


def extract_technicals(ticker):
    """
    Re-uses extract_price to get OHLCV, then runs compute_technicals().
    Returns dict with keys: symbol, df  (output of compute_technicals)
    """
    print(f"\n  ▶ Extracting Technical Indicators …")
    price_result = extract_price(ticker)
    if price_result is None:
        return None
    df_tech = compute_technicals(price_result["df"])
    if df_tech.empty:
        print(f"  ⚠  technical_indicators: compute returned empty df")
        return None
    return dict(symbol=price_result["symbol"], df=df_tech)


def extract_macro(_ticker):
    """
    Macro is not ticker-specific.
    Calls the macro extractor from your existing extract module.
    Returns dict with keys: indices_data, forex_data, rbi_data,
                             indicators_list, snapshot_date
    """
    print(f"\n  ▶ Extracting Macro data …")
    snap_date = date.today().isoformat()
    try:
        from extract.macro_mysql import (
            get_market_indices,
            get_forex_commodities,
            get_rbi_rates,
            get_macro_indicators,
        )
        indices_data    = {"indices": get_market_indices()}
        forex_data      = {"forex":   get_forex_commodities()}
        rbi_data        = get_rbi_rates()
        indicators_list = get_macro_indicators(snap_date)
        return dict(
            indices_data    = indices_data,
            forex_data      = forex_data,
            rbi_data        = rbi_data,
            indicators_list = indicators_list,
            snapshot_date   = snap_date,
        )
    except Exception as e:
        print(f"  [ERROR] extract_macro: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# ❻  Section dispatch maps
# ─────────────────────────────────────────────────────────────────

SECTION_EXTRACT = {
    "sm": extract_stock_master,
    "bs": extract_balance_sheet,
    "pl": extract_profit_loss,
    "cf": extract_cash_flow,
    "qr": extract_quarterly_results,
    "sh": extract_shareholding,
    "gm": extract_growth_metrics,
    "pr": extract_price,
    "ti": extract_technicals,
    "mc": extract_macro,
    "ca": scrape_corporate_actions,
}


def _load_result(section: str, result: dict):
    """Route result dict to the correct MySQL loader."""

    # ── Screener sections ────────────────────────────────────────
    if section == "sm":
        load_stock_master(
            DB_CONFIG,
            result,
            raw_ticker=result.get("_raw_ticker"),
        )
    elif section == "bs":
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

    elif section == "gm":
        load_growth_metrics(
            DB_CONFIG, result["symbol"], result["metrics"],
        )

    # ── yfinance / MySQL sections ────────────────────────────────
    elif section == "pr":
        load_price(DB_CONFIG, result["df"], result["symbol"])

    elif section == "ti":
        load_technicals(DB_CONFIG, result["df"], result["symbol"])

    elif section == "mc":
        sd = result["snapshot_date"]
        # Each macro sub-loader runs independently so one failure does not
        # abort the others.  load_rbi_rates has a known KeyError: 0 bug in
        # macro_loader_mysql.py (line ~136: `last[0]` on a dict row —
        # fix: change `last[0]` → `last["repo_rate"]` in that file).
        for fn, args in [
            (load_market_indices,   (DB_CONFIG, result["indices_data"],    sd)),
            (load_forex_commodities,(DB_CONFIG, result["forex_data"],       sd)),
            (load_rbi_rates,        (DB_CONFIG, result["rbi_data"],           )),
            (load_macro_indicators, (DB_CONFIG, result["indicators_list"],    )),
        ]:
            try:
                fn(*args)
            except KeyError as e:
                print(f"  [MACRO] ✗ {fn.__name__} failed — KeyError {e}")
                print(f"          Fix in macro_loader_mysql.py: change `last[0]`"
                      f" → `last['repo_rate']` (or use integer index with cursor"
                      f" dictionary=False)")
            except Exception as e:
                print(f"  [MACRO] ✗ {fn.__name__} failed — {e}")

    elif section == "ca":
        load_corporate_actions(DB_CONFIG, result["symbol"], result["actions"])


# ─────────────────────────────────────────────────────────────────
# ❼  Per-ticker pipeline runner
# ─────────────────────────────────────────────────────────────────

def _check_mysql_connection() -> bool:
    """
    Attempt a lightweight MySQL connection using DB_CONFIG.
    Returns True if successful, False otherwise (with a clear error message).
    Prevents the pipeline from attempting to load every section only to fail
    with the same connection-refused error each time.
    """
    try:
        import mysql.connector
        conn = mysql.connector.connect(**DB_CONFIG)
        conn.close()
        return True
    except Exception as e:
        print(f"\n  [PIPELINE] ✗ Cannot connect to MySQL — load phase will be skipped.")
        print(f"             {e}")
        print(f"\n  Fix: make sure MySQL is running on {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        print(f"       Windows:  net start MySQL80   (run as Administrator)")
        print(f"       Then ensure the database exists:")
        print(f"         CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} CHARACTER SET utf8mb4;\n")
        return False


def run_pipeline(ticker: str, sections: list):
    start  = datetime.now()
    symbol = clean_ticker_for_screener(ticker)

    print(f"\n{'═'*60}")
    print(f"  PIPELINE  ·  {symbol}")
    print(f"  Sections : {[SECTION_LABELS[s] for s in sections]}")
    print(f"{'═'*60}")

    # ── Pre-flight MySQL check: fail fast instead of repeating the error ──
    mysql_ok = _check_mysql_connection()
    if not mysql_ok:
        print(f"  [PIPELINE] Extraction will still run; loading will be skipped.\n")

    success, failed = [], []

    for sec in sections:
        label = SECTION_LABELS[sec]
        try:
            result = SECTION_EXTRACT[sec](ticker)

            if result is None:
                print(f"\n  [PIPELINE] ✗ Extraction failed — {label}")
                failed.append(sec)
                continue

            if not mysql_ok:
                print(f"\n  [PIPELINE] ⚠  Skipping load for {label} (MySQL unavailable)")
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

    # Return structured result so callers (e.g. pipeline_service) can inspect
    # which sections succeeded / failed without parsing stdout.
    return {"success": success, "failed": failed}


# ─────────────────────────────────────────────────────────────────
# ❽  CLI entry point
# ─────────────────────────────────────────────────────────────────

def parse_args():
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

    if not tickers:
        raw     = input("Enter ticker symbol(s) separated by spaces: ").strip()
        tickers = [t.strip() for t in raw.split() if t.strip()]

    if not tickers:
        print("[ERROR] No tickers provided. Exiting.")
        sys.exit(1)

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