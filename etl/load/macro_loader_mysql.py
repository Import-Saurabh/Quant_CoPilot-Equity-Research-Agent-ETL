"""
etl/load/macro_loader_mysql.py  v1.0
────────────────────────────────────────────────────────────────
MySQL port of macro_loader.py.

Schema tables targeted (mysql_schema_v2.sql):
  • market_indices      UNIQUE (snapshot_date, index_name)
  • forex_commodities   UNIQUE (snapshot_date, instrument)
  • rbi_rates           UNIQUE (effective_date)
  • macro_indicators    UNIQUE (snapshot_date, indicator_name, year_key)
                          year_key is a GENERATED column = COALESCE(year, 0)
                          so we must NOT include it in INSERT — MySQL populates it.

Key differences vs SQLite loader:
  • Uses PyMySQL via database.db_mysql.get_connection()
  • INSERT OR IGNORE  → INSERT IGNORE INTO  (MySQL syntax)
  • Paramstyle: %s  not  ?
  • rbi_rates: is_cached column absent from schema — omitted
  • macro_indicators: year_key is GENERATED — never listed in INSERT cols
  • All connections closed via cursor.close() + conn.close()
────────────────────────────────────────────────────────────────
"""

from database.db_mysql import get_connection as _get_conn_base

def _get_conn(_db_config=None):
    """Always use db_mysql credentials — db_config arg kept for API compat."""
    return _get_conn_base()


# ─────────────────────────────────────────────────────────────
#  market_indices
# ─────────────────────────────────────────────────────────────

def load_market_indices(db_config: dict, data: dict, snapshot_date: str):
    """
    INSERT IGNORE into market_indices.
    Schema UNIQUE KEY: uq_mi (snapshot_date, index_name)
    Columns: snapshot_date, index_name, last_price, change_pct, direction
    (updated_at auto-managed by ON UPDATE CURRENT_TIMESTAMP)
    """
    indices = data.get("indices", {})
    if not indices:
        print("  ⚠  market_indices: no data")
        return

    conn   = _get_conn(db_config)
    cursor = conn.cursor()
    count  = 0

    for name, entry in indices.items():
        cursor.execute("""
            INSERT IGNORE INTO market_indices
                (snapshot_date, index_name, last_price, change_pct, direction)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            snapshot_date,
            name,
            entry.get("price"),
            entry.get("change_pct"),
            entry.get("direction"),
        ))
        count += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ market_indices: {count} rows processed for {snapshot_date}")


# ─────────────────────────────────────────────────────────────
#  forex_commodities
# ─────────────────────────────────────────────────────────────

def load_forex_commodities(db_config: dict, data: dict, snapshot_date: str):
    """
    INSERT IGNORE into forex_commodities.
    Schema UNIQUE KEY: uq_fc (snapshot_date, instrument)
    Columns: snapshot_date, instrument, last_price, change_pct
    """
    forex = data.get("forex", {})
    if not forex:
        print("  ⚠  forex_commodities: no data")
        return

    conn   = _get_conn(db_config)
    cursor = conn.cursor()
    count  = 0

    for name, entry in forex.items():
        cursor.execute("""
            INSERT IGNORE INTO forex_commodities
                (snapshot_date, instrument, last_price, change_pct)
            VALUES (%s, %s, %s, %s)
        """, (
            snapshot_date,
            name,
            entry.get("price"),
            entry.get("change_pct"),
        ))
        count += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ forex_commodities: {count} rows processed for {snapshot_date}")


# ─────────────────────────────────────────────────────────────
#  rbi_rates
# ─────────────────────────────────────────────────────────────

def load_rbi_rates(db_config: dict, data: dict):
    """
    Load RBI policy rates — skips if repo_rate is identical to the most
    recent stored row.  INSERT IGNORE guards against same-date re-runs.

    Schema UNIQUE KEY: uq_rbi (effective_date)
    Columns: effective_date, repo_rate, reverse_repo, sdf_rate,
             msf_rate, bank_rate, crr, slr, source

    NOTE: is_cached is NOT a column in mysql_schema_v2 — omitted.
    """
    if not data:
        print("  ⚠  rbi_rates: no data")
        return

    conn   = _get_conn(db_config)
    cursor = conn.cursor()

    # Skip if repo_rate unchanged since last insert
    cursor.execute(
        "SELECT repo_rate FROM rbi_rates ORDER BY id DESC LIMIT 1"
    )
    last = cursor.fetchone()
    if last and float(last[0]) == float(data.get("repo_rate", 0)):
        cursor.close()
        conn.close()
        print(f"  ⏭  rbi_rates: repo_rate unchanged ({data.get('repo_rate')}%) — skipping")
        return

    cursor.execute("""
        INSERT IGNORE INTO rbi_rates
            (effective_date, repo_rate, reverse_repo, sdf_rate,
             msf_rate, bank_rate, crr, slr, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data.get("date"),
        data.get("repo_rate"),
        data.get("reverse_repo"),
        data.get("sdf_rate"),
        data.get("msf_rate"),
        data.get("bank_rate"),
        data.get("crr"),
        data.get("slr"),
        data.get("source", ""),
    ))

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ rbi_rates: repo={data.get('repo_rate')}% saved")


# ─────────────────────────────────────────────────────────────
#  macro_indicators
# ─────────────────────────────────────────────────────────────

def load_macro_indicators(db_config: dict, records: list):
    """
    INSERT IGNORE into macro_indicators.

    Schema UNIQUE KEY: uq_macro (snapshot_date, indicator_name, year_key)
      year_key is GENERATED ALWAYS AS (COALESCE(year, 0)) STORED NOT NULL
      → it must NOT appear in the INSERT column list; MySQL computes it.

    Columns inserted: snapshot_date, indicator_name, source, value, year
    (year_key auto-computed; updated_at auto-managed by DEFAULT/ON UPDATE)
    """
    if not records:
        return

    conn   = _get_conn(db_config)
    cursor = conn.cursor()
    count  = 0

    for r in records:
        cursor.execute("""
            INSERT IGNORE INTO macro_indicators
                (snapshot_date, indicator_name, source, value, year)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            r.get("snapshot_date"),
            r.get("indicator_name"),
            r.get("source"),
            r.get("value"),
            r.get("year"),      # nullable — year_key generated from this
        ))
        count += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  ✅ macro_indicators: {count} records processed")