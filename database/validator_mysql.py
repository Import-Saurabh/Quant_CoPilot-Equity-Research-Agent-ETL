"""
database/validator_mysql.py  v1.0
Data quality validation for MySQL – adapted to the provided MySQL schema.
Tables not present in the schema are omitted.
"""
import json
import math
from database.db_mysql import get_connection

# Required fields per table (must not be NULL)
REQUIRED_FIELDS = {
    "quarterly_results":        ["symbol", "period_end", "sales", "net_profit"],
    "annual_results":           ["symbol", "period_end", "sales", "net_profit"],
    "profit_loss":              ["symbol", "period_end", "period_type"],   # renamed from profit_and_loss
    "balance_sheet":            ["symbol", "period_end", "period_type"],
    "cash_flow":                ["symbol", "period_end", "period_type"],
    "shareholding":             ["symbol", "period_end", "promoter_pct"],  # replaced ownership_history
}

# Completeness columns (must match actual columns in schema)
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
    "profit_loss": [
        "sales", "expenses", "operating_profit", "opm_pct",
        "other_income", "interest", "depreciation",
        "profit_before_tax", "tax_pct", "net_profit", "eps",
        "dividend_payout_pct",
    ],
    "balance_sheet": [
        "equity_capital", "reserves", "total_equity", "borrowings",
        "total_liabilities", "total_assets", "fixed_assets",
        "investments", "other_assets", "net_debt",
    ],
    "cash_flow": [
        "cfo", "cfi", "cff", "free_cash_flow",
    ],
    "shareholding": [
        "promoter_pct", "fii_pct", "dii_pct", "public_pct",
        "total_institutional_pct",
    ],
    "technical_indicators": [
        "close", "rsi_14", "macd", "sma_50", "sma_200"
    ],
    "earnings_history": [
        "eps_actual", "eps_estimate", "surprise_pct"
    ],
    "corporate_actions": [
        "action_type", "value"
    ],
}

# Symbol column name per table
_SYMBOL_COL = {
    "quarterly_results":        "symbol",
    "annual_results":           "symbol",
    "profit_loss":              "symbol",
    "balance_sheet":            "symbol",
    "cash_flow":                "symbol",
    "shareholding":             "symbol",
    "technical_indicators":     "symbol",
    "earnings_history":         "symbol",
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
    pct = round((1 - len(missing) / len(fields)) * 100, 1)
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
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO data_quality_log (
                symbol, table_name, rows_inserted, rows_null_heavy,
                avg_completeness, critical_nulls_json, source, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (symbol, table_name, rows_inserted, rows_null_heavy,
              round(avg_completeness, 1),
              json.dumps(critical_nulls), source, notes))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"  warn  data_quality_log: {e}")

def audit_table(symbol: str, table: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    sym_col = _SYMBOL_COL.get(table)
    fields = COMPLETENESS_FIELDS.get(table, [])

    try:
        if sym_col:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}` WHERE `{sym_col}` = %s", (symbol,))
            total = cursor.fetchone()["COUNT(*)"]
        else:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            total = cursor.fetchone()["COUNT(*)"]

        null_counts = {}
        for f in fields:
            try:
                if sym_col:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM `{table}`
                        WHERE `{sym_col}` = %s AND `{f}` IS NULL
                    """, (symbol,))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}` WHERE `{f}` IS NULL")
                nc = cursor.fetchone()["COUNT(*)"]
                if nc > 0:
                    null_counts[f] = nc
            except Exception:
                pass

        avg_comp = 0.0
        if fields and total > 0:
            filled = sum(total - nc for nc in null_counts.values())
            avg_comp = round(filled / (len(fields) * total) * 100, 1)

        partial_nulls = {k: v for k, v in null_counts.items() if v < total}
        all_null = {k: v for k, v in null_counts.items() if v == total}

        status = f"{total} rows | {avg_comp}% complete"
        if partial_nulls:
            status += f" | partial NULLs: {partial_nulls}"
        if all_null:
            status += f" | all-NULL cols: {list(all_null.keys())}"

        print(f"  audit [{table}] {status}")
        cursor.close()
        conn.close()
        return {"table": table, "total": total,
                "avg_comp": avg_comp, "nulls": null_counts}
    except Exception as e:
        cursor.close()
        conn.close()
        print(f"  warn  audit failed {table}: {e}")
        return {}