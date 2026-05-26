"""
gm_loader.py  –  Growth Metrics Loader
========================================
Upserts one row per (symbol, as_of_date) into `growth_metrics`.

Schema columns written
----------------------
sales_cagr_10y / _5y / _3y / _ttm
profit_cagr_10y / _5y / _3y / _ttm
stock_cagr_10y / _5y / _3y / _ttm
roe_10y / _5y / _3y / _last
completeness_pct   — fraction of the 16 metric cols that are non-NULL

Screener table-header → column mapping
---------------------------------------
Screener emits four <table class="ranges-table"> blocks whose <th> headers are:
  "Compounded Sales Growth"
  "Compounded Profit Growth"
  "Stock Price CAGR"
  "Return on Equity"

Row labels inside each table are: "10 Years:", "5 Years:", "3 Years:", "TTM:"
(For ROE the last row is labelled "Last Year:" instead of "TTM:")

Dependencies:  pip install mysql-connector-python
"""

import math
import mysql.connector
from datetime import date
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# Value sanitiser
# ─────────────────────────────────────────────────────────────────

def _clean(v) -> Optional[float]:
    """
    '18%' → 18.0,  '18.5%' → 18.5,  '' / None / 'N/A' → None
    Handles plain numbers too ('18.5' → 18.5).
    """
    if v is None:
        return None
    s = str(v).replace("%", "").replace(",", "").strip()
    if s in ("", "-", "N/A", "n/a", "—"):
        return None
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────
# Table-header  →  (col_prefix, ttm_col_suffix)
# ─────────────────────────────────────────────────────────────────
# Maps the exact <th> text Screener emits to the DB column prefix
# and the name used for the TTM / last-year slot.

TABLE_MAP: dict[str, tuple[str, str]] = {
    # Screener header text              col_prefix   ttm_col_name
    "Compounded Sales Growth":         ("sales_cagr",   "sales_ttm"),
    "Compounded Profit Growth":        ("profit_cagr",  "profit_ttm"),
    "Stock Price CAGR":                ("stock_cagr",   "stock_ttm"),
    "Return on Equity":                ("roe",          "roe_last"),
}

# Row-label → column suffix (applied to the prefix above)
ROW_SUFFIX_MAP: dict[str, str] = {
    "10 Years":  "10y",
    "10 years":  "10y",
    "5 Years":   "5y",
    "5 years":   "5y",
    "3 Years":   "3y",
    "3 years":   "3y",
    "TTM":       "ttm",      # Sales / Profit / Stock
    "Last Year": "last",     # ROE
}

# All 16 metric columns — used for completeness_pct
ALL_METRIC_COLS = [
    "sales_cagr_10y",  "sales_cagr_5y",  "sales_cagr_3y",  "sales_ttm",
    "profit_cagr_10y", "profit_cagr_5y", "profit_cagr_3y", "profit_ttm",
    "stock_cagr_10y",  "stock_cagr_5y",  "stock_cagr_3y",  "stock_ttm",
    "roe_10y",         "roe_5y",          "roe_3y",         "roe_last",
]


# ─────────────────────────────────────────────────────────────────
# Result dict  →  flat col_values dict
# ─────────────────────────────────────────────────────────────────

def _build_col_values(metrics: dict) -> dict:
    """
    metrics: {table_header: {row_label: raw_value_str}}
    Returns a flat dict keyed by DB column name.
    """
    col_values: dict = {}

    for header, rows in metrics.items():
        mapping = TABLE_MAP.get(header)
        if mapping is None:
            continue
        col_prefix, ttm_col = mapping

        for row_label, raw_val in rows.items():
            # Strip trailing colon Screener sometimes adds: "10 Years:" → "10 Years"
            clean_label = row_label.rstrip(":").strip()
            suffix = ROW_SUFFIX_MAP.get(clean_label)
            if suffix is None:
                continue

            # For ROE: "last" → roe_last  (ttm_col already correct)
            # For others: "ttm" → sales_ttm / profit_ttm / stock_ttm
            if suffix in ("ttm", "last"):
                col_name = ttm_col
            else:
                col_name = f"{col_prefix}_{suffix}"

            col_values[col_name] = _clean(raw_val)

    return col_values


# ─────────────────────────────────────────────────────────────────
# Completeness
# ─────────────────────────────────────────────────────────────────

def _completeness(col_values: dict) -> float:
    filled = sum(1 for c in ALL_METRIC_COLS if col_values.get(c) is not None)
    return round(filled / len(ALL_METRIC_COLS) * 100, 2)


# ─────────────────────────────────────────────────────────────────
# Missing-value report
# ─────────────────────────────────────────────────────────────────

def _print_missing_report(symbol: str, col_values: dict):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Growth Metrics  ·  {symbol}")
    print(f"{'─'*60}")
    missing = [c for c in ALL_METRIC_COLS if col_values.get(c) is None]
    if missing:
        for c in missing:
            print(f"  [COL]  '{c}' — NULL (not provided by Screener)")
    else:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────

def _get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def _upsert(cursor, symbol: str, as_of_date: date, col_values: dict):
    cols      = ALL_METRIC_COLS + ["completeness_pct"]
    set_cls   = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in cols)
    ph        = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(f"`{c}`" for c in cols)
    values    = [col_values.get(c) for c in ALL_METRIC_COLS] + [col_values["completeness_pct"]]

    sql = f"""
        INSERT INTO growth_metrics
            (`symbol`, `as_of_date`, {col_names})
        VALUES (%s, %s, {ph})
        ON DUPLICATE KEY UPDATE
            {set_cls},
            `updated_at` = CURRENT_TIMESTAMP
    """
    cursor.execute(sql, [symbol, as_of_date] + values)


# ─────────────────────────────────────────────────────────────────
# Master load function
# ─────────────────────────────────────────────────────────────────

def load_growth_metrics(db_config: dict, symbol: str,
                        metrics: dict, as_of_date: date = None):
    """
    Parameters
    ----------
    db_config  : mysql.connector connect kwargs
    symbol     : e.g. 'HAL'
    metrics    : {table_header: {row_label: value_str}}
                 (direct return value from scrape_growth_metrics)
    as_of_date : date to stamp the row; defaults to today
    """
    if as_of_date is None:
        as_of_date = date.today()

    print(f"\n[GM LOADER] Connecting to MySQL …")
    conn   = _get_connection(db_config)
    cursor = conn.cursor()

    # Ensure parent stock row exists
    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    col_values = _build_col_values(metrics)
    col_values["completeness_pct"] = _completeness(col_values)

    _upsert(cursor, symbol, as_of_date, col_values)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[GM LOADER] ✓ Upserted 1 row for {symbol}  "
          f"(completeness: {col_values['completeness_pct']}%)")
    _print_missing_report(symbol, col_values)