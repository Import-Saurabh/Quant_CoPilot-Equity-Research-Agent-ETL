"""
etl/load/price_loader_mysql.py  v1.0
────────────────────────────────────────────────────────────────
MySQL port of price_loader.py.

Schema tables targeted (mysql_schema_v2.sql):
  • price_daily    UNIQUE (symbol, date)
                   FK → stocks(symbol)

Key differences vs SQLite loader:
  • INSERT OR IGNORE  →  INSERT IGNORE INTO  (MySQL syntax)
  • Paramstyle: %s  not  ?
  • source column exists in MySQL schema (DEFAULT 'yfinance') — not in
    SQLite schema; included here with default value so it is populated.
  • volume column type is BIGINT in MySQL — _safe_int already returns
    Python int, compatible with mysql-connector.
  • Batch insert with executemany() for performance.
────────────────────────────────────────────────────────────────
"""

import math
import pandas as pd
import mysql.connector


# ─────────────────────────────────────────────────────────────
#  Type helpers  (identical logic to SQLite version)
# ─────────────────────────────────────────────────────────────

def _safe_float(v, dp: int = 4) -> float | None:
    try:
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return round(fv, dp)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    try:
        fv = float(v)
        if math.isnan(fv):
            return None
        return int(fv)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────
#  Loader
# ─────────────────────────────────────────────────────────────

def load_price(db_config: dict, df: pd.DataFrame, symbol: str,
               source: str = "yfinance"):
    """
    Batch-insert daily OHLCV + adj_close into price_daily.

    Schema columns:
        symbol, date, open, high, low, close, adj_close, volume, source
        (id + updated_at auto-managed)

    INSERT IGNORE safely handles re-runs — UNIQUE KEY uq_price_daily
    (symbol, date) prevents duplicates without raising an error.

    Parameters
    ----------
    db_config : dict   mysql-connector connect kwargs
    df        : DataFrame  must have columns: date, open, high, low,
                           close, adj_close, volume  (case-sensitive or
                           lowered upstream)
    symbol    : str    ticker symbol — must already exist in stocks table
                       (FK constraint)
    source    : str    data source tag (default 'yfinance')
    """
    if df is None or df.empty:
        print(f"  ⚠  price_daily [{symbol}]: empty dataframe — skipping")
        return

    rows = []
    for _, row in df.iterrows():
        rows.append((
            symbol,
            str(row.get("date"))[:10],          # 'YYYY-MM-DD'
            _safe_float(row.get("open")),
            _safe_float(row.get("high")),
            _safe_float(row.get("low")),
            _safe_float(row.get("close")),
            _safe_float(row.get("adj_close")),
            _safe_int(row.get("volume")),
            source,
        ))

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT IGNORE INTO price_daily
            (symbol, date, open, high, low, close, adj_close, volume, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ price_daily: {len(rows)} rows processed for {symbol}")