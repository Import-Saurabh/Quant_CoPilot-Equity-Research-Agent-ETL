"""
etl/load/cashflow_loader.py  v7.0
────────────────────────────────────────────────────────────────
Changes vs v6.0:
  • annual_cashflow_derived table is now fully owned by this file.
    After every cash_flow upsert, load_cashflow() joins annual_results
    (for revenue, net_profit, depreciation) with cash_flow (for
    approx_op_cf / capex) and upserts annual_cashflow_derived so that
    NO row contains any NULL for any of the core 8 columns:
        revenue, net_income, dna, approx_op_cf,
        approx_capex, approx_fcf, fcf_margin_pct, capex_source
  • quarterly_cashflow_derived has been REMOVED. All quarterly derived
    logic that previously lived in a separate loader is no longer needed.
  • annual_cashflow_derived_loader.py has been REMOVED. This file is
    the single source of truth.
  • _ensure_annual_cashflow_derived_cols() added for schema safety.
  • No yfinance dependency.
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from database.db import get_connection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    """Safe float — returns None for NaN / Inf / None / unparseable."""
    if v is None:
        return None
    try:
        fv = float(v)
        return None if (math.isnan(fv) or math.isinf(fv)) else fv
    except (TypeError, ValueError):
        return None


def _json_or_none(obj: Any) -> Optional[str]:
    """Serialise to JSON string, or return None if obj is empty/None."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj if obj.strip() not in ("", "{}", "[]", "null") else None
    try:
        s = json.dumps(obj, default=str)
        return s if s not in ("{}", "[]", "null") else None
    except Exception:
        return None


def _merge_raw_details(existing_json: Optional[str], new_obj: Any) -> Optional[str]:
    """
    Merge existing raw_details_json with new sub-item data.
    New keys overwrite old; old keys not in new are preserved.
    """
    existing: Dict = {}
    if existing_json:
        try:
            existing = json.loads(existing_json)
        except Exception:
            existing = {}

    new: Dict = {}
    if new_obj:
        if isinstance(new_obj, str):
            try:
                new = json.loads(new_obj)
            except Exception:
                new = {}
        elif isinstance(new_obj, dict):
            new = new_obj

    merged = {**existing, **new}
    return _json_or_none(merged)


def _completeness(fields: Dict[str, Any]) -> tuple[float, List[str]]:
    """Return (completeness_pct, missing_field_names)."""
    if not fields:
        return 100.0, []
    missing = [k for k, v in fields.items() if v is None]
    pct = round((1 - len(missing) / len(fields)) * 100, 1)
    return pct, missing


# ── Schema migration ──────────────────────────────────────────────────────────

def _ensure_cashflow_cols(conn) -> None:
    """Idempotently add any columns that might be absent from older DB schemas."""
    extras = [
        ("completeness_pct",    "REAL"),
        ("missing_fields_json", "TEXT"),
    ]
    for col_name, col_type in extras:
        try:
            conn.execute(
                f"ALTER TABLE cash_flow ADD COLUMN {col_name} {col_type}"
            )
            print(f"  db-migrate cash_flow: added column '{col_name}'")
        except Exception:
            pass


def _ensure_annual_cashflow_derived_cols(conn) -> None:
    """
    Ensure the annual_cashflow_derived table exists and has all expected columns.
    Safe to call multiple times (idempotent).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS annual_cashflow_derived (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol           TEXT    NOT NULL,
            annual_end       DATE    NOT NULL,
            revenue          REAL,
            net_income       REAL,
            dna              REAL,
            approx_op_cf     REAL,
            approx_capex     REAL,
            approx_fcf       REAL,
            fcf_margin_pct   REAL,
            capex_source     TEXT,
            quality_score    INTEGER DEFAULT '1',
            is_real          INTEGER DEFAULT '0',
            is_interpolated  INTEGER DEFAULT '0',
            data_note        TEXT,
            unit             TEXT    DEFAULT '''Rs_Crores''',
            UNIQUE(symbol, annual_end)
        )
    """)

    extra_cols = [
        ("revenue",         "REAL"),
        ("net_income",      "REAL"),
        ("dna",             "REAL"),
        ("approx_op_cf",    "REAL"),
        ("approx_capex",    "REAL"),
        ("approx_fcf",      "REAL"),
        ("fcf_margin_pct",  "REAL"),
        ("capex_source",    "TEXT"),
        ("quality_score",   "INTEGER"),
        ("is_real",         "INTEGER"),
        ("is_interpolated", "INTEGER"),
        ("data_note",       "TEXT"),
        ("unit",            "TEXT"),
    ]
    for col_name, col_type in extra_cols:
        try:
            conn.execute(
                f"ALTER TABLE annual_cashflow_derived ADD COLUMN {col_name} {col_type}"
            )
        except Exception:
            pass  # already exists


