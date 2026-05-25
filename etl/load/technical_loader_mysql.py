"""
etl/load/technical_loader_mysql.py  v1.0
────────────────────────────────────────────────────────────────
MySQL port of technical_loader.py (load_technicals only).
compute_technicals() is database-agnostic — import it directly
from technical_loader.py; it is not duplicated here.

Schema table targeted (mysql_schema_v2.sql):
  • technical_indicators
    UNIQUE KEY uq_ti (symbol, date)
    FK → stocks(symbol)

    Columns:
      symbol, date, close,
      rsi_14, macd, macd_signal, macd_hist,
      sma_50, sma_200, ema_21,
      bb_mid, bb_upper, bb_lower,
      atr_14, adx_14, vwap_14, obv,
      supertrend, supertrend_dir

    All indicator columns already present in mysql_schema_v2 —
    the SQLite migration ALTERs in technical_loader.py are NOT
    needed here.

Key differences vs SQLite loader:
  • INSERT OR REPLACE  →  INSERT … ON DUPLICATE KEY UPDATE
    (same reason as earnings_loader_mysql: avoids PK DELETE+re-INSERT)
  • Paramstyle: %s  not  ?
  • No ALTER TABLE migrations — schema already has all columns.
  • obv is DECIMAL(18,2) in MySQL — float value is compatible.
  • supertrend_dir is TINYINT — Python int from _safe() after int() cast.
  • Batch insert via executemany() for performance.
────────────────────────────────────────────────────────────────
"""

import math
import pandas as pd
from database.db_mysql import get_connection as _get_conn


# ─────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────

def _safe(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def _safe_tinyint(v) -> int | None:
    """Cast supertrend_dir (+1/-1) to plain Python int for TINYINT column."""
    f = _safe(v)
    return int(f) if f is not None else None


# ─────────────────────────────────────────────────────────────
#  Loader
# ─────────────────────────────────────────────────────────────

def load_technicals(db_config: dict, df: pd.DataFrame, symbol: str):
    """
    Batch-upsert technical indicators into technical_indicators.

    Expects df produced by compute_technicals() from technical_loader.py:
        date, close,
        rsi_14, macd, macd_signal, macd_hist,
        sma_50, sma_200, ema_21,
        bb_mid, bb_upper, bb_lower,
        atr_14, adx_14, vwap_14, obv,
        supertrend, supertrend_dir

    Warmup rows where close IS NULL are skipped (same as SQLite version).
    All schema columns are present in mysql_schema_v2 — no ALTER needed.

    Parameters
    ----------
    db_config : dict   mysql-connector connect kwargs
    df        : DataFrame  output of compute_technicals()
    symbol    : str    must already exist in stocks table (FK)
    """
    if df is None or df.empty:
        print(f"  ⚠  technical_indicators [{symbol}]: empty DataFrame — skipping")
        return

    rows = []
    for _, row in df.iterrows():
        close_val = _safe(row.get("close"))
        if close_val is None:       # skip warmup / bad rows
            continue

        def g(col: str):
            return _safe(row.get(col))

        rows.append((
            symbol,
            str(row["date"])[:10],  # 'YYYY-MM-DD'
            close_val,
            g("rsi_14"),
            g("macd"),
            g("macd_signal"),
            g("macd_hist"),
            g("sma_50"),
            g("sma_200"),
            g("ema_21"),
            g("bb_mid"),
            g("bb_upper"),
            g("bb_lower"),
            g("atr_14"),
            g("adx_14"),
            g("vwap_14"),
            g("obv"),
            g("supertrend"),
            _safe_tinyint(row.get("supertrend_dir")),  # TINYINT column
        ))

    if not rows:
        print(f"  ⚠  technical_indicators [{symbol}]: no valid rows after filtering")
        return

    conn   = _get_conn()
    cursor = conn.cursor()

    # Ensure symbol exists in stocks table (FK guard)
    cursor.execute(
        "INSERT IGNORE INTO stocks (symbol, exchange) VALUES (%s, 'NSE')",
        (symbol,)
    )
    conn.commit()

    cursor.executemany("""
        INSERT INTO technical_indicators
            (symbol, date, close,
             rsi_14, macd, macd_signal, macd_hist,
             sma_50, sma_200, ema_21,
             bb_mid, bb_upper, bb_lower,
             atr_14, adx_14, vwap_14, obv,
             supertrend, supertrend_dir)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            close           = new.close,
            rsi_14          = new.rsi_14,
            macd            = new.macd,
            macd_signal     = new.macd_signal,
            macd_hist       = new.macd_hist,
            sma_50          = new.sma_50,
            sma_200         = new.sma_200,
            ema_21          = new.ema_21,
            bb_mid          = new.bb_mid,
            bb_upper        = new.bb_upper,
            bb_lower        = new.bb_lower,
            atr_14          = new.atr_14,
            adx_14          = new.adx_14,
            vwap_14         = new.vwap_14,
            obv             = new.obv,
            supertrend      = new.supertrend,
            supertrend_dir  = new.supertrend_dir
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()

    null_sma50 = sum(1 for r in rows if r[7] is None)
    print(
        f"  ✅ technical_indicators: {len(rows)} rows upserted for {symbol}"
        f"  (warmup NULLs in sma_50: {null_sma50})"
    )