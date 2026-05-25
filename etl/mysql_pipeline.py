"""
mysql_pipeline.py    Full Screener + yfinance ETL Pipeline  (v3)
==================================================================
Changes vs v2:
  • New sections added:  price (pr), technical (ti),
                         earnings history/estimates (eh/ee),
                         eps trend / revisions (et/er),
                         macro (mc)
  • All yfinance-backed loaders now use the *_mysql variants
    (price_loader_mysql, technical_loader_mysql,
     earnings_loader_mysql, macro_loader_mysql) which target
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
    eh  = Earnings History     (yfinance)
    ee  = Earnings Estimates   (yfinance)
    et  = EPS Trend            (yfinance)
    er  = EPS Revisions        (yfinance)
    mc  = Macro (indices/forex/RBI/indicators)

Dependencies:
    pip install requests beautifulsoup4 mysql-connector-python
    pip install yfinance pandas pandas_ta   # for yfinance sections
"""

import sys
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

# ── yfinance / MySQL loaders ──────────────────────────────────────
from load.price_loader_mysql     import load_price
from load.technical_loader_mysql import load_technicals
from load.technical_loader       import compute_technicals   # DB-agnostic
from load.earnings_loader_mysql  import (
    load_earnings_history,
    load_earnings_estimates,
    load_eps_trend,
    load_eps_revisions,
)
from load.macro_loader_mysql import (
    load_market_indices,
    load_forex_commodities,
    load_rbi_rates,
    load_macro_indicators,
)

# ─────────────────────────────────────────────────────────────────
# ❶  MySQL connection config — edit before running
# ─────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":       "localhost",
    "port":       3306,
    "database":   "ai_hedge_fund",
    "user":       "root",           # ← change
    "password":   "Avinash18",      # ← change
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

ALL_SECTIONS    = ["bs", "pl", "cf", "qr", "sh", "pr", "ti", "eh", "ee", "et", "er", "mc"]
SCREENER_SECTIONS = ["bs", "pl", "cf", "qr", "sh"]

