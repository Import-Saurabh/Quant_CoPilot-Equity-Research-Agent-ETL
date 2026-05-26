"""
sh_loader.py  –  Shareholding Pattern Loader  (v2 – fixed)
============================================================
Fixes vs v1
-----------
1.  "FIIs" / "DIIs" label variants (trailing 's') added to PARENT_LABEL_MAP
    — these are the exact labels Screener emits for most companies, causing
      fii_pct / dii_pct to be silently NULL in v1.
2.  "No. of Shareholders" now written to `num_shareholders` column.
3.  `total_institutional_pct` computed as fii_pct + dii_pct and persisted.
4.  _upsert_shareholding rewritten to write ALL schema columns in one shot
    (num_shareholders and total_institutional_pct were excluded in v1).
5.  Missing-value report now correctly detects absent FII/DII using the
    full alias set instead of a single canonical label.

Dependencies:  pip install mysql-connector-python
"""

import math
import json
import mysql.connector
from datetime import datetime, date, timedelta
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# Value sanitisers
# ─────────────────────────────────────────────────────────────────

def _clean_pct(v) -> Optional[float]:
    """
    '71.64%' → 71.64,  '0.00%' → 0.0,  None / bad → None.
    Strips the '%' sign so both '71.64%' and '71.64' are handled.
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


def _clean_int(v) -> Optional[int]:
    """'1,291,771' → 1291771,  None / bad → None."""
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────
# Screener label  →  shareholding column mapping
#
# FIX 1: Added "FIIs" and "DIIs" — these are the exact strings
#         Screener emits on the shareholding table for most Indian
#         companies (HAL, TCS, INFY, …).  v1 only had "FII"/"DII"
#         which caused fii_pct / dii_pct to always be NULL.
# ─────────────────────────────────────────────────────────────────

PARENT_LABEL_MAP: dict[str, str] = {
    # Promoters
    "Promoters":                         "promoter_pct",
    "Promoter":                          "promoter_pct",
    "Promoter & Promoter Group":         "promoter_pct",
    # FII variants
    "FII":                               "fii_pct",
    "FIIs":                              "fii_pct",          # ← FIX 1
    "Foreign Institutions":              "fii_pct",
    "Foreign Institutional Investors":   "fii_pct",
    "Foreign Portfolio Investors":       "fii_pct",
    # DII variants
    "DII":                               "dii_pct",
    "DIIs":                              "dii_pct",          # ← FIX 1
    "Domestic Institutions":             "dii_pct",
    "Domestic Institutional Investors":  "dii_pct",
    # Government
    "Government":                        "government_pct",
    # Public / Retail
    "Public":                            "public_pct",
    "Non-Institutions":                  "public_pct",
    "Retail & Others":                   "public_pct",
    # Others
    "Others":                            "others_pct",
    "Other":                             "others_pct",
}

# The 4 columns we track completeness against
PCT_COLS = ["promoter_pct", "fii_pct", "dii_pct", "public_pct"]

# Canonical label used in the missing-value report when a col is absent
# Maps col_name → list of all aliases that could fill it
_COL_ALIASES: dict[str, list] = {}
for _lbl, _col in PARENT_LABEL_MAP.items():
    _COL_ALIASES.setdefault(_col, []).append(_lbl)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def parse_quarter_end(raw: str) -> Optional[date]:
    """
    Shareholding headers: 'Jun 2023', 'Sep-23', 'Mar 2024'
    Returns last calendar day of that month.
    """
    raw = raw.strip()
    if raw.upper() in ("", "-"):
        return None
    for fmt in ("%b %Y", "%b-%y", "%b-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            # last day of the same month
            if dt.month == 12:
                last = date(dt.year + 1, 1, 1) - timedelta(days=1)
            else:
                last = date(dt.year, dt.month + 1, 1) - timedelta(days=1)
            return last
        except ValueError:
            continue
    print(f"  [WARN] Cannot parse shareholding date header: '{raw}' — skipping")
    return None


# ─────────────────────────────────────────────────────────────────
# Upsert  (FIX 4: writes all schema columns in one statement)
# ─────────────────────────────────────────────────────────────────

# All columns that go into the INSERT (must match shareholding schema exactly)
# Note: shareholding has no completeness_pct / missing_fields_json columns
_ALL_DATA_COLS = [
    "promoter_pct", "fii_pct", "dii_pct", "public_pct",
    "government_pct", "others_pct",
    "total_institutional_pct",   # FIX 3
    "num_shareholders",          # FIX 2
    "data_source",
]


def _upsert_shareholding(cursor, symbol: str, period_end: date,
                         col_values: dict, data_source: str):
    """
    Upsert one row into `shareholding`.
    col_values must contain keys matching _ALL_DATA_COLS (except data_source).
    """
    cols_no_src = [c for c in _ALL_DATA_COLS if c != "data_source"]
    set_clauses  = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in cols_no_src)
    placeholders = ", ".join(["%s"] * len(_ALL_DATA_COLS))
    col_names    = ", ".join(f"`{c}`" for c in _ALL_DATA_COLS)
    values       = [col_values.get(c) for c in cols_no_src] + [data_source]

    sql = f"""
        INSERT INTO shareholding
            (`symbol`, `period_end`, {col_names})
        VALUES (%s, %s, {placeholders})
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            `data_source` = VALUES(`data_source`),
            `updated_at`  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql, [symbol, period_end] + values)


