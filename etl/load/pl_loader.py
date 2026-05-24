"""
pl_loader.py  –  Profit & Loss Loader
=======================================
Upserts rows into `profit_loss` (parent) and `profit_loss_items` (child).
Prints a missing-value report after every load cycle.

Dependencies:  pip install mysql-connector-python
"""

import mysql.connector
from datetime import datetime, date, timedelta
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Screener label  →  profit_loss column mapping
# Only universal lines that appear across ALL sectors go here.
# Everything else auto-routes to profit_loss_items.
# ─────────────────────────────────────────────────────────────
PARENT_LABEL_MAP: dict[str, str] = {
    "Sales":                    "sales",
    "Revenue":                  "sales",          # alternate label
    "Expenses":                 "expenses",
    "Operating Profit":         "operating_profit",
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
    "Dividend Payout %":        "dividend_payout_pct",
}

# Columns considered critical for the missing-value report
UNIVERSAL_COLS = [
    "sales", "expenses", "operating_profit",
    "profit_before_tax", "net_profit", "eps",
]


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def parse_period_end(raw: str) -> Optional[date]:
    """
    Handles: 'Mar 2024', 'Mar-24', 'Mar-2024', 'TTM', '2024-03-31'
    Returns last day of that month, or None for TTM / unparseable.
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
    print(f"  [WARN] Cannot parse P&L date header: '{raw}' — skipping")
    return None


def _period_type(raw: str) -> str:
    return "ttm" if raw.strip().upper() == "TTM" else "annual"


# ─────────────────────────────────────────────────────────────
# Upserts
# ─────────────────────────────────────────────────────────────
def _upsert_parent(cursor, symbol, period_end, period_type,
                   is_consolidated, col_values, data_source):
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
        INSERT INTO profit_loss
            (symbol, period_end, period_type, is_consolidated,
             {col_names}, data_source)
        VALUES (%s, %s, %s, %s, {placeholders}, %s)
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            data_source = VALUES(data_source),
            updated_at  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql,
        [symbol, period_end, period_type, is_consolidated] + values + [data_source])


def _upsert_item(cursor, symbol, period_end, period_type,
                 is_consolidated, parent_label, item_label,
                 value, sort_order, data_source):
    sql = """
        INSERT INTO profit_loss_items
            (symbol, period_end, period_type, is_consolidated,
             parent_label, item_label, value, sort_order, data_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            value       = VALUES(value),
            sort_order  = VALUES(sort_order),
            data_source = VALUES(data_source)
    """
    cursor.execute(sql, [
        symbol, period_end, period_type, is_consolidated,
        parent_label[:100], item_label[:100],
        value, sort_order, data_source,
    ])


# ─────────────────────────────────────────────────────────────
# Missing-value report
# ─────────────────────────────────────────────────────────────
def print_missing_report(symbol, dates, main_rows, child_items):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  P&L  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False

    for screener_label, col_name in PARENT_LABEL_MAP.items():
        if col_name not in UNIVERSAL_COLS:
            continue
        if screener_label not in main_rows:
            continue  # only report first alias found
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
def load_profit_loss(db_config, symbol, dates, main_rows,
                     child_items, is_consolidated=1):
    """
    Params
    ------
    db_config      : mysql.connector connect kwargs
    symbol         : e.g. 'HAL'
    dates          : list of period-header strings
    main_rows      : {screener_label: [val, …]}
    child_items    : {parent_label: {child_label: [val, …]}}
    is_consolidated: 1 or 0
    """
    print(f"\n[PL LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    inserted_parent = 0
    inserted_child  = 0

    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    for col_idx, raw_date in enumerate(dates):
        ptype      = _period_type(raw_date)
        period_end = parse_period_end(raw_date)
        if period_end is None and ptype != "ttm":
            print(f"  [SKIP] '{raw_date}' unparseable — skipping")
            continue
        # For TTM use today as a surrogate period_end so the row has a date
        if period_end is None:
            period_end = date.today()

        col_values: dict = {}
        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if screener_label in main_rows and col_name not in col_values:
                vals = main_rows[screener_label]
                col_values[col_name] = vals[col_idx] if col_idx < len(vals) else None

        _upsert_parent(cursor, symbol, period_end, ptype,
                       is_consolidated, col_values, "screener")
        inserted_parent += 1

        for parent_label, rows in child_items.items():
            for sort_idx, (child_label, vals) in enumerate(rows.items()):
                value = vals[col_idx] if col_idx < len(vals) else None
                _upsert_item(cursor, symbol, period_end, ptype,
                             is_consolidated, parent_label, child_label,
                             value, sort_idx, "screener")
                inserted_child += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[PL LOADER] ✓ Upserted {inserted_parent} parent rows, "
          f"{inserted_child} child rows for {symbol}")

    print_missing_report(symbol, dates, main_rows, child_items)