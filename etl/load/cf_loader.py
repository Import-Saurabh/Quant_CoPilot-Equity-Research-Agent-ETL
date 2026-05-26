"""
cf_loader.py  –  Cash Flow Loader  (v2 – fixed)
=================================================
Fixes vs v1
-----------
1.  completeness_pct and missing_fields_json now computed and written
    for every parent row — schema had these columns but v1 never wrote them.
2.  capex extraction fixed: Screener surfaces it as "Free Cash Flow" minus
    "Cash from Operating Activity" only when a dedicated "Capital Expenditure"
    row is absent.  We now also look for the child item
    "Fixed assets purchased" inside the operating/investing schedule and
    store it as capex when the top-level label is absent.
3.  Child missing-value report no longer flags dict sentinel values
    (e.g. {'class': 'strong'}) as genuine NULLs — they are structural
    Screener artefacts, not missing data.
4.  _upsert_parent now includes completeness_pct and missing_fields_json
    in the ON DUPLICATE KEY UPDATE clause so re-runs always refresh them.
5.  Period-date parser is stricter: ISO dates (YYYY-MM-DD) are parsed
    directly without converting to "last day of month" arithmetic.

Dependencies:  pip install mysql-connector-python
"""

import json
import math
import mysql.connector
from datetime import datetime, date, timedelta
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# Value sanitisers
# ─────────────────────────────────────────────────────────────────

def _clean_value(v) -> Optional[float]:
    """
    Comma-str '5,143' → 5143.0
    Dict sentinel {'class': 'strong'} → None  (Screener artefact)
    None / blank / bad → None
    """
    if v is None:
        return None
    if isinstance(v, dict):          # ← FIX 3: structural sentinel, not real data
        return None
    try:
        f = float(str(v).replace(",", "").strip())
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _clean_pct(v) -> Optional[float]:
    """'20%' → 20.0; None / bad → None."""
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


def _is_sentinel(v) -> bool:
    """Returns True for Screener structural artefacts that are not real NULLs."""
    if isinstance(v, dict):
        return True
    if v is None:
        return False
    s = str(v).strip()
    return s == ""


# ─────────────────────────────────────────────────────────────────
# Screener label  →  cash_flow column mapping
# ─────────────────────────────────────────────────────────────────

PARENT_LABEL_MAP: dict[str, str] = {
    "Cash from Operating Activity":   "cfo",
    "Cash from Operating Activities": "cfo",
    "Cash from Investing Activity":   "cfi",
    "Cash from Investing Activities": "cfi",
    "Cash from Financing Activity":   "cff",
    "Cash from Financing Activities": "cff",
    # Capex: only present as a top-level row for some companies
    "Capital Expenditure":            "capex",
    "Capex":                          "capex",
    "Free Cash Flow":                 "free_cash_flow",
    "Net Cash Flow":                  "net_cash_flow",
}

# Columns we require to call a row "complete"
UNIVERSAL_COLS = ["cfo", "cfi", "cff"]

# Schedule parent labels used by the scraper
SCHEDULE_PARENTS = [
    "Cash from Operating Activity",
    "Cash from Investing Activity",
    "Cash from Financing Activity",
]

# Child item labels we can use to back-fill capex when no top-level row exists
_CAPEX_CHILD_LABELS = {"Fixed assets purchased", "Capital expenditure",
                       "Purchase of fixed assets", "Purchase of PPE"}


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


