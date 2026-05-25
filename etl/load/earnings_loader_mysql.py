"""
etl/load/earnings_loader_mysql.py  v1.0
────────────────────────────────────────────────────────────────
MySQL port of earnings_loader.py.

Schema tables targeted (mysql_schema_v2.sql):
  • earnings_history    UNIQUE (symbol, quarter_end)
  • earnings_estimates  UNIQUE (symbol, snapshot_date, period_code)
  • eps_trend           UNIQUE (symbol, snapshot_date, period_code)
  • eps_revisions       UNIQUE (symbol, snapshot_date, period_code)
  All have FK → stocks(symbol).

Key differences vs SQLite loader:
  • INSERT OR REPLACE  →  INSERT … ON DUPLICATE KEY UPDATE  (MySQL)
    (OR REPLACE would DELETE+INSERT and break FK child rows if any;
     ON DUPLICATE KEY UPDATE is the safe, correct MySQL upsert.)
  • Paramstyle: %s  not  ?
  • analyst_count is SMALLINT in MySQL — Python int from _to_int() is fine.
  • numpy int64 / float BLOB issue: same _to_int() / _to_float() guards
    kept — they ensure plain Python scalars reach the driver.
  • Batch inserts via executemany() for performance.

NOTE ON UPSERT PATTERN
  MySQL lacks "INSERT OR REPLACE … VALUES" as a single idempotent upsert
  when there is an AUTO_INCREMENT PK.  The safe idiom is:

      INSERT INTO t (col, ...) VALUES (%s, ...)
      AS new
      ON DUPLICATE KEY UPDATE col = new.col, ...

  This updates only the payload columns, leaves id/created_at untouched.
────────────────────────────────────────────────────────────────
"""

import math
import mysql.connector


# ─────────────────────────────────────────────────────────────
#  Type helpers
# ─────────────────────────────────────────────────────────────

def _to_int(v) -> int | None:
    """Cast any numeric (numpy int64, float, str) to plain Python int."""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────
#  earnings_history
# ─────────────────────────────────────────────────────────────

def load_earnings_history(db_config: dict, records: list, symbol: str):
    """
    Upsert into earnings_history.
    UNIQUE KEY uq_eh (symbol, quarter_end)
    Columns: symbol, quarter_end, eps_actual, eps_estimate,
             eps_difference, surprise_pct
    """
    if not records:
        return

    rows = [
        (
            symbol,
            r["quarter_end"],
            _to_float(r.get("eps_actual")),
            _to_float(r.get("eps_estimate")),
            _to_float(r.get("eps_difference")),
            _to_float(r.get("surprise_pct")),
        )
        for r in records
    ]

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT INTO earnings_history
            (symbol, quarter_end, eps_actual, eps_estimate,
             eps_difference, surprise_pct)
        VALUES (%s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            eps_actual      = new.eps_actual,
            eps_estimate    = new.eps_estimate,
            eps_difference  = new.eps_difference,
            surprise_pct    = new.surprise_pct
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ earnings_history: {len(rows)} rows upserted for {symbol}")


# ─────────────────────────────────────────────────────────────
#  earnings_estimates
# ─────────────────────────────────────────────────────────────

def load_earnings_estimates(db_config: dict, records: list, symbol: str):
    """
    Upsert into earnings_estimates.
    UNIQUE KEY uq_ee (symbol, snapshot_date, period_code)
    Columns: symbol, snapshot_date, period_code, avg_eps, low_eps,
             high_eps, year_ago_eps, analyst_count, growth_pct
    analyst_count → SMALLINT; _to_int() ensures plain Python int.
    """
    if not records:
        return

    rows = [
        (
            symbol,
            r["snapshot_date"],
            r["period_code"],
            _to_float(r.get("avg_eps")),
            _to_float(r.get("low_eps")),
            _to_float(r.get("high_eps")),
            _to_float(r.get("year_ago_eps")),
            _to_int(r.get("analyst_count")),    # SMALLINT — must be Python int
            _to_float(r.get("growth_pct")),
        )
        for r in records
    ]

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT INTO earnings_estimates
            (symbol, snapshot_date, period_code,
             avg_eps, low_eps, high_eps, year_ago_eps,
             analyst_count, growth_pct)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            avg_eps        = new.avg_eps,
            low_eps        = new.low_eps,
            high_eps       = new.high_eps,
            year_ago_eps   = new.year_ago_eps,
            analyst_count  = new.analyst_count,
            growth_pct     = new.growth_pct
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ earnings_estimates: {len(rows)} rows upserted for {symbol}")


# ─────────────────────────────────────────────────────────────
#  eps_trend
# ─────────────────────────────────────────────────────────────

def load_eps_trend(db_config: dict, records: list, symbol: str):
    """
    Upsert into eps_trend.
    UNIQUE KEY: (symbol, snapshot_date, period_code)
    Columns: symbol, snapshot_date, period_code,
             current_est, seven_days_ago, thirty_days_ago,
             sixty_days_ago, ninety_days_ago
    """
    if not records:
        return

    rows = [
        (
            symbol,
            r["snapshot_date"],
            r["period_code"],
            _to_float(r.get("current_est")),
            _to_float(r.get("seven_days_ago")),
            _to_float(r.get("thirty_days_ago")),
            _to_float(r.get("sixty_days_ago")),
            _to_float(r.get("ninety_days_ago")),
        )
        for r in records
    ]

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT INTO eps_trend
            (symbol, snapshot_date, period_code,
             current_est, seven_days_ago, thirty_days_ago,
             sixty_days_ago, ninety_days_ago)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            current_est      = new.current_est,
            seven_days_ago   = new.seven_days_ago,
            thirty_days_ago  = new.thirty_days_ago,
            sixty_days_ago   = new.sixty_days_ago,
            ninety_days_ago  = new.ninety_days_ago
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ eps_trend: {len(rows)} rows upserted for {symbol}")


# ─────────────────────────────────────────────────────────────
#  eps_revisions
# ─────────────────────────────────────────────────────────────

def load_eps_revisions(db_config: dict, records: list, symbol: str):
    """
    Upsert into eps_revisions.
    UNIQUE KEY: (symbol, snapshot_date, period_code)
    Columns: symbol, snapshot_date, period_code,
             up_last_7d, up_last_30d, down_last_30d, down_last_7d

    All revision counts stored as plain Python int via _to_int()
    to prevent numpy int64 BLOB corruption in mysql-connector.
    """
    if not records:
        return

    rows = [
        (
            symbol,
            r["snapshot_date"],
            r["period_code"],
            _to_int(r.get("up_last_7d")),
            _to_int(r.get("up_last_30d")),
            _to_int(r.get("down_last_30d")),
            _to_int(r.get("down_last_7d")),
        )
        for r in records
    ]

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT INTO eps_revisions
            (symbol, snapshot_date, period_code,
             up_last_7d, up_last_30d, down_last_30d, down_last_7d)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        AS new
        ON DUPLICATE KEY UPDATE
            up_last_7d    = new.up_last_7d,
            up_last_30d   = new.up_last_30d,
            down_last_30d = new.down_last_30d,
            down_last_7d  = new.down_last_7d
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ eps_revisions: {len(rows)} rows upserted for {symbol}")