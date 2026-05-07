"""
BUFFETT-GRADE ETL PIPELINE  v6.0
Changes vs v5.8:
  • income_statement table REMOVED.
  • New profit_and_loss table (Screener-only source of truth).
  • statements.py (yfinance income) REMOVED from pipeline.
  • profit_and_loss.py  → fetch_profit_and_loss()
  • profit_and_loss_loader.py → load_profit_and_loss()
  • reconcile updated to target profit_and_loss table.
"""

import sys
import os
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.init_db   import init_db
from database.dedup     import run_all_dedup
from database.validator import audit_table

from etl.extract.price              import fetch_price
from etl.extract.fundamentals       import fetch_fundamentals
from etl.extract.profit_and_loss    import fetch_profit_and_loss       # ← NEW
from etl.extract.technicals         import compute_technicals
from etl.extract.corporate_actions  import fetch_corporate_actions
from etl.extract.macro              import fetch_market_indices, fetch_rbi_rates, fetch_macro_indicators
from etl.extract.ownership          import fetch_ownership
from etl.extract.earnings           import fetch_earnings
from etl.extract.growth             import fetch_growth_metrics
from etl.extract.screener           import fetch_screener_data

from etl.load.stock_loader              import insert_stock
from etl.load.price_loader              import load_price
from etl.load.technical_loader          import load_technicals
from etl.load.fundamentals_loader       import load_fundamentals
from etl.load.profit_and_loss_loader    import load_profit_and_loss    # ← NEW
from etl.load.cashflow_loader           import load_cashflow
from etl.load.corporate_actions_loader  import load_corporate_actions
from etl.load.macro_loader              import (load_market_indices, load_forex_commodities,
                                                load_rbi_rates, load_macro_indicators)
from etl.load.ownership_loader          import load_ownership
from etl.load.earnings_loader           import (load_earnings_history, load_earnings_estimates,
                                                load_eps_trend, load_eps_revisions)
from etl.load.growth_loader             import load_growth_metrics
from etl.load.run_log_loader            import log_run
from etl.load.screener_loader           import load_all_screener
from etl.load.reconcile                 import run_reconciliation

import pandas as pd


def _safe_df(obj) -> pd.DataFrame | None:
    """
    Safely return a DataFrame only if non-None and non-empty.
    Never use `if df:` or `df or other` on pandas DataFrames.
    """
    if obj is None:
        return None
    if isinstance(obj, pd.DataFrame):
        return obj if not obj.empty else None
    return None


