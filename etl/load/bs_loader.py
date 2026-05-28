"""
bs_loader.py  –  Balance Sheet Loader
======================================
Responsibility: Takes the structured dict produced by the scraper and
upserts rows into `balance_sheet` (parent) and `balance_sheet_items` (child).
Also prints a missing-value report after every insert cycle.

Dependencies:  pip install mysql-connector-python
"""

import math
import mysql.connector
from datetime import datetime, date
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Value sanitisers
# ─────────────────────────────────────────────────────────────
def _clean_value(v):
    """
    Convert Screener child-item values to a plain Python float/None.
    Handles:
      • Already a float/int   → return as-is
      • Comma-formatted str   '2,342'  → 2342.0
      • Dict artifact         {'class': 'strong'}  → None
      • None / empty string   → None
      • NaN / Inf             → None
    """
    if v is None:
        return None
    if isinstance(v, dict):          # HTML artifact from scraper
        return None
    try:
        f = float(str(v).replace(",", "").strip())
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _clean_pct(v):
    """
    Convert percentage strings like '15%', '-3%', '145%' to float (15.0, -3.0, …).
    Returns None for non-parseable values.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    s = str(v).replace("%", "").replace(",", "").strip()
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None

# ─────────────────────────────────────────────────────────────
# Screener label  →  balance_sheet column mapping
# Only the truly universal columns belong here.
# Everything else goes to balance_sheet_items automatically.
# ─────────────────────────────────────────────────────────────
PARENT_LABEL_MAP: dict[str, str] = {
    # Liabilities
    "Equity Capital":       "equity_capital",
    "Reserves":             "reserves",
    # total_equity column dropped — equity_capital + reserves gives the same figure
    "Borrowings":           "borrowings",
    "Other Liabilities":    "other_liabilities",
    "Total Liabilities":    "total_liabilities",
    # Assets
    "Fixed Assets":         "fixed_assets",
    "CWIP":                 "cwip",
    "Investments":          "investments",
    "Other Assets":         "other_assets",
    "Inventories":          "inventories",
    "Trade Receivables":    "trade_receivables",
    "Cash Equivalents":     "cash_equivalents",
    "Cash & Equivalents":   "cash_equivalents",
    "Loans & Advances":     "loans_advances",
    "Total Assets":         "total_assets",
    "Net Debt":             "net_debt",
}

# Columns that are meaningful for all sectors (for missing-value report)
UNIVERSAL_COLS = [
    "equity_capital", "reserves", "borrowings",
    "total_liabilities", "fixed_assets", "total_assets",
    "cash_equivalents",
]


# ─────────────────────────────────────────────────────────────
# DB connection helper
# ─────────────────────────────────────────────────────────────
def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


# ─────────────────────────────────────────────────────────────
# Period parsing
# ─────────────────────────────────────────────────────────────
def parse_period_end(raw: str) -> Optional[date]:
    """
    Screener date headers arrive in several formats:
      'Mar 2024', 'Mar-24', '2024-03-31', 'TTM'
    Returns a date object (last day of that month) or None for TTM/unparseable.
    """
    raw = raw.strip()
    if raw.upper() in ("TTM", ""):
        return None

    formats = ["%b %Y", "%b-%y", "%b-%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            # Advance to last day of that month
            if dt.month == 12:
                last_day = date(dt.year + 1, 1, 1)
            else:
                last_day = date(dt.year, dt.month + 1, 1)
            from datetime import timedelta
            return last_day - timedelta(days=1)
        except ValueError:
            continue
    print(f"  [WARN] Could not parse date header: '{raw}' — skipping column")
    return None


# ─────────────────────────────────────────────────────────────
# Core upsert: balance_sheet  (parent row)
# ─────────────────────────────────────────────────────────────
def upsert_balance_sheet_parent(
    cursor,
    symbol: str,
    period_end: date,
    is_consolidated: int,
    col_values: dict,          # {column_name: value_or_None}
    data_source: str = "screener",
):
    """INSERT … ON DUPLICATE KEY UPDATE for one period row."""

    all_cols = list(PARENT_LABEL_MAP.values())
    # de-dup preserving order
    seen = set()
    unique_cols = [c for c in all_cols if not (c in seen or seen.add(c))]

    set_clauses = ", ".join(
        f"{col} = VALUES({col})" for col in unique_cols
    )

    placeholders = ", ".join(["%s"] * len(unique_cols))
    col_names    = ", ".join(unique_cols)
    values       = [col_values.get(c) for c in unique_cols]

    sql = f"""
        INSERT INTO balance_sheet
            (symbol, period_end, period_type, is_consolidated,
             {col_names}, data_source)
        VALUES
            (%s, %s, %s, %s, {placeholders}, %s)
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            data_source = VALUES(data_source),
            updated_at  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql, [symbol, period_end, "annual", is_consolidated] + values + [data_source])