def parse_period_end(raw: str) -> Optional[date]:
    """
    Accepts:
        'Mar 2025'  → 2025-03-31
        'Mar-25'    → 2025-03-31
        '2025-03-31'→ 2025-03-31  (FIX 5: pass-through without re-arithmetic)
    """
    raw = raw.strip()
    if raw.upper() in ("TTM", ""):
        return None
    # ISO date — use directly (FIX 5)
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    for fmt in ("%b %Y", "%b-%y", "%b-%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.month == 12:
                return date(dt.year + 1, 1, 1) - timedelta(days=1)
            else:
                return date(dt.year, dt.month + 1, 1) - timedelta(days=1)
        except ValueError:
            continue
    print(f"  [WARN] Cannot parse Cash Flow date header: '{raw}' — skipping")
    return None


def _period_type(raw: str) -> str:
    return "ttm" if raw.strip().upper() == "TTM" else "annual"


# ─────────────────────────────────────────────────────────────────
# Completeness helpers  (FIX 1)
# ─────────────────────────────────────────────────────────────────

def _compute_completeness(col_values: dict) -> tuple[float, str]:
    """
    Returns (completeness_pct, missing_fields_json_str).
    Tracks UNIVERSAL_COLS only for the pct score.
    """
    missing = [c for c in UNIVERSAL_COLS if col_values.get(c) is None]
    pct     = round((len(UNIVERSAL_COLS) - len(missing)) / len(UNIVERSAL_COLS) * 100, 2)
    return pct, json.dumps(missing) if missing else json.dumps([])


# ─────────────────────────────────────────────────────────────────
# Capex back-fill from child items  (FIX 2)
# ─────────────────────────────────────────────────────────────────

def _extract_capex_from_children(child_items: dict, col_idx: int) -> Optional[float]:
    """
    Look inside investing-activity child rows for a capex-equivalent item.
    Screener usually reports it as a negative number; we store absolute value.
    """
    investing_rows = child_items.get("Cash from Investing Activity", {})
    for label, vals in investing_rows.items():
        if label in _CAPEX_CHILD_LABELS:
            raw = vals[col_idx] if col_idx < len(vals) else None
            v   = _clean_value(raw)
            if v is not None:
                return abs(v)      # capex is conventionally positive
    return None


# ─────────────────────────────────────────────────────────────────
# Upserts  (FIX 1 + FIX 4)
# ─────────────────────────────────────────────────────────────────

# All data columns in the cash_flow table (excluding id, symbol, period_end,
# period_type, is_consolidated, updated_at which are handled separately)
_PARENT_DATA_COLS = [
    "cfo", "cfi", "cff", "capex", "free_cash_flow", "net_cash_flow",
    "completeness_pct", "missing_fields_json",   # FIX 1
    "data_source",
]


def _upsert_parent(cursor, symbol: str, period_end: date,
                   period_type: str, is_consolidated: int,
                   col_values: dict, data_source: str):
    cols_no_src = [c for c in _PARENT_DATA_COLS if c != "data_source"]
    set_clauses  = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in cols_no_src)
    placeholders = ", ".join(["%s"] * len(_PARENT_DATA_COLS))
    col_names    = ", ".join(f"`{c}`" for c in _PARENT_DATA_COLS)
    values       = [col_values.get(c) for c in cols_no_src] + [data_source]

    sql = f"""
        INSERT INTO cash_flow
            (`symbol`, `period_end`, `period_type`, `is_consolidated`,
             {col_names})
        VALUES (%s, %s, %s, %s, {placeholders})
        ON DUPLICATE KEY UPDATE
            {set_clauses},
            `data_source` = VALUES(`data_source`),
            `updated_at`  = CURRENT_TIMESTAMP
    """
    cursor.execute(sql,
        [symbol, period_end, period_type, is_consolidated] + values)


def _upsert_item(cursor, symbol: str, period_end: date,
                 period_type: str, is_consolidated: int,
                 parent_label: str, item_label: str,
                 value: Optional[float], sort_order: int, data_source: str):
    sql = """
        INSERT INTO cash_flow_items
            (`symbol`, `period_end`, `period_type`, `is_consolidated`,
             `parent_label`, `item_label`, `value`, `sort_order`, `data_source`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            `value`       = VALUES(`value`),
            `sort_order`  = VALUES(`sort_order`),
            `data_source` = VALUES(`data_source`)
    """
    cursor.execute(sql, [
        symbol, period_end, period_type, is_consolidated,
        parent_label[:100], item_label[:100],
        value, sort_order, data_source,
    ])


