"""
etl/load/profit_and_loss_loader.py
────────────────────────────────────────────────────────────────
Loads Screener P&L data into the `profit_and_loss` SQLite table.

Replaces: income_loader.py
  • No yfinance path — Screener is the sole source of truth.
  • Maps Screener metric names directly to DB column names.
  • Handles % strings (OPM %, Tax %) and plain numeric strings.
  • UPSERT on (symbol, period_end, period_type).
────────────────────────────────────────────────────────────────
"""

import math
import re
import pandas as pd
from database.db import get_connection

# ── Month helpers ──────────────────────────────────────────────
_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MONTH_END = {
    "01": "31", "02": "28", "03": "31", "04": "30",
    "05": "31", "06": "30", "07": "31", "08": "31",
    "09": "30", "10": "31", "11": "30", "12": "31",
}


# ── Value coercers ─────────────────────────────────────────────

def _to_float(v) -> float | None:
    """Convert any Screener cell value to float; return None on failure."""
    if v is None:
        return None
    s = str(v).replace("%", "").replace(",", "").strip()
    if s in ("", "-", "—", "N/A", "nan", "None"):
        return None
    try:
        fv = float(s)
        return None if (math.isnan(fv) or math.isinf(fv)) else round(fv, 4)
    except ValueError:
        return None


def _parse_period_end(label: str) -> str | None:
    """
    Convert Screener period label → ISO date string.

    Accepts:
      "Mar 2024"  → "2024-03-31"
      "Jun 2023"  → "2023-06-30"
      TTM / blank → None (skip)
    """
    label = str(label).strip()
    if label.upper() in ("TTM", "NAN", ""):
        return None

    m = re.match(r"([A-Za-z]{3})\s+(\d{4})", label)
    if not m:
        return None

    mon = _MONTH_MAP.get(m.group(1).lower())
    if not mon:
        return None

    year = m.group(2)
    day  = _MONTH_END[mon]
    return f"{year}-{mon}-{day}"


# ── Loader ────────────────────────────────────────────────────

def load_profit_and_loss(df: pd.DataFrame, symbol: str, period_type: str = "annual"):
    """
    Upsert rows from a Screener P&L DataFrame into `profit_and_loss`.

    Parameters
    ----------
    df          : DataFrame returned by fetch_profit_and_loss()
                  Expected columns (after rename in fetcher):
                    symbol, period_end, period_type,
                    sales, expenses, operating_profit, opm_pct,
                    other_income, interest, depreciation,
                    profit_before_tax, tax_pct, net_profit,
                    eps, dividend_payout_pct
    symbol      : NSE ticker, e.g. "ADANIPORTS"
    period_type : "annual" | "quarterly"
    """
    if df is None or df.empty:
        print(f"  ⚠  profit_and_loss ({period_type}): empty DataFrame — skipping")
        return

    conn  = get_connection()
    count = 0
    skip  = 0

    for _, row in df.iterrows():
        # Resolve period_end ──────────────────────────────────
        raw_period = row.get("period_end", "")
        period_end = _parse_period_end(str(raw_period))
        if not period_end:
            skip += 1
            continue

        # Resolve period_type (prefer column value if present) ─
        pt = str(row.get("period_type", period_type)).strip() or period_type

        def g(col):
            return _to_float(row.get(col))

        conn.execute("""
            INSERT INTO profit_and_loss (
                symbol, period_end, period_type,
                sales, expenses, operating_profit, opm_pct,
                other_income, interest, depreciation,
                profit_before_tax, tax_pct, net_profit,
                eps, dividend_payout_pct,
                is_interpolated, data_source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, period_end, period_type) DO UPDATE SET
                sales               = excluded.sales,
                expenses            = excluded.expenses,
                operating_profit    = excluded.operating_profit,
                opm_pct             = excluded.opm_pct,
                other_income        = excluded.other_income,
                interest            = excluded.interest,
                depreciation        = excluded.depreciation,
                profit_before_tax   = excluded.profit_before_tax,
                tax_pct             = excluded.tax_pct,
                net_profit          = excluded.net_profit,
                eps                 = excluded.eps,
                dividend_payout_pct = excluded.dividend_payout_pct,
                data_source         = 'screener'
        """, (
            symbol.upper(),
            period_end,
            pt,
            g("sales"),
            g("expenses"),
            g("operating_profit"),
            g("opm_pct"),
            g("other_income"),
            g("interest"),
            g("depreciation"),
            g("profit_before_tax"),
            g("tax_pct"),
            g("net_profit"),
            g("eps"),
            g("dividend_payout_pct"),
            0,           # is_interpolated
            "screener",  # data_source
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"  ✅ profit_and_loss ({period_type}): {count} rows upserted, {skip} skipped [screener]")