def run_pipeline(symbol_yf: str = "ADANIPORTS.NS"):
    symbol_nse = symbol_yf.replace(".NS", "")
    today      = date.today().isoformat()
    ok_mods, warn_mods = [], []

    print(f"\n{'='*60}")
    print(f"  BUFFETT ETL PIPELINE  v6.0")
    print(f"  Symbol : {symbol_nse}  ({symbol_yf})")
    print(f"  Date   : {today}")
    print(f"{'='*60}\n")

    # ── 0. Init DB ─────────────────────────────────────────────
    init_db()

    # ── 1. Seed stock ──────────────────────────────────────────
    insert_stock(symbol_nse, symbol_nse)
    print(f"[1/11] Stock seeded: {symbol_nse}")

    # ── 2. Price ───────────────────────────────────────────────
    print(f"\n[2/11] Price data...")
    price_df = None
    try:
        price_df = fetch_price(symbol_yf, years=5)
        load_price(price_df, symbol_nse)
        ok_mods.append("price")
    except Exception as e:
        print(f"  error price: {e}"); warn_mods.append("price")

    # ── 3. Technicals ──────────────────────────────────────────
    print(f"\n[3/11] Technical indicators...")
    try:
        if price_df is not None and not price_df.empty:
            tech_df = compute_technicals(price_df.copy())
            tech_df = tech_df[tech_df["sma_200"].notna()].copy()
            load_technicals(tech_df, symbol_nse)
            ok_mods.append("technicals")
        else:
            raise Exception("no price data")
    except Exception as e:
        print(f"  error technicals: {e}"); warn_mods.append("technicals")

    # ── 4. Screener.in (primary financial data) ────────────────
    print(f"\n[4/11] Screener.in (primary financial data source)...")
    screener_data = {}
    try:
        screener_data = fetch_screener_data(symbol_nse)
        if not screener_data:
            raise Exception("empty response from Screener.in")
        load_all_screener(screener_data, symbol_nse)
        ok_mods.append("screener")
    except Exception as e:
        print(f"  error screener: {e}"); warn_mods.append("screener")
        import traceback; traceback.print_exc()

    time.sleep(0.5)

    # ── 5. Profit & Loss (Screener — replaces income_statement) ─
    print(f"\n[5/11] Profit & Loss (Screener)...")
    try:
        pl_df = fetch_profit_and_loss(symbol_nse, period_type="annual")
        load_profit_and_loss(_safe_df(pl_df), symbol_nse, "annual")
        ok_mods.append("profit_and_loss")
    except Exception as e:
        print(f"  error profit_and_loss: {e}"); warn_mods.append("profit_and_loss")
        import traceback; traceback.print_exc()

    time.sleep(0.5)

    # ── 6. Fundamentals (yfinance ratios/valuation) ────────────
    print(f"\n[6/11] Fundamentals (yfinance ratios/valuation)...")
    try:
        fund_data = fetch_fundamentals(symbol_yf)
        load_fundamentals(symbol_nse, fund_data)

        screener_ratios = screener_data.get("ratios") if screener_data else None
        if screener_ratios is not None and isinstance(screener_ratios, pd.DataFrame) \
                and not screener_ratios.empty:
            from etl.load.screener_loader import load_fundamentals_from_screener
            load_fundamentals_from_screener(screener_ratios, symbol_nse)

        ok_mods.append("fundamentals_yf")
    except Exception as e:
        print(f"  error fundamentals_yf: {e}"); warn_mods.append("fundamentals_yf")

    time.sleep(0.5)

    # ── 7. Cash flow (yfinance) ────────────────────────────────
    # ── 7. Cash flow (yfinance) — REMOVED (Screener is primary source) ─
    print(f"\n[7/11] Cash flow statements (yfinance) — skipped (Screener data used)")
    # ── 8. Corporate actions ───────────────────────────────────
    print(f"\n[8/11] Corporate actions...")
    try:
        ca_data = fetch_corporate_actions(symbol_yf)
        load_corporate_actions(ca_data, symbol_nse)
        ok_mods.append("corporate_actions")
    except Exception as e:
        print(f"  error corporate_actions: {e}"); warn_mods.append("corporate_actions")

    time.sleep(0.3)

    # ── 9. Macro ───────────────────────────────────────────────
    print(f"\n[9/11] Macro & market data...")
    try:
        mkt = fetch_market_indices()
        load_market_indices(mkt, today)
        load_forex_commodities(mkt, today)
        load_rbi_rates(fetch_rbi_rates())
        macro_recs = fetch_macro_indicators()
        if macro_recs:
            load_macro_indicators(macro_recs)
        ok_mods.append("macro")
    except Exception as e:
        print(f"  error macro: {e}"); warn_mods.append("macro")

    time.sleep(0.3)

    # ── 10. Ownership ──────────────────────────────────────────
    print(f"\n[10/11] Ownership...")
    try:
        screener_sh = screener_data.get("shareholding") if screener_data else None
        own_data = fetch_ownership(symbol_yf, symbol_nse,
                                   screener_shareholding_df=screener_sh)
        load_ownership(own_data, symbol_nse)
        ok_mods.append("ownership")
    except Exception as e:
        print(f"  error ownership: {e}"); warn_mods.append("ownership")

    time.sleep(0.3)

    # ── 11. Earnings + Growth ──────────────────────────────────
    print(f"\n[11/11] Earnings & Growth...")
    try:
        earn = fetch_earnings(symbol_yf)
        if earn.get("earnings_history"):
            load_earnings_history(earn["earnings_history"], symbol_nse)
        if earn.get("earnings_estimates"):
            load_earnings_estimates(earn["earnings_estimates"], symbol_nse)
        if earn.get("eps_trend"):
            load_eps_trend(earn["eps_trend"], symbol_nse)
        if earn.get("eps_revisions"):
            load_eps_revisions(earn["eps_revisions"], symbol_nse)
        ok_mods.append("earnings")
    except Exception as e:
        print(f"  error earnings: {e}"); warn_mods.append("earnings")

    time.sleep(0.3)

    try:
        growth = fetch_growth_metrics(symbol_nse)
        load_growth_metrics(growth, symbol_nse)
        ok_mods.append("growth_metrics")
    except Exception as e:
        print(f"  error growth_metrics: {e}"); warn_mods.append("growth_metrics")

    # ── Dedup ──────────────────────────────────────────────────
    print(f"\n[DEDUP]...")
    try:
        run_all_dedup()
        print("  dedup complete")
    except Exception as e:
        print(f"  dedup error: {e}")

    # ── Reconciliation ─────────────────────────────────────────
    try:
        run_reconciliation(symbol_nse)
        ok_mods.append("reconcile")
    except Exception as e:
        print(f"  error reconcile: {e}"); warn_mods.append("reconcile")
        import traceback; traceback.print_exc()

    # ── Final audits ───────────────────────────────────────────
    print(f"\n[AUDIT]")
    for tbl in [
        "fundamentals", "growth_metrics",
        "quarterly_results", "annual_results",
        "profit_and_loss",                      # ← replaces income_statement
        "balance_sheet",
        "cash_flow", "annual_cashflow_derived",
    ]:
        audit_table(symbol_nse, tbl)

    log_run(symbol_nse, ok_mods, warn_mods)

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE  {today}")
    print(f"  OK   : {', '.join(ok_mods)}")
    print(f"  WARN : {', '.join(warn_mods) or 'none'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "ADANIPORTS.NS"
    run_pipeline(sym)