# ─────────────────────────────────────────────────────────────────
# Missing-value report  (FIX 3: skip dict sentinels)
# ─────────────────────────────────────────────────────────────────

def print_missing_report(symbol: str, dates: list,
                         main_rows: dict, child_items: dict):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Cash Flow  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False

    # Parent-level checks (UNIVERSAL_COLS only)
    for screener_label, col_name in PARENT_LABEL_MAP.items():
        if col_name not in UNIVERSAL_COLS:
            continue
        if screener_label not in main_rows:
            continue
        for i, v in enumerate(main_rows[screener_label]):
            if v is None and not _is_sentinel(v):
                # v is genuinely None (not a dict sentinel), flag it
                period = dates[i] if i < len(dates) else f"col-{i}"
                print(f"  [PARENT]  '{screener_label}' · {period} "
                      f"— NULL (Screener did not provide)")
                any_missing = True

    # Child-level checks — skip sentinels (FIX 3)
    for parent_label, rows in child_items.items():
        for child_label, vals in rows.items():
            for i, v in enumerate(vals):
                if v is None and not _is_sentinel(v):
                    period = dates[i] if i < len(dates) else f"col-{i}"
                    print(f"  [CHILD]   '{parent_label}' → '{child_label}' "
                          f"· {period} — NULL (Screener did not provide)")
                    any_missing = True

    if not any_missing:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────
# Master load function
# ─────────────────────────────────────────────────────────────────

def load_cash_flow(db_config: dict, symbol: str,
                   dates: list, main_rows: dict,
                   child_items: dict, is_consolidated: int = 1):
    """
    Parameters
    ----------
    db_config      : mysql.connector connect kwargs
    symbol         : e.g. 'HAL'
    dates          : list of period-header strings from scraper
    main_rows      : {screener_label: [val, …]}
    child_items    : {parent_label: {child_label: [val, …]}}
    is_consolidated: 1 or 0
    """
    print(f"\n[CF LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    inserted_parent = 0
    inserted_child  = 0

    # Ensure parent stock row exists
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
        if period_end is None:
            period_end = date.today()

        # ── Build col_values ───────────────────────────────────
        col_values: dict = {}

        PCT_ONLY = set()    # no ratio cols in current schema

        for screener_label, col_name in PARENT_LABEL_MAP.items():
            if col_name in col_values:
                continue   # first match per column wins
            if screener_label not in main_rows:
                continue
            vals = main_rows[screener_label]
            raw  = vals[col_idx] if col_idx < len(vals) else None
            col_values[col_name] = (
                _clean_pct(raw) if col_name in PCT_ONLY else _clean_value(raw)
            )

        # FIX 2: back-fill capex from child items when absent as top-level row
        if col_values.get("capex") is None:
            capex_from_child = _extract_capex_from_children(child_items, col_idx)
            if capex_from_child is not None:
                col_values["capex"] = capex_from_child

        # FIX 1: compute completeness
        completeness_pct, missing_json = _compute_completeness(col_values)
        col_values["completeness_pct"]   = completeness_pct
        col_values["missing_fields_json"] = missing_json

        _upsert_parent(cursor, symbol, period_end, ptype,
                       is_consolidated, col_values, "screener")
        inserted_parent += 1

        # ── Child items ────────────────────────────────────────
        for parent_label, rows in child_items.items():
            for sort_idx, (child_label, vals) in enumerate(rows.items()):
                raw   = vals[col_idx] if col_idx < len(vals) else None
                value = _clean_value(raw)   # dict sentinels → None automatically
                _upsert_item(cursor, symbol, period_end, ptype,
                             is_consolidated, parent_label, child_label,
                             value, sort_idx, "screener")
                inserted_child += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[CF LOADER] ✓ Upserted {inserted_parent} parent rows, "
          f"{inserted_child} child rows for {symbol}")

    print_missing_report(symbol, dates, main_rows, child_items)