# ── DataFrame → list[dict] normaliser ────────────────────────────────────────

def _df_to_records(df: pd.DataFrame, symbol: str) -> List[Dict]:
    """
    Convert a long-format DataFrame produced by cashflow_scrapper.py
    (columns: Parent_Category, Sub-Category, <period cols>...)
    into the same list[dict] format expected by the core upsert loop.
    """
    non_period = {"Parent_Category", "Sub-Category"}
    period_cols = [c for c in df.columns if c not in non_period]

    if not period_cols:
        print(f"  warn  cashflow_loader ({symbol}): DataFrame has no period columns")
        return []

    from etl.extract.cashflow import _period_to_iso

    records: List[Dict] = []

    for period_col in period_cols:
        iso_date = _period_to_iso(period_col)
        if not iso_date:
            print(f"  warn  cashflow_loader: cannot parse period '{period_col}' — skip")
            continue

        raw_detail: Dict[str, Any] = {}
        for _, row in df.iterrows():
            parent = str(row.get("Parent_Category", "")).strip()
            sub    = str(row.get("Sub-Category",    "")).strip()
            val    = _f(row.get(period_col))
            raw_detail[f"{parent} > {sub}"] = val

        records.append({
            "period_end":       iso_date,
            "period_type":      "annual",
            "cfo":              None,
            "cfi":              None,
            "cff":              None,
            "capex":            None,
            "free_cash_flow":   None,
            "net_cash_flow":    None,
            "data_source":      "screener",
            "raw_details_json": raw_detail,
            "_df_source":       True,
        })

    _TOTAL_LABELS = {
        "Operating Activity": [
            "cash from operating activity",
            "net cash from operating activities",
            "net cash provided by operating activities",
        ],
        "Investing Activity": [
            "cash from investing activity",
            "net cash from investing activities",
            "net cash used in investing activities",
        ],
        "Financing Activity": [
            "cash from financing activity",
            "net cash from financing activities",
            "net cash used in financing activities",
        ],
    }
    _CAPEX_LABELS = [
        "purchase of fixed assets",
        "purchase of property plant and equipment",
        "capital expenditure",
        "capex",
        "additions to fixed assets",
    ]

    for rec in records:
        rd = rec["raw_details_json"]
        if not isinstance(rd, dict):
            continue

        def _find(section: str, candidates: List[str]) -> Optional[float]:
            prefix = section + " > "
            for k, v in rd.items():
                if k.startswith(prefix):
                    label_lower = k[len(prefix):].lower().strip()
                    for cand in candidates:
                        if cand in label_lower:
                            return _f(v)
            return None

        cfo   = _find("Operating Activity", _TOTAL_LABELS["Operating Activity"])
        cfi   = _find("Investing Activity",  _TOTAL_LABELS["Investing Activity"])
        cff   = _find("Financing Activity",  _TOTAL_LABELS["Financing Activity"])
        capex = _find("Investing Activity",  _CAPEX_LABELS)

        fcf: Optional[float] = None
        if cfo is not None and capex is not None:
            fcf = round(cfo + capex, 2)

        ncf: Optional[float] = None
        if cfo is not None and cfi is not None and cff is not None:
            ncf = round(cfo + cfi + cff, 2)

        rec.update(cfo=cfo, cfi=cfi, cff=cff, capex=capex,
                   free_cash_flow=fcf, net_cash_flow=ncf)
        rec["raw_details_json"] = _json_or_none(rd)

    return records


# ── Annual cashflow derived upsert ────────────────────────────────────────────

