"""
ca_loader.py  –  Corporate Actions Loader
==========================================
Upserts rows into the `corporate_actions` table.
Handles dividends and splits fetched by corporate_actions.py,
plus any future action_type passed in via the generic interface.

Schema target
─────────────
corporate_actions (
    symbol       VARCHAR(30)       FK → stocks.symbol
    action_date  DATE              NOT NULL
    action_type  VARCHAR(50)       NOT NULL  e.g. 'dividend', 'split'
    value        DECIMAL(14,4)
    notes        TEXT
    UNIQUE KEY uq_ca (symbol, action_date, action_type)
)

Dependencies:  pip install mysql-connector-python
"""

import math
import mysql.connector
from datetime import date
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Value sanitiser
# ─────────────────────────────────────────────────────────────────────────────
def _clean_value(v) -> Optional[float]:
    """Numeric / string → float; None / NaN / Inf → None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DB connection
# ─────────────────────────────────────────────────────────────────────────────
def get_connection(db_config: dict) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**db_config)


# ─────────────────────────────────────────────────────────────────────────────
# Upsert
# ─────────────────────────────────────────────────────────────────────────────
def _upsert_action(
    cursor,
    symbol: str,
    action_date: date,
    action_type: str,
    value: Optional[float],
    notes: Optional[str],
):
    """
    INSERT … ON DUPLICATE KEY UPDATE so re-running the pipeline is safe.
    The unique key on (symbol, action_date, action_type) prevents duplicates.
    """
    sql = """
        INSERT INTO corporate_actions
            (symbol, action_date, action_type, value, notes)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            value = VALUES(value),
            notes = VALUES(notes)
    """
    cursor.execute(sql, [symbol, action_date, action_type, value, notes])


# ─────────────────────────────────────────────────────────────────────────────
# Missing-value report
# ─────────────────────────────────────────────────────────────────────────────
def _print_missing_report(symbol: str, records: list[dict]):
    print(f"\n{'─'*60}")
    print(f"  MISSING VALUE REPORT  ·  Corporate Actions  ·  {symbol}")
    print(f"{'─'*60}")
    any_missing = False
    for rec in records:
        if rec.get("value") is None:
            print(
                f"  [WARN]  {rec['action_type']:<12}  {rec['action_date']}  "
                f"— value is NULL"
            )
            any_missing = True
    if not any_missing:
        print("  ✓  No missing values detected.")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Master load function
# ─────────────────────────────────────────────────────────────────────────────
def load_corporate_actions(
    db_config: dict,
    symbol: str,
    actions: dict,
):
    """
    Parameters
    ----------
    db_config : mysql.connector connect kwargs
    symbol    : clean NSE ticker, e.g. 'HDFCBANK'
    actions   : dict returned by fetch_corporate_actions()
                {
                  'dividends': pd.DataFrame(columns=['date','value']),
                  'splits':    pd.DataFrame(columns=['date','value']),
                  ...any future action_type key...
                }
    """
    print(f"\n[CA LOADER] Connecting to MySQL …")
    conn   = get_connection(db_config)
    cursor = conn.cursor()

    # Ensure the symbol exists in the stocks master table
    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,),
    )

    inserted   = 0
    all_records: list[dict] = []   # collected for the missing-value report

    for action_type, df in actions.items():
        if df is None or (hasattr(df, "empty") and df.empty):
            print(f"  [SKIP] No data for action_type='{action_type}'")
            continue

        # Build human-readable notes per action type
        def _notes(action_type: str, value: Optional[float]) -> Optional[str]:
            if action_type == "dividend" and value is not None:
                return f"Dividend ₹{value:.4f} per share"
            if action_type == "split" and value is not None:
                return f"Stock split ratio {value:.4f}"
            return None

        for _, row in df.iterrows():
            action_date: date = row["date"]
            raw_value         = row["value"]
            clean_val         = _clean_value(raw_value)
            notes             = _notes(action_type, clean_val)

            _upsert_action(cursor, symbol, action_date, action_type,
                           clean_val, notes)
            inserted += 1

            all_records.append({
                "action_type": action_type,
                "action_date": action_date,
                "value":       clean_val,
            })

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[CA LOADER] ✓ Upserted {inserted} corporate action rows for {symbol}")
    _print_missing_report(symbol, all_records)