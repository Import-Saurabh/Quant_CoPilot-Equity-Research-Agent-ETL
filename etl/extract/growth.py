"""
etl/extract/growth.py  v4.2
────────────────────────────────────────────────────────────
Scrapes Screener.in (consolidated / standalone) for:
  • Sales/Profit/Stock CAGR (10Y,5Y,3Y,TTM)
  • Return on Equity (10Y,5Y,3Y,Last Year)
Does NOT use Yahoo Finance for growth_metrics.
────────────────────────────────────────────────────────────
"""

import re
import requests
import traceback
from bs4 import BeautifulSoup
from datetime import date
from typing import Optional, Dict, List

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _pct_to_float(value_str: str) -> Optional[float]:
    if not value_str:
        return None
    s = value_str.strip()
    if s == "-":
        return None
    match = re.search(r"([-+]?\d+\.?\d*)\s*%?", s)
    if match:
        try:
            return round(float(match.group(1)), 2)
        except ValueError:
            return None
    return None


def _scrape_growth_table(table) -> Dict[str, Optional[float]]:
    """Parse one ranges-table."""
    header_el = table.find("th")
    if not header_el:
        return {}
    header = header_el.text.strip()
    h_lower = header.lower()

    # Determine category
    if "sales growth" in h_lower or "revenue" in h_lower:
        category = "sales"
    elif "profit growth" in h_lower or "net profit" in h_lower:
        category = "profit"
    elif "stock price" in h_lower or "stock cagr" in h_lower:
        category = "stock"
    elif "return on equity" in h_lower or "roe" == h_lower:
        category = "roe"
    else:
        return {}

    result = {}
    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cols = row.find_all("td")
        if len(cols) != 2:
            continue
        period_raw = cols[0].text.strip().rstrip(":").lower()
        value_raw = cols[1].text.strip()
        val = _pct_to_float(value_raw)

        # Map period
        if "10 year" in period_raw:
            suffix = "cagr_10y"
        elif "5 year" in period_raw:
            suffix = "cagr_5y"
        elif "3 year" in period_raw:
            suffix = "cagr_3y"
        elif "ttm" in period_raw or "last 12 month" in period_raw:
            suffix = "ttm"
        elif "last year" in period_raw or "1 year" in period_raw:
            suffix = "last"
        else:
            continue

        if category == "roe" and suffix == "last":
            result["roe_last"] = val
        else:
            result[f"{category}_{suffix}"] = val
    return result


def _scrape_symbol(symbol: str) -> Dict[str, Optional[float]]:
    """Try consolidated first, then standalone."""
    for page_type in ["/consolidated/", "/"]:
        url = f"https://www.screener.in/company/{symbol.upper()}{page_type}"
        print(f"  scraping growth: {url}")
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "html.parser")
            tables = soup.find_all("table", class_="ranges-table")
            if not tables:
                continue

            result = {}
            for tbl in tables:
                result.update(_scrape_growth_table(tbl))
            if result:
                # Remap keys to match DB columns
                renamed = {}
                for k, v in result.items():
                    if k.startswith("roe_cagr_"):
                        new_key = k.replace("roe_cagr_", "roe_")
                        renamed[new_key] = v
                    elif k == "stock_last":
                        renamed["stock_ttm"] = v
                    else:
                        renamed[k] = v
                print(f"  scraped fields: { {k:v for k,v in renamed.items() if v is not None} }")
                return renamed
        except Exception:
            traceback.print_exc()
    return {}


def fetch_growth_metrics(symbol: str) -> dict:
    today = date.today().isoformat()
    scraped = _scrape_symbol(symbol)

    return {
        "as_of_date": today,
        "sales_cagr_10y":   scraped.get("sales_cagr_10y"),
        "sales_cagr_5y":    scraped.get("sales_cagr_5y"),
        "sales_cagr_3y":    scraped.get("sales_cagr_3y"),
        "sales_ttm":        scraped.get("sales_ttm"),
        "profit_cagr_10y":  scraped.get("profit_cagr_10y"),
        "profit_cagr_5y":   scraped.get("profit_cagr_5y"),
        "profit_cagr_3y":   scraped.get("profit_cagr_3y"),
        "profit_ttm":       scraped.get("profit_ttm"),
        "stock_cagr_10y":   scraped.get("stock_cagr_10y"),
        "stock_cagr_5y":    scraped.get("stock_cagr_5y"),
        "stock_cagr_3y":    scraped.get("stock_cagr_3y"),
        "stock_ttm":        scraped.get("stock_ttm"),
        "roe_10y":          scraped.get("roe_10y"),
        "roe_5y":           scraped.get("roe_5y"),
        "roe_3y":           scraped.get("roe_3y"),
        "roe_last":         scraped.get("roe_last"),
        # Left NULL – will be filled by reconciler
        "revenue_cagr_3y": None,
        "net_profit_cagr_3y": None,
        "ebitda_cagr_3y": None,
        "eps_cagr_3y": None,
        "fcf_cagr_3y": None,
    }