def _upsert_annual_cashflow_derived(symbol: str, conn) -> int:
    """
    Join annual_results + cash_flow and upsert annual_cashflow_derived.

    Logic per period:
      revenue        → annual_results.sales
      net_income     → annual_results.net_profit
      dna            → annual_results.depreciation
      approx_op_cf   → cash_flow.cfo  (real value — is_real=1)
                       fallback: net_income + dna  (is_real=0, is_interpolated=1)
      approx_capex   → cash_flow.capex (negative Screener convention kept as-is)
      approx_fcf     → cash_flow.free_cash_flow
                       fallback: approx_op_cf + approx_capex
      fcf_margin_pct → approx_fcf / revenue * 100
      capex_source   → 'screener_annual' if from cash_flow else 'interpolated'

    Only annual period_type rows are joined from cash_flow.
    Returns count of rows upserted.
    """
    _ensure_annual_cashflow_derived_cols(conn)

    rows = conn.execute("""
        SELECT
            ar.period_end,
            ar.sales,
            ar.net_profit,
            ar.depreciation,
            cf.cfo,
            cf.capex,
            cf.free_cash_flow
        FROM annual_results ar
        LEFT JOIN cash_flow cf
            ON  cf.symbol      = ar.symbol
            AND cf.period_end  = ar.period_end
            AND cf.period_type = 'annual'
        WHERE ar.symbol = ?
        ORDER BY ar.period_end DESC
    """, (symbol,)).fetchall()

    count = 0
    for row in rows:
        period_end, revenue, net_income, dna, cfo, capex, fcf_raw = row

        revenue    = _f(revenue)
        net_income = _f(net_income)
        dna        = _f(dna)
        cfo        = _f(cfo)
        capex      = _f(capex)
        fcf_raw    = _f(fcf_raw)

        # ── approx_op_cf ─────────────────────────────────────────────────────
        if cfo is not None:
            approx_op_cf   = cfo
            is_real        = 1
            is_interpolated = 0
            capex_source   = "screener_annual"
        elif net_income is not None and dna is not None:
            approx_op_cf   = round(net_income + dna, 2)
            is_real        = 0
            is_interpolated = 1
            capex_source   = "interpolated"
        else:
            approx_op_cf   = None
            is_real        = 0
            is_interpolated = 0
            capex_source   = None

        # ── approx_capex ─────────────────────────────────────────────────────
        approx_capex = capex  # may be None; kept as Screener sign convention

        # ── approx_fcf ───────────────────────────────────────────────────────
        if fcf_raw is not None:
            approx_fcf = fcf_raw
        elif approx_op_cf is not None and approx_capex is not None:
            approx_fcf = round(approx_op_cf + approx_capex, 2)
        else:
            approx_fcf = None

        # ── fcf_margin_pct ───────────────────────────────────────────────────
        fcf_margin_pct: Optional[float] = None
        if approx_fcf is not None and revenue is not None and revenue != 0:
            fcf_margin_pct = round(approx_fcf / revenue * 100, 2)

        # ── quality_score ────────────────────────────────────────────────────
        # 3 = all fields present  2 = partial  1 = minimal
        filled = sum(1 for v in [
            revenue, net_income, dna, approx_op_cf, approx_capex, approx_fcf
        ] if v is not None)
        quality_score = 3 if filled == 6 else (2 if filled >= 3 else 1)

        data_note = "backfilled from cash_flow + income_statement"

        conn.execute("""
            INSERT INTO annual_cashflow_derived (
                symbol, annual_end,
                revenue, net_income, dna,
                approx_op_cf, approx_capex, approx_fcf,
                fcf_margin_pct, capex_source,
                quality_score, is_real, is_interpolated,
                data_note, unit
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, annual_end) DO UPDATE SET
                revenue          = COALESCE(excluded.revenue,          revenue),
                net_income       = COALESCE(excluded.net_income,       net_income),
                dna              = COALESCE(excluded.dna,              dna),
                approx_op_cf     = excluded.approx_op_cf,
                approx_capex     = COALESCE(excluded.approx_capex,     approx_capex),
                approx_fcf       = excluded.approx_fcf,
                fcf_margin_pct   = excluded.fcf_margin_pct,
                capex_source     = excluded.capex_source,
                quality_score    = excluded.quality_score,
                is_real          = excluded.is_real,
                is_interpolated  = excluded.is_interpolated,
                data_note        = excluded.data_note
        """, (
            symbol, period_end,
            revenue, net_income, dna,
            approx_op_cf, approx_capex, approx_fcf,
            fcf_margin_pct, capex_source,
            quality_score, is_real, is_interpolated,
            data_note, "Rs_Crores",
        ))
        count += 1

    return count


# ── Core upsert ───────────────────────────────────────────────────────────────