SECTION_LABELS = {
    "bs": "Balance Sheet",
    "pl": "Profit & Loss",
    "cf": "Cash Flow",
    "qr": "Quarterly Results",
    "sh": "Shareholding",
    "pr": "Price Daily",
    "ti": "Technical Indicators",
    "eh": "Earnings History",
    "ee": "Earnings Estimates",
    "et": "EPS Trend",
    "er": "EPS Revisions",
    "mc": "Macro",
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
# ❹  Per-section extractors — Screener
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


# ─────────────────────────────────────────────────────────────────
# ❺  Per-section extractors — yfinance
# ─────────────────────────────────────────────────────────────────

def _yf_ticker(ticker: str):
    """
    Return a yfinance Ticker object.
    Appends '.NS' if no exchange suffix is present.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance not installed — run: pip install yfinance")
    sym = ticker if ("." in ticker or ticker.endswith(".BO")) else ticker + ".NS"
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


def extract_earnings_history(ticker):
    print(f"\n  ▶ Extracting Earnings History …")
    symbol = clean_ticker_for_screener(ticker)
    try:
        yt   = _yf_ticker(ticker)
        data = yt.earnings_history          # DataFrame or None
        if data is None or (hasattr(data, "empty") and data.empty):
            print(f"  ⚠  earnings_history: no data for {ticker}")
            return None
        records = []
        for _, row in data.iterrows():
            records.append({
                "quarter_end":    str(row.get("quarter", ""))[:10],
                "eps_actual":     row.get("epsActual"),
                "eps_estimate":   row.get("epsEstimate"),
                "eps_difference": row.get("epsDifference"),
                "surprise_pct":   row.get("surprisePercent"),
            })
        return dict(symbol=symbol, records=records)
    except Exception as e:
        print(f"  [ERROR] extract_earnings_history: {e}")
        return None


def extract_earnings_estimates(ticker):
    print(f"\n  ▶ Extracting Earnings Estimates …")
    symbol    = clean_ticker_for_screener(ticker)
    snap_date = date.today().isoformat()
    try:
        yt   = _yf_ticker(ticker)
        data = yt.earnings_estimate         # DataFrame or None
        if data is None or (hasattr(data, "empty") and data.empty):
            print(f"  ⚠  earnings_estimates: no data for {ticker}")
            return None
        records = []
        for period_code, row in data.iterrows():
            records.append({
                "snapshot_date": snap_date,
                "period_code":   str(period_code),
                "avg_eps":       row.get("avg"),
                "low_eps":       row.get("low"),
                "high_eps":      row.get("high"),
                "year_ago_eps":  row.get("yearAgoEps"),
                "analyst_count": row.get("numberOfAnalysts"),
                "growth_pct":    row.get("growth"),
            })
        return dict(symbol=symbol, records=records)
    except Exception as e:
        print(f"  [ERROR] extract_earnings_estimates: {e}")
        return None


def extract_eps_trend(ticker):
    print(f"\n  ▶ Extracting EPS Trend …")
    symbol    = clean_ticker_for_screener(ticker)
    snap_date = date.today().isoformat()
    try:
        yt   = _yf_ticker(ticker)
        data = yt.eps_trend                 # DataFrame or None
        if data is None or (hasattr(data, "empty") and data.empty):
            print(f"  ⚠  eps_trend: no data for {ticker}")
            return None
        records = []
        for period_code, row in data.iterrows():
            records.append({
                "snapshot_date":   snap_date,
                "period_code":     str(period_code),
                "current_est":     row.get("current"),
                "seven_days_ago":  row.get("7daysAgo"),
                "thirty_days_ago": row.get("30daysAgo"),
                "sixty_days_ago":  row.get("60daysAgo"),
                "ninety_days_ago": row.get("90daysAgo"),
            })
        return dict(symbol=symbol, records=records)
    except Exception as e:
        print(f"  [ERROR] extract_eps_trend: {e}")
        return None


def extract_eps_revisions(ticker):
    print(f"\n  ▶ Extracting EPS Revisions …")
    symbol    = clean_ticker_for_screener(ticker)
    snap_date = date.today().isoformat()
    try:
        yt   = _yf_ticker(ticker)
        data = yt.eps_revisions             # DataFrame or None
        if data is None or (hasattr(data, "empty") and data.empty):
            print(f"  ⚠  eps_revisions: no data for {ticker}")
            return None
        records = []
        for period_code, row in data.iterrows():
            records.append({
                "snapshot_date":  snap_date,
                "period_code":    str(period_code),
                "up_last_7d":     row.get("upLast7days"),
                "up_last_30d":    row.get("upLast30days"),
                "down_last_30d":  row.get("downLast30days"),
                "down_last_7d":   row.get("downLast7days"),
            })
        return dict(symbol=symbol, records=records)
    except Exception as e:
        print(f"  [ERROR] extract_eps_revisions: {e}")
        return None


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
        from extract.macro import (
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
    "bs": extract_balance_sheet,
    "pl": extract_profit_loss,
    "cf": extract_cash_flow,
    "qr": extract_quarterly_results,
    "sh": extract_shareholding,
    "pr": extract_price,
    "ti": extract_technicals,
    "eh": extract_earnings_history,
    "ee": extract_earnings_estimates,
    "et": extract_eps_trend,
    "er": extract_eps_revisions,
    "mc": extract_macro,
}


def _load_result(section: str, result: dict):
    """Route result dict to the correct MySQL loader."""

    # ── Screener sections ────────────────────────────────────────
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

    # ── yfinance / MySQL sections ────────────────────────────────
    elif section == "pr":
        load_price(DB_CONFIG, result["df"], result["symbol"])

    elif section == "ti":
        load_technicals(DB_CONFIG, result["df"], result["symbol"])

    elif section == "eh":
        load_earnings_history(DB_CONFIG, result["records"], result["symbol"])

    elif section == "ee":
        load_earnings_estimates(DB_CONFIG, result["records"], result["symbol"])

    elif section == "et":
        load_eps_trend(DB_CONFIG, result["records"], result["symbol"])

    elif section == "er":
        load_eps_revisions(DB_CONFIG, result["records"], result["symbol"])

    elif section == "mc":
        sd = result["snapshot_date"]
        load_market_indices(DB_CONFIG, result["indices_data"], sd)
        load_forex_commodities(DB_CONFIG, result["forex_data"], sd)
        load_rbi_rates(DB_CONFIG, result["rbi_data"])
        load_macro_indicators(DB_CONFIG, result["indicators_list"])


# ─────────────────────────────────────────────────────────────────
# ❼  Per-ticker pipeline runner
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