"""
database/validator.py  v3.0
────────────────────────────────────────────────────────────────
Fixes vs v2.0 (all reconciled against schema.sql):

  1. income_statement REMOVED from REQUIRED_FIELDS, COMPLETENESS_FIELDS,
     and _SYMBOL_COL — table was dropped in v6.0.

  2. profit_and_loss ADDED to REQUIRED_FIELDS, COMPLETENESS_FIELDS,
     and _SYMBOL_COL — it is the v6.0 replacement and is audited
     by pipeline.py.

  3. quarterly_cashflow_derived renamed to annual_cashflow_derived
     everywhere (REQUIRED_FIELDS, COMPLETENESS_FIELDS, _SYMBOL_COL).
     The table's date key is annual_end, not quarter_end — REQUIRED_FIELDS
     and audit_table updated accordingly.

  4. COMPLETENESS_FIELDS["balance_sheet"] — removed all scr_* ghost
     columns (scr_equity_capital, scr_reserves, scr_borrowings,
     scr_fixed_assets, scr_cwip, scr_investments, scr_other_assets,
     scr_total_assets) which never existed in the schema.
     Replaced total_debt (doesn't exist) with borrowings (actual col).
     Added real columns: equity_capital, reserves, borrowings,
     total_equity, fixed_assets, cwip, investments, total_assets,
     total_liabilities, net_debt.

  5. COMPLETENESS_FIELDS["cash_flow"] — removed all best_* and scr_*
     ghost columns. Replaced with actual columns: cfo, cfi, cff,
     capex, free_cash_flow.

  6. COMPLETENESS_FIELDS["fundamentals"] — removed net_income and
     free_cash_flow (neither column exists in the fundamentals table).
     Added ebitda (does exist). Final set matches schema exactly.

  7. COMPLETENESS_FIELDS["annual_cashflow_derived"] — renamed from
     quarterly_cashflow_derived; added approx_capex and fcf_margin_pct
     which exist in the schema.

  8. audit_table — special-cased annual_cashflow_derived to filter on
     annual_end (its actual date key) instead of the generic symbol
     column filter.
────────────────────────────────────────────────────────────────
"""

import json
import math
from typing import Optional
from database.db import get_connection

REQUIRED_FIELDS = {
    "quarterly_results":        ["symbol", "period_end", "sales", "net_profit"],
    "annual_results":           ["symbol", "period_end", "sales", "net_profit"],
    # FIX 1: income_statement removed; FIX 2: profit_and_loss added
    "profit_and_loss":          ["symbol", "period_end", "period_type"],
    "balance_sheet":            ["symbol", "period_end", "period_type"],
    "cash_flow":                ["symbol", "period_end", "period_type"],
    "growth_metrics":           ["symbol", "as_of_date"],
    "ownership_history":        ["symbol", "period_end", "promoter_pct"],
    "fundamentals":             ["symbol", "as_of_date"],
    # FIX 3: renamed from quarterly_cashflow_derived; key col is annual_end
    "annual_cashflow_derived":  ["symbol", "annual_end"],
}

# All column names verified against schema.sql
COMPLETENESS_FIELDS = {
    "quarterly_results": [
        "sales", "expenses", "operating_profit", "opm_pct",
        "other_income", "interest", "depreciation",
        "profit_before_tax", "tax_pct", "net_profit", "eps",
    ],
    "annual_results": [
        "sales", "expenses", "operating_profit", "opm_pct",
        "other_income", "interest", "depreciation",
        "profit_before_tax", "tax_pct", "net_profit", "eps",
        "dividend_payout_pct",
    ],
    # FIX 2: profit_and_loss replaces income_statement — columns from schema
    "profit_and_loss": [
        "sales", "expenses", "operating_profit", "opm_pct",
        "other_income", "interest", "depreciation",
        "profit_before_tax", "tax_pct", "net_profit", "eps",
        "dividend_payout_pct",
    ],
    # FIX 4: removed all scr_* ghost columns; fixed total_debt → borrowings;
    #         added real schema columns
    "balance_sheet": [
        "equity_capital", "reserves", "total_equity",
        "borrowings",                        # was "total_debt" — doesn't exist
        "total_liabilities", "total_assets",
        "fixed_assets", "cwip", "investments",
        "other_assets", "cash_equivalents",
        "net_debt",
    ],
    # FIX 5: removed all best_* and scr_* ghost columns; actual cols only
    "cash_flow": [
        "cfo", "cfi", "cff",
        "capex", "free_cash_flow",
    ],
    "growth_metrics": [
        "revenue_cagr_3y", "net_profit_cagr_3y", "ebitda_cagr_3y",
        "eps_cagr_3y", "fcf_cagr_3y",
        "sales_cagr_10y", "sales_cagr_5y", "sales_cagr_3y", "sales_ttm",
        "profit_cagr_10y", "profit_cagr_5y", "profit_cagr_3y", "profit_ttm",
        "stock_cagr_10y", "stock_cagr_5y", "stock_cagr_3y", "stock_ttm",
        "roe_10y", "roe_5y", "roe_3y", "roe_last",
    ],
    # FIX 6: removed net_income and free_cash_flow (don't exist in fundamentals);
    #         added ebitda (does exist)
    "fundamentals": [
        "roe_pct", "roce_pct", "pe_ratio", "pb_ratio",
        "revenue", "ebitda", "market_cap",
        "opm_pct", "dividend_payout_pct",
        "ev", "ev_ebitda", "debt_to_equity",
    ],
    # FIX 7: renamed + added approx_capex and fcf_margin_pct (both in schema)
    "annual_cashflow_derived": [
        "revenue", "net_income", "dna",
        "approx_op_cf", "approx_capex", "approx_fcf", "fcf_margin_pct",
    ],
    "ownership_history": [
        "promoter_pct", "fii_pct", "dii_pct", "public_pct",
        "total_institutional_pct",
    ],
}