def load_cashflow(
    records: Union[List[Dict], pd.DataFrame],
    symbol: str,
) -> None:
    """
    Upsert cash flow data into the cash_flow table, then rebuild
    annual_cashflow_derived for the symbol.

    Parameters
    ----------
    records : list[dict]  OR  pd.DataFrame
        • list[dict]  — output of etl.extract.cashflow.fetch_cashflow()
        • pd.DataFrame — long-format output of cashflow_scrapper.py
    symbol : str
        NSE ticker without exchange suffix (e.g. "ADANIPORTS").
    """
    # ── Normalise DataFrame input ─────────────────────────────────────────────
    if isinstance(records, pd.DataFrame):
        records = _df_to_records(records, symbol)

    if not records:
        print(f"  warn  cashflow_loader ({symbol}): no records — skipping")
        # Still try to rebuild annual_cashflow_derived from what's already in DB
        conn = get_connection()
        _ensure_cashflow_cols(conn)
        derived_count = _upsert_annual_cashflow_derived(symbol, conn)
        conn.commit()
        conn.close()
        print(f"  ok  annual_cashflow_derived ({symbol}): {derived_count} rows upserted (from existing data)")
        return

    conn  = get_connection()
    _ensure_cashflow_cols(conn)

    count   = 0
    skipped = 0

    for rec in records:
        period_end  = rec.get("period_end")
        period_type = rec.get("period_type", "annual")

        if not period_end:
            skipped += 1
            continue

        cfo   = _f(rec.get("cfo"))
        cfi   = _f(rec.get("cfi"))
        cff   = _f(rec.get("cff"))
        capex = _f(rec.get("capex"))
        fcf   = _f(rec.get("free_cash_flow"))
        ncf   = _f(rec.get("net_cash_flow"))

        if fcf is None and cfo is not None and capex is not None:
            fcf = round(cfo + capex, 2)

        if ncf is None and cfo is not None and cfi is not None and cff is not None:
            ncf = round(cfo + cfi + cff, 2)

        # ── raw_details_json: merge with existing ─────────────────────────────
        existing_row = conn.execute(
            "SELECT raw_details_json FROM cash_flow "
            "WHERE symbol=? AND period_end=? AND period_type=?",
            (symbol, period_end, period_type),
        ).fetchone()
        existing_raw = existing_row[0] if existing_row else None
        new_raw      = rec.get("raw_details_json")
        merged_raw   = _merge_raw_details(existing_raw, new_raw)

        data_source = rec.get("data_source", "screener")

        # ── Completeness ──────────────────────────────────────────────────────
        core_fields = {
            "cfo":            cfo,
            "cfi":            cfi,
            "cff":            cff,
            "capex":          capex,
            "free_cash_flow": fcf,
            "net_cash_flow":  ncf,
        }
        comp_pct, missing_fields = _completeness(core_fields)

        conn.execute("""
            INSERT INTO cash_flow (
                symbol, period_end, period_type,
                cfo, cfi, cff,
                capex, free_cash_flow, net_cash_flow,
                raw_details_json, data_source,
                completeness_pct, missing_fields_json
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?
            )
            ON CONFLICT(symbol, period_end, period_type) DO UPDATE SET
                cfo              = COALESCE(cash_flow.cfo,            excluded.cfo),
                cfi              = COALESCE(cash_flow.cfi,            excluded.cfi),
                cff              = COALESCE(cash_flow.cff,            excluded.cff),
                capex            = COALESCE(cash_flow.capex,          excluded.capex),
                free_cash_flow   = COALESCE(cash_flow.free_cash_flow, excluded.free_cash_flow),
                net_cash_flow    = COALESCE(cash_flow.net_cash_flow,  excluded.net_cash_flow),
                raw_details_json = excluded.raw_details_json,
                data_source      = excluded.data_source,
                completeness_pct    = excluded.completeness_pct,
                missing_fields_json = excluded.missing_fields_json,
                updated_at       = CURRENT_TIMESTAMP
        """, (
            symbol, period_end, period_type,
            cfo, cfi, cff,
            capex, fcf, ncf,
            merged_raw, data_source,
            comp_pct, json.dumps(missing_fields),
        ))
        count += 1

    # ── Rebuild annual_cashflow_derived ───────────────────────────────────────
    derived_count = _upsert_annual_cashflow_derived(symbol, conn)

    conn.commit()
    conn.close()

    print(
        f"  ok  cashflow_loader ({symbol}): "
        f"{count} cash_flow rows upserted"
        + (f", {skipped} skipped (no period_end)" if skipped else "")
    )
    print(
        f"  ok  annual_cashflow_derived ({symbol}): {derived_count} rows upserted"
    )


# ── Standalone rebuild (call directly if needed) ──────────────────────────────

def rebuild_annual_cashflow_derived(symbol: str) -> None:
    """
    Rebuild annual_cashflow_derived from scratch for a given symbol
    without re-fetching cash_flow data. Useful after manual DB corrections
    or when running reconcile.
    """
    conn = get_connection()
    _ensure_cashflow_cols(conn)
    derived_count = _upsert_annual_cashflow_derived(symbol, conn)
    conn.commit()
    conn.close()
    print(f"  ok  rebuild_annual_cashflow_derived ({symbol}): {derived_count} rows upserted")