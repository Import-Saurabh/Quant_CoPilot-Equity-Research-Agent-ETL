"""
etl/extract/profit_and_loss.py
────────────────────────────────────────────────────────────────
Fetches Profit & Loss data from Screener.in for any NSE ticker.
Returns a clean DataFrame ready for profit_and_loss_loader.py.

Replaces: statements.py (yfinance income logic removed entirely)
────────────────────────────────────────────────────────────────
"""

import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ── Session setup ──────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    )
})

# ── Column name normalisation ──────────────────────────────────
_COLUMN_MAPPING = {
    "Sales":                "sales",
    "Expenses":             "expenses",
    "Operating Profit":     "operating_profit",
    "OPM %":                "opm_pct",
    "Other Income":         "other_income",
    "Interest":             "interest",
    "Depreciation":         "depreciation",
    "Profit before tax":    "profit_before_tax",
    "Tax %":                "tax_pct",
    "Net Profit":           "net_profit",
    "EPS in Rs":            "eps",
    "Dividend Payout %":    "dividend_payout_pct",
}


def _scrape_pl_table(ticker: str, consolidated: bool = True) -> pd.DataFrame | None:
    """
    Scrape the P&L table from Screener.in for *ticker*.

    Parameters
    ----------
    ticker       : NSE symbol, e.g. "ADANIPORTS"
    consolidated : True  → uses /consolidated/ URL (default)
                   False → falls back to standalone URL

    Returns
    -------
    Wide DataFrame  – columns: [symbol, period_end, <metrics...>]
                      one row per reporting period
    None            – on any failure
    """
    suffix = "consolidated" if consolidated else ""
    url = f"https://www.screener.in/company/{ticker.upper()}/{suffix}/"

    try:
        resp = _session.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"  [P&L] HTTP {resp.status_code} for {ticker} (consolidated={consolidated})")
            return None

        soup = BeautifulSoup(resp.content, "html.parser")
        pl_section = soup.find("section", id="profit-loss")
        if not pl_section:
            print(f"  [P&L] 'profit-loss' section not found for {ticker}")
            return None

        table = pl_section.find("table", class_="data-table")
        if not table:
            print(f"  [P&L] data-table not found inside profit-loss section for {ticker}")
            return None

        # ── Headers (years) ───────────────────────────────────
        thead = table.find("thead")
        headers = [th.text.strip() for th in thead.find_all("th") if th.text.strip()]
        headers.insert(0, "Metric")

        # ── Data rows ─────────────────────────────────────────
        rows = []
        for tr in table.find("tbody").find_all("tr"):
            cells = tr.find_all("td")
            row_data = [
                cell.get_text(strip=True).replace("+", "").strip()
                for cell in cells
            ]
            if row_data:
                rows.append(row_data)

        if not rows:
            print(f"  [P&L] No data rows found for {ticker}")
            return None

        # ── Build raw DataFrame (metrics as rows) ─────────────
        df_raw = pd.DataFrame(rows, columns=headers)

        # ── Transpose → periods as rows, metrics as columns ───
        df = df_raw.set_index("Metric").T.reset_index()
        df.rename(columns={"index": "period_end"}, inplace=True)
        df.insert(0, "symbol", ticker.upper())

        # ── Normalise column names ─────────────────────────────
        df.rename(columns=_COLUMN_MAPPING, inplace=True)

        # ── Drop TTM row if present ────────────────────────────
        df = df[~df["period_end"].str.upper().isin(["TTM", ""])].copy()
        df.reset_index(drop=True, inplace=True)

        return df

    except Exception as exc:
        print(f"  [P&L] Exception scraping {ticker}: {exc}")
        return None


def fetch_profit_and_loss(ticker: str, period_type: str = "annual") -> pd.DataFrame | None:
    """
    Public entry point.  Tries consolidated first, falls back to standalone.

    Parameters
    ----------
    ticker      : NSE symbol, e.g. "ADANIPORTS"
    period_type : "annual" or "quarterly"
                  (Screener shows annual by default on the P&L table;
                   quarterly is available via the same section)

    Returns
    -------
    DataFrame with columns matching the profit_and_loss table schema,
    or None on failure.
    """
    print(f"  [P&L] Fetching {period_type} P&L for {ticker} …")

    df = _scrape_pl_table(ticker, consolidated=True)

    # Fallback to standalone page
    if df is None:
        time.sleep(1)
        print(f"  [P&L] Retrying {ticker} on standalone page …")
        df = _scrape_pl_table(ticker, consolidated=False)

    if df is None:
        print(f"  [P&L] ❌ Could not fetch P&L for {ticker}")
        return None

    # Tag period_type so the loader can use it
    df["period_type"] = period_type

    print(f"  [P&L] ✅ {len(df)} periods fetched for {ticker}")
    return df


# ── Standalone test ────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "ADANIPORTS"
    result = fetch_profit_and_loss(sym)
    if result is not None:
        print(result.to_string())