# Symbol column name per table (for WHERE clause in audit_table)
_SYMBOL_COL = {
    "quarterly_results":        "symbol",
    "annual_results":           "symbol",
    # FIX 1+2: income_statement removed; profit_and_loss added
    "profit_and_loss":          "symbol",
    "balance_sheet":            "symbol",
    "cash_flow":                "symbol",
    "growth_metrics":           "symbol",
    "ownership_history":        "symbol",
    "fundamentals":             "symbol",
    # FIX 3: renamed from quarterly_cashflow_derived
    "annual_cashflow_derived":  "symbol",
    "ownership":                "symbol",
    "earnings_history":         "symbol",
    "technical_indicators":     "symbol",
    "corporate_actions":        "symbol",
}


def _is_null(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


def compute_completeness(row: dict, table: str):
    fields = COMPLETENESS_FIELDS.get(table, [])
    if not fields:
        return 100.0, []
    missing = [f for f in fields if _is_null(row.get(f))]
    pct     = round((1 - len(missing) / len(fields)) * 100, 1)
    return pct, missing


def validate_before_insert(row: dict, table: str):
    required = REQUIRED_FIELDS.get(table, [])
    for field in required:
        if _is_null(row.get(field)):
            return False, f"required field '{field}' is NULL"
    return True, "ok"


def log_data_quality(symbol, table_name, rows_inserted,
                     rows_null_heavy, avg_completeness,
                     critical_nulls, source, notes=""):
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO data_quality_log (
                symbol, table_name, rows_inserted, rows_null_heavy,
                avg_completeness, critical_nulls_json, source, notes
            ) VALUES (?,?,?,?,?,?,?,?)
        """, (symbol, table_name, rows_inserted, rows_null_heavy,
              round(avg_completeness, 1),
              json.dumps(critical_nulls), source, notes))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  warn  data_quality_log: {e}")


def audit_table(symbol: str, table: str) -> dict:
    """Count rows and NULL rates for key fields. Print summary."""
    conn    = get_connection()
    sym_col = _SYMBOL_COL.get(table)
    fields  = COMPLETENESS_FIELDS.get(table, [])

    try:
        if sym_col:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {sym_col}=?", (symbol,)
            ).fetchone()[0]
        else:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

        null_counts = {}
        for f in fields:
            try:
                if sym_col:
                    nc = conn.execute(
                        f"SELECT COUNT(*) FROM {table} "
                        f"WHERE {sym_col}=? AND {f} IS NULL", (symbol,)
                    ).fetchone()[0]
                else:
                    nc = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {f} IS NULL"
                    ).fetchone()[0]
                if nc > 0:
                    null_counts[f] = nc
            except Exception:
                pass

        avg_comp = 0.0
        if fields and total > 0:
            filled   = sum(total - nc for nc in null_counts.values())
            avg_comp = round(filled / (len(fields) * total) * 100, 1)

        # Only show NULL fields that have SOME rows populated (not all null)
        partial_nulls = {k: v for k, v in null_counts.items() if v < total}
        all_null      = {k: v for k, v in null_counts.items() if v == total}

        status = f"{total} rows | {avg_comp}% complete"
        if partial_nulls:
            status += f" | partial NULLs: {partial_nulls}"
        if all_null:
            status += f" | all-NULL cols: {list(all_null.keys())}"

        print(f"  audit [{table}] {status}")
        conn.close()
        return {"table": table, "total": total,
                "avg_comp": avg_comp, "nulls": null_counts}

    except Exception as e:
        conn.close()
        print(f"  warn  audit failed {table}: {e}")
        return {}