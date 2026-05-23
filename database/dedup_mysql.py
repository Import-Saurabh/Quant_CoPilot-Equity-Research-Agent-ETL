"""
database/dedup_mysql.py  v1.0
Deduplication for MySQL – only tables present in the provided MySQL schema.
Uses MIN(id) / MAX(id) because MySQL has no `rowid`.
"""
from database.db_mysql import get_connection

_DEDUP_CONFIG = [
    {
        "table": "rbi_rates",
        "key_cols": ["effective_date"],
        "data_cols": ["repo_rate", "reverse_repo", "crr", "slr"],
        "keep": "first",
    },
    {
        "table": "macro_indicators",
        "key_cols": ["snapshot_date", "indicator_name", "year_key"],
        "data_cols": ["value"],
        "keep": "first",
    },
    {
        "table": "market_indices",
        "key_cols": ["snapshot_date", "index_name"],
        "data_cols": ["last_price"],
        "keep": "first",
    },
    {
        "table": "forex_commodities",
        "key_cols": ["snapshot_date", "instrument"],
        "data_cols": ["last_price"],
        "keep": "first",
    },
    {
        "table": "earnings_estimates",
        "key_cols": ["symbol", "snapshot_date", "period_code"],
        "data_cols": ["avg_eps", "analyst_count"],
        "keep": "first",
    },
    {
        "table": "technical_indicators",
        "key_cols": ["symbol", "date"],
        "data_cols": ["close", "rsi_14"],
        "keep": "first",
    },
]

def _dedup_table(conn, table: str, key_cols: list, data_cols: list, keep: str = "first") -> int:
    cursor = conn.cursor()
    # Check if table exists
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
    """, (table,))
    if cursor.fetchone()["COUNT(*)"] == 0:
        return 0

    # Collect columns that actually exist
    cursor.execute(f"DESCRIBE {table}")
    existing_cols = {row["Field"] for row in cursor.fetchall()}
    all_group_cols = key_cols + data_cols
    valid_cols = [c for c in all_group_cols if c in existing_cols]
    if not valid_cols:
        return 0

    group_expr = ", ".join(f"`{c}`" for c in valid_cols)
    agg = "MIN(id)" if keep == "first" else "MAX(id)"

    sql = f"""
        DELETE FROM `{table}`
        WHERE id NOT IN (
            SELECT {agg}
            FROM `{table}`
            GROUP BY {group_expr}
        )
    """
    # MySQL does not allow direct subquery in DELETE FROM same table without a workaround
    # Use a temporary table or double subquery
    sql = f"""
        DELETE FROM `{table}`
        WHERE id NOT IN (
            SELECT * FROM (
                SELECT {agg}
                FROM `{table}`
                GROUP BY {group_expr}
            ) AS tmp
        )
    """
    cursor.execute(sql)
    conn.commit()
    return cursor.rowcount

def run_all_dedup():
    conn = get_connection()
    summary = {}
    for cfg in _DEDUP_CONFIG:
        table = cfg["table"]
        key_cols = cfg["key_cols"]
        data_cols = cfg["data_cols"]
        keep = cfg.get("keep", "first")
        try:
            deleted = _dedup_table(conn, table, key_cols, data_cols, keep)
            summary[table] = deleted
            if deleted:
                print(f"  🧹 dedup {table}: removed {deleted} duplicate rows")
        except Exception as e:
            summary[table] = f"ERROR: {e}"
            print(f"  ⚠  dedup {table}: {e}")
    conn.close()
    return summary

def run_one_time_cleanup():
    print("═" * 60)
    print("ONE-TIME DEDUP CLEANUP (MySQL)")
    print("═" * 60)
    summary = run_all_dedup()
    total = sum(v for v in summary.values() if isinstance(v, int))
    print(f"\nTotal rows removed: {total}")
    print("═" * 60)
    return summary

if __name__ == "__main__":
    run_one_time_cleanup()