# ─────────────────────────────────────────────────────────────────
# Missing-value report  (FIX 5: uses full alias set for detection)
# ─────────────────────────────────────────────────────────────────

def print_missing_report(symbol: str, dates: list, rows: dict):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Shareholding  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False

    # Check per-cell NULLs for columns we care about
    for col_name in PCT_COLS:
        aliases = _COL_ALIASES.get(col_name, [])
        matched_label = next((a for a in aliases if a in rows), None)
        if matched_label is None:
            # No alias found on the page at all
            print(f"  [ROW]  '{col_name}' — not present on Screener page")
            any_missing = True
            continue
        for i, v in enumerate(rows[matched_label]):
            if v is None:
                period = dates[i] if i < len(dates) else f"col-{i}"
                print(f"  [ROW]  '{matched_label}' · {period} — NULL (Screener did not provide)")
                any_missing = True

    if not any_missing:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────
# Master load function
# ─────────────────────────────────────────────────────────────────

def load_shareholding(db_config: dict, symbol: str,
                      dates: list, shareholding_rows: dict):
    """
    Parameters
    ----------
    db_config          : mysql.connector connect kwargs
    symbol             : e.g. 'HAL'
    dates              : list of quarter-header strings from scraper
    shareholding_rows  : {screener_label: [val, …]}
    """
    print(f"\n[SH LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    # Ensure parent stock row exists
    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )

    inserted = 0

    for col_idx, raw_date in enumerate(dates):
        period_end = parse_quarter_end(raw_date)
        if period_end is None:
            print(f"  [SKIP] '{raw_date}' unparseable — skipping")
            continue

        # ── Build col_values dict ──────────────────────────────
        col_values: dict = {}

        # Map every scraped label → its column (first match wins per col)
        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if col_name in col_values:
                continue                       # already filled by an earlier alias
            if screener_label not in shareholding_rows:
                continue
            vals = shareholding_rows[screener_label]
            raw  = vals[col_idx] if col_idx < len(vals) else None
            col_values[col_name] = _clean_pct(raw)

        # FIX 2: num_shareholders
        for lbl in ("No. of Shareholders", "No of Shareholders",
                    "Number of Shareholders"):
            if lbl in shareholding_rows:
                vals = shareholding_rows[lbl]
                raw  = vals[col_idx] if col_idx < len(vals) else None
                col_values["num_shareholders"] = _clean_int(raw)
                break
        else:
            col_values.setdefault("num_shareholders", None)

        # FIX 3: total_institutional_pct = fii_pct + dii_pct
        fii = col_values.get("fii_pct")
        dii = col_values.get("dii_pct")
        if fii is not None and dii is not None:
            col_values["total_institutional_pct"] = round(fii + dii, 4)
        else:
            col_values["total_institutional_pct"] = None

        _upsert_shareholding(cursor, symbol, period_end, col_values, "screener")
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[SH LOADER] ✓ Upserted {inserted} rows for {symbol}")
    print_missing_report(symbol, dates, shareholding_rows)