# ─────────────────────────────────────────────────────────────
# Core upsert: balance_sheet_items  (child row)
# ─────────────────────────────────────────────────────────────
def upsert_bs_item(
    cursor,
    symbol: str,
    period_end: date,
    is_consolidated: int,
    parent_label: str,
    item_label: str,
    value,
    sort_order: int = 0,
    data_source: str = "screener",
):
    sql = """
        INSERT INTO balance_sheet_items
            (symbol, period_end, period_type, is_consolidated,
             parent_label, item_label, value, sort_order, data_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            value       = VALUES(value),
            sort_order  = VALUES(sort_order),
            data_source = VALUES(data_source)
    """
    cursor.execute(sql, [
        symbol, period_end, "annual", is_consolidated,
        parent_label[:100], item_label[:100], _clean_value(value), sort_order, data_source,
    ])


# ─────────────────────────────────────────────────────────────
# Missing value report
# ─────────────────────────────────────────────────────────────
def print_missing_report(
    symbol: str,
    dates: list[str],
    main_rows: dict,
    child_items: dict,          # {parent_label: {child_label: [values]}}
):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  {symbol}")
    print(f"{'─'*60}")

    any_missing = False

    # Check parent rows
    for screener_label, col_name in PARENT_LABEL_MAP.items():
        if col_name not in UNIVERSAL_COLS:
            continue
        if screener_label not in main_rows:
            print(f"  [PARENT]  '{screener_label}' — not present on Screener page")
            any_missing = True
            continue
        vals = main_rows[screener_label]
        for i, v in enumerate(vals):
            if v is None:
                period = dates[i] if i < len(dates) else f"col-{i}"
                print(f"  [PARENT]  '{screener_label}' · {period} — NULL (Screener did not provide)")
                any_missing = True

    # Check child rows
    for parent_label, rows in child_items.items():
        for child_label, vals in rows.items():
            for i, v in enumerate(vals):
                if v is None:
                    period = dates[i] if i < len(dates) else f"col-{i}"
                    print(f"  [CHILD]   '{parent_label}' → '{child_label}' · {period} — NULL (Screener did not provide)")
                    any_missing = True

    if not any_missing:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────
# Master load function  (called from pipeline)
# ─────────────────────────────────────────────────────────────
def load_balance_sheet(
    db_config: dict,
    symbol: str,
    dates: list[str],
    main_rows: dict,
    child_items: dict,          # {parent_label: {child_label: [values]}}
    is_consolidated: int = 1,
):
    """
    Params
    ------
    db_config      : mysql.connector connect kwargs
    symbol         : e.g. 'HAL'
    dates          : list of period-header strings from parse_html_table
    main_rows      : {screener_label: [val, val, …]}  — parent table rows
    child_items    : {parent_label:   {child_label: [val, val, …]}}
    is_consolidated: 1 or 0
    """
    print(f"\n[LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    inserted_parent = 0
    inserted_child  = 0

    # Ensure symbol exists in stocks master (bare minimum row)
    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    for col_idx, raw_date in enumerate(dates):
        period_end = parse_period_end(raw_date)
        if period_end is None:
            print(f"  [SKIP] Column '{raw_date}' is TTM or unparseable — skipping")
            continue

        # ── Build column-value dict for parent row ──────────────
        col_values: dict = {}
        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if screener_label in main_rows:
                vals = main_rows[screener_label]
                col_values[col_name] = vals[col_idx] if col_idx < len(vals) else None

        upsert_balance_sheet_parent(
            cursor, symbol, period_end, is_consolidated, col_values
        )
        inserted_parent += 1

        # ── Child rows ───────────────────────────────────────────
        for parent_label, rows in child_items.items():
            for sort_idx, (child_label, vals) in enumerate(rows.items()):
                value = vals[col_idx] if col_idx < len(vals) else None
                upsert_bs_item(
                    cursor, symbol, period_end, is_consolidated,
                    parent_label, child_label, value, sort_order=sort_idx
                )
                inserted_child += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[LOADER] ✓ Upserted {inserted_parent} parent rows, {inserted_child} child rows for {symbol}")

    # Print missing value report after every load
    print_missing_report(symbol, dates, main_rows, child_items)