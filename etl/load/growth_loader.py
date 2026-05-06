"""
etl/load/growth_loader.py  v5.3
────────────────────────────────────────────────────────────
Always writes ONE row per (symbol, as_of_date).
Schema matches the exact growth_metrics table (no JSON blobs).
────────────────────────────────────────────────────────────
"""

from datetime import date
from database.db import get_connection

_ALL_FIELDS = [
    "revenue_cagr_3y", "net_profit_cagr_3y", "ebitda_cagr_3y",
    "eps_cagr_3y", "fcf_cagr_3y",
    "sales_cagr_10y", "sales_cagr_5y", "sales_cagr_3y", "sales_ttm",
    "profit_cagr_10y", "profit_cagr_5y", "profit_cagr_3y", "profit_ttm",
    "stock_cagr_10y", "stock_cagr_5y", "stock_cagr_3y", "stock_ttm",
    "roe_10y", "roe_5y", "roe_3y", "roe_last",
    "growth_available",
]


def _completeness(data: dict) -> float:
    filled = sum(1 for f in _ALL_FIELDS if data.get(f) is not None)
    return round(filled / len(_ALL_FIELDS) * 100, 1)


def load_growth_metrics(data: dict, symbol: str):
    conn = get_connection()
    today = data.get("as_of_date", date.today().isoformat())

    # One‑time drop of old JSON columns (idempotent)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(growth_metrics)").fetchall()]
    json_cols = {"revenue_yoy_json", "net_income_yoy_json", "ebitda_yoy_json",
                 "fcf_yoy_json", "gross_margin_trend_json"}
    if any(c in cols for c in json_cols):
        keep = [c for c in cols if c not in json_cols]
        keep_str = ", ".join(keep)
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS growth_metrics_new AS
                SELECT {keep_str} FROM growth_metrics;
            DROP TABLE growth_metrics;
            ALTER TABLE growth_metrics_new RENAME TO growth_metrics;
        """)
        conn.commit()
        print("  info  growth_metrics: dropped JSON columns")

    comp = _completeness(data)

    conn.execute("""
        INSERT INTO growth_metrics (
            symbol, as_of_date,
            revenue_cagr_3y, net_profit_cagr_3y, ebitda_cagr_3y,
            eps_cagr_3y, fcf_cagr_3y,
            sales_cagr_10y, sales_cagr_5y, sales_cagr_3y, sales_ttm,
            profit_cagr_10y, profit_cagr_5y, profit_cagr_3y, profit_ttm,
            stock_cagr_10y, stock_cagr_5y, stock_cagr_3y, stock_ttm,
            roe_10y, roe_5y, roe_3y, roe_last,
            growth_available, completeness_pct
        ) VALUES (
            ?,?,
            ?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,
            ?,?
        )
        ON CONFLICT(symbol, as_of_date) DO UPDATE SET
            revenue_cagr_3y     = COALESCE(excluded.revenue_cagr_3y,    revenue_cagr_3y),
            net_profit_cagr_3y  = COALESCE(excluded.net_profit_cagr_3y, net_profit_cagr_3y),
            ebitda_cagr_3y      = COALESCE(excluded.ebitda_cagr_3y,     ebitda_cagr_3y),
            eps_cagr_3y         = COALESCE(excluded.eps_cagr_3y,        eps_cagr_3y),
            fcf_cagr_3y         = COALESCE(excluded.fcf_cagr_3y,        fcf_cagr_3y),
            sales_cagr_10y      = COALESCE(excluded.sales_cagr_10y,     sales_cagr_10y),
            sales_cagr_5y       = COALESCE(excluded.sales_cagr_5y,      sales_cagr_5y),
            sales_cagr_3y       = COALESCE(excluded.sales_cagr_3y,      sales_cagr_3y),
            sales_ttm           = COALESCE(excluded.sales_ttm,          sales_ttm),
            profit_cagr_10y     = COALESCE(excluded.profit_cagr_10y,    profit_cagr_10y),
            profit_cagr_5y      = COALESCE(excluded.profit_cagr_5y,     profit_cagr_5y),
            profit_cagr_3y      = COALESCE(excluded.profit_cagr_3y,     profit_cagr_3y),
            profit_ttm          = COALESCE(excluded.profit_ttm,         profit_ttm),
            stock_cagr_10y      = COALESCE(excluded.stock_cagr_10y,     stock_cagr_10y),
            stock_cagr_5y       = COALESCE(excluded.stock_cagr_5y,      stock_cagr_5y),
            stock_cagr_3y       = COALESCE(excluded.stock_cagr_3y,      stock_cagr_3y),
            stock_ttm           = COALESCE(excluded.stock_ttm,          stock_ttm),
            roe_10y             = COALESCE(excluded.roe_10y,            roe_10y),
            roe_5y              = COALESCE(excluded.roe_5y,             roe_5y),
            roe_3y              = COALESCE(excluded.roe_3y,             roe_3y),
            roe_last            = COALESCE(excluded.roe_last,           roe_last),
            growth_available    = COALESCE(excluded.growth_available,   growth_available),
            completeness_pct    = excluded.completeness_pct
    """, (
        symbol, today,
        data.get("revenue_cagr_3y"),
        data.get("net_profit_cagr_3y"),
        data.get("ebitda_cagr_3y"),
        data.get("eps_cagr_3y"),
        data.get("fcf_cagr_3y"),
        data.get("sales_cagr_10y"),
        data.get("sales_cagr_5y"),
        data.get("sales_cagr_3y"),
        data.get("sales_ttm"),
        data.get("profit_cagr_10y"),
        data.get("profit_cagr_5y"),
        data.get("profit_cagr_3y"),
        data.get("profit_ttm"),
        data.get("stock_cagr_10y"),
        data.get("stock_cagr_5y"),
        data.get("stock_cagr_3y"),
        data.get("stock_ttm"),
        data.get("roe_10y"),
        data.get("roe_5y"),
        data.get("roe_3y"),
        data.get("roe_last"),
        data.get("growth_available", 1),
        comp,
    ))
    conn.commit()
    conn.close()
    print(f"  ok  growth_metrics: {symbol} | completeness {comp}%")