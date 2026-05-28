"""
corporate_actions.py  –  Corporate Actions Extractor
=====================================================
Fetches dividends and stock splits for a given NSE ticker
using yfinance and returns a normalised dict ready for ca_loader.py.

Dependencies:  pip install yfinance pandas
"""

import yfinance as yf
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Symbol helpers
# ─────────────────────────────────────────────────────────────────────────────
def _to_yf_symbol(ticker: str) -> str:
    """
    Convert a bare NSE symbol to a yfinance-compatible symbol.
    If the caller has already appended a suffix (.NS / .BO) leave it as-is.
    Otherwise append '.NS' (NSE is the primary exchange for Indian equities).

    Examples
      'HAL'        → 'HAL.NS'
      'HDFCBANK.NS' → 'HDFCBANK.NS'
      'RELIANCE.BO' → 'RELIANCE.BO'
    """
    upper = ticker.upper().strip()
    if upper.endswith(".NS") or upper.endswith(".BO"):
        return upper
    return upper + ".NS"


# ─────────────────────────────────────────────────────────────────────────────
# Core fetcher
# ─────────────────────────────────────────────────────────────────────────────
def fetch_corporate_actions(symbol: str) -> dict:
    """
    Fetch dividends and stock splits via yfinance.

    Parameters
    ----------
    symbol : bare NSE ticker ('HAL') or suffixed ('HAL.NS')

    Returns
    -------
    dict with zero or more of these keys:
        'dividend' : pd.DataFrame(columns=['date', 'value'])
        'split'    : pd.DataFrame(columns=['date', 'value'])
    Keys are omitted (not set to None) when no data is available so the
    loader can iterate over present keys without extra guards.

    Note: action_type keys use singular lowercase ('dividend', 'split')
    to match the corporate_actions.action_type column values in the schema.
    """
    yf_symbol = _to_yf_symbol(symbol)
    t   = yf.Ticker(yf_symbol)
    out = {}

    # ── Dividends ────────────────────────────────────────────────────────────
    try:
        divs = t.dividends
        if divs is not None and not divs.empty:
            divs = divs.reset_index()
            divs.columns = ["date", "value"]
            divs["date"] = pd.to_datetime(divs["date"]).dt.date
            out["dividend"] = divs
    except Exception as e:
        print(f"  [WARN] Could not fetch dividends for {yf_symbol}: {e}")

    # ── Splits ───────────────────────────────────────────────────────────────
    try:
        splits = t.splits
        if splits is not None and not splits.empty:
            splits = splits.reset_index()
            splits.columns = ["date", "value"]
            splits["date"] = pd.to_datetime(splits["date"]).dt.date
            out["split"] = splits
    except Exception as e:
        print(f"  [WARN] Could not fetch splits for {yf_symbol}: {e}")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline-compatible scraper wrapper
# ─────────────────────────────────────────────────────────────────────────────
def scrape_corporate_actions(ticker: str) -> dict | None:
    """
    Top-level extractor called by mysql_pipeline.py.

    Returns
    -------
    {
        'symbol':  str,           # clean bare symbol, e.g. 'HAL'
        'actions': dict,          # output of fetch_corporate_actions()
    }
    or None if nothing was fetched.
    """
    # Strip any exchange suffix for the DB symbol column
    clean = ticker.upper().strip()
    for suffix in (".NS", ".BO", ":NS", ":BO"):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]
            break

    print(f"\n  ▶ Extracting Corporate Actions for {clean} …")
    actions = fetch_corporate_actions(ticker)

    if not actions:
        print(f"  ⚠  corporate_actions: no dividends or splits found for {ticker}")
        return None

    total = sum(len(df) for df in actions.values())
    for action_type, df in actions.items():
        print(f"  ✔  {action_type:<10} : {len(df)} rows")
    print(f"  ✔  Total corporate action rows fetched: {total}")

    return dict(symbol=clean, actions=actions)