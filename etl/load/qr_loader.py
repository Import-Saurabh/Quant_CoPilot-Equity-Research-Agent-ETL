"""
qr_loader.py  –  Quarterly Results Loader
===========================================
Upserts rows into `quarterly_results` (parent) and
`quarterly_results_items` (child).
Prints a missing-value report after every load cycle.

Dependencies:  pip install mysql-connector-python
"""

import math
import mysql.connector
from datetime import datetime, date, timedelta
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Value sanitisers
# ─────────────────────────────────────────────────────────────
def _clean_value(v):
    """Comma-str '1,651' → 1651.0; dict/None/bad → None."""
    if v is None:
        return None
    if isinstance(v, dict):
        return None
    try:
        f = float(str(v).replace(",", "").strip())
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _clean_pct(v):
    """Pct str '26%' → 26.0; None/bad → None."""
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
# Screener label  →  quarterly_results column mapping
# Same universal P&L lines, targeted at the Quarters table.
# ─────────────────────────────────────────────────────────────
PARENT_LABEL_MAP: dict[str, str] = {
    "Sales":                    "sales",
    "Revenue":                  "sales",
    "Expenses":                 "expenses",
    "Operating Profit":         "operating_profit",
    # ── Bank / NBFC / Financial-service aliases ──────────────
    # Screener shows "Financing Profit" instead of "Operating Profit"
    # and "Financing Margin %" / "NIM %" instead of "OPM %" for these sectors.
    "Financing Profit":         "operating_profit",
    "Financing Margin %":       "opm_pct",
    "NIM %":                    "opm_pct",
    # ────────────────────────────────────────────────────────
    "OPM %":                    "opm_pct",
    "OPM%":                     "opm_pct",
    "Other Income":             "other_income",
    "Interest":                 "interest",
    "Depreciation":             "depreciation",
    "Profit before tax":        "profit_before_tax",
    "Profit Before Tax":        "profit_before_tax",
    "Tax %":                    "tax_pct",
    "Net Profit":               "net_profit",
    "EPS in Rs":                "eps",
    "EPS":                      "eps",
}

UNIVERSAL_COLS = [
    "sales", "expenses", "operating_profit",
    "profit_before_tax", "net_profit", "eps",
]


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def parse_quarter_end(raw: str) -> Optional[date]:
    """
    Quarterly headers look like: 'Jun 2023', 'Sep-23', 'Dec 2022'
    Returns last day of that quarter month.
    """
    raw = raw.strip()
    if raw.upper() in ("TTM", ""):
        return None
    for fmt in ("%b %Y", "%b-%y", "%b-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.month == 12:
                last = date(dt.year + 1, 1, 1) - timedelta(days=1)
            else:
                last = date(dt.year, dt.month + 1, 1) - timedelta(days=1)
            return last
        except ValueError:
            continue
    print(f"  [WARN] Cannot parse quarterly date header: '{raw}' — skipping")
    return None


# ─────────────────────────────────────────────────────────────
# Upserts
# ─────────────────────────────────────────────────────────────
def _upsert_parent(cursor, symbol, period_end, is_consolidated,
                   col_values, data_source):
    seen, unique_cols = set(), []
    for c in PARENT_LABEL_MAP.values():
        if c not in seen:
            seen.add(c)
            unique_cols.append(c)

    set_clauses  = ", ".join(f"{c} = VALUES({c})" for c in unique_cols)
    placeholders = ", ".join(["%s"] * len(unique_cols))
    col_names    = ", ".join(unique_cols)
    values       = [col_values.get(c) for c in unique_cols]

    sql = f"""
        INSERT INTO quarterly_results
            (symbol, period_end, is_consolidated,
             {col_names}, data_source)
        VALUES (%s, %s, %s, {placeholders}, %s)
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            data_source = VALUES(data_source),
            updated_at  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql,
        [symbol, period_end, is_consolidated] + values + [data_source])


def _upsert_item(cursor, symbol, period_end, is_consolidated,
                 parent_label, item_label, value, sort_order, data_source):
    sql = """
        INSERT INTO quarterly_results_items
            (symbol, period_end, is_consolidated,
             parent_label, item_label, value, sort_order, data_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            value       = VALUES(value),
            sort_order  = VALUES(sort_order),
            data_source = VALUES(data_source)
    """
    cursor.execute(sql, [
        symbol, period_end, is_consolidated,
        parent_label[:100], item_label[:100],
        value, sort_order, data_source,
    ])


# ─────────────────────────────────────────────────────────────
# Missing-value report
# ─────────────────────────────────────────────────────────────
def print_missing_report(symbol, dates, main_rows, child_items):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Quarterly Results  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False

    for screener_label, col_name in PARENT_LABEL_MAP.items():
        if col_name not in UNIVERSAL_COLS:
            continue
        if screener_label not in main_rows:
            continue
        for i, v in enumerate(main_rows[screener_label]):
            if v is None:
                period = dates[i] if i < len(dates) else f"col-{i}"
                print(f"  [PARENT]  '{screener_label}' · {period} — NULL (Screener did not provide)")
                any_missing = True

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
# Master load function
# ─────────────────────────────────────────────────────────────
def load_quarterly_results(db_config, symbol, dates, main_rows,
                            child_items, is_consolidated=1):
    """
    Params
    ------
    db_config      : mysql.connector connect kwargs
    symbol         : e.g. 'HAL'
    dates          : list of quarter-header strings
    main_rows      : {screener_label: [val, …]}
    child_items    : {parent_label: {child_label: [val, …]}}
    is_consolidated: 1 or 0
    """
    print(f"\n[QR LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    inserted_parent = 0
    inserted_child  = 0

    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    for col_idx, raw_date in enumerate(dates):
        # Skip the label column (first th is usually "")
        period_end = parse_quarter_end(raw_date)
        if period_end is None:
            print(f"  [SKIP] '{raw_date}' is TTM or unparseable — skipping")
            continue

        PCT_COLS = {"opm_pct", "tax_pct"}
        col_values: dict = {}
        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if screener_label in main_rows and col_name not in col_values:
                vals = main_rows[screener_label]
                raw  = vals[col_idx] if col_idx < len(vals) else None
                col_values[col_name] = _clean_pct(raw) if col_name in PCT_COLS else _clean_value(raw)

        # Also skip "Raw PDF" rows at scraper level; safe to ignore here too
        _upsert_parent(cursor, symbol, period_end, is_consolidated,
                       col_values, "screener")
        inserted_parent += 1

        for parent_label, rows in child_items.items():
            for sort_idx, (child_label, vals) in enumerate(rows.items()):
                value = vals[col_idx] if col_idx < len(vals) else None
                _upsert_item(cursor, symbol, period_end, is_consolidated,
                             parent_label, child_label,
                             _clean_pct(value), sort_idx, "screener")
                inserted_child += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[QR LOADER] ✓ Upserted {inserted_parent} parent rows, "
          f"{inserted_child} child rows for {symbol}")

    print_missing_report(symbol, dates, main_rows, child_items)