"""
sh_loader.py  –  Shareholding Pattern Loader
==============================================
Upserts rows into `shareholding`.
Screener's shareholding table has no child/schedule breakdowns,
so there is no items table — only parent rows.
Prints a missing-value report after every load cycle.

Dependencies:  pip install mysql-connector-python
"""

import mysql.connector
from datetime import datetime, date, timedelta
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Screener label  →  shareholding column mapping
# ─────────────────────────────────────────────────────────────
PARENT_LABEL_MAP: dict[str, str] = {
    "Promoters":                    "promoter_pct",
    "Promoter":                     "promoter_pct",
    "FII":                          "fii_pct",
    "Foreign Institutions":         "fii_pct",
    "Foreign Institutional Investors": "fii_pct",
    "DII":                          "dii_pct",
    "Domestic Institutions":        "dii_pct",
    "Domestic Institutional Investors": "dii_pct",
    "Public":                       "public_pct",
    "Government":                   "government_pct",
    "Others":                       "others_pct",
}

UNIVERSAL_COLS = ["promoter_pct", "fii_pct", "dii_pct", "public_pct"]


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def parse_quarter_end(raw: str) -> Optional[date]:
    """
    Shareholding headers: 'Jun 2023', 'Sep-23', 'Mar 2024'
    Returns last day of that quarter month.
    """
    raw = raw.strip()
    if raw.upper() in ("", "-"):
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
    print(f"  [WARN] Cannot parse shareholding date header: '{raw}' — skipping")
    return None


# ─────────────────────────────────────────────────────────────
# Upsert
# ─────────────────────────────────────────────────────────────
def _upsert_shareholding(cursor, symbol, period_end, col_values, data_source):
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
        INSERT INTO shareholding
            (symbol, period_end,
             {col_names}, data_source)
        VALUES (%s, %s, {placeholders}, %s)
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            data_source = VALUES(data_source),
            updated_at  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql,
        [symbol, period_end] + values + [data_source])


# ─────────────────────────────────────────────────────────────
# Missing-value report
# ─────────────────────────────────────────────────────────────
def print_missing_report(symbol, dates, rows):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Shareholding  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False

    for screener_label, col_name in PARENT_LABEL_MAP.items():
        if col_name not in UNIVERSAL_COLS:
            continue
        if screener_label not in rows:
            continue
        for i, v in enumerate(rows[screener_label]):
            if v is None:
                period = dates[i] if i < len(dates) else f"col-{i}"
                print(f"  [ROW]  '{screener_label}' · {period} — NULL (Screener did not provide)")
                any_missing = True

    # Check for labels completely absent from the page
    seen_cols: set = set()
    for label, col_name in PARENT_LABEL_MAP.items():
        if col_name in UNIVERSAL_COLS and col_name not in seen_cols:
            if label in rows:
                seen_cols.add(col_name)
    for col_name in UNIVERSAL_COLS:
        if col_name not in seen_cols:
            print(f"  [ROW]  '{col_name}' — not present on Screener page")
            any_missing = True

    if not any_missing:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────
# Master load function
# ─────────────────────────────────────────────────────────────
def load_shareholding(db_config, symbol, dates, shareholding_rows):
    """
    Params
    ------
    db_config          : mysql.connector connect kwargs
    symbol             : e.g. 'HAL'
    dates              : list of quarter-header strings from scraper
    shareholding_rows  : {screener_label: [val, …]}
                         (the 'shareholding' key from scraper result dict)
    """
    print(f"\n[SH LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    inserted = 0

    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    for col_idx, raw_date in enumerate(dates):
        period_end = parse_quarter_end(raw_date)
        if period_end is None:
            print(f"  [SKIP] '{raw_date}' unparseable — skipping")
            continue

        col_values: dict = {}
        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if screener_label in shareholding_rows and col_name not in col_values:
                vals = shareholding_rows[screener_label]
                col_values[col_name] = vals[col_idx] if col_idx < len(vals) else None

        _upsert_shareholding(cursor, symbol, period_end, col_values, "screener")
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[SH LOADER] ✓ Upserted {inserted} rows for {symbol}")
    print_missing_report(symbol, dates, shareholding_rows)