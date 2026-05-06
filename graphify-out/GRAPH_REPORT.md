# Graph Report - Fund  (2026-05-06)

## Corpus Check
- 43 files · ~41,048 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 459 nodes · 753 edges · 73 communities detected
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 85 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]

## God Nodes (most connected - your core abstractions)
1. `run_pipeline()` - 42 edges
2. `get_connection()` - 38 edges
3. `warn()` - 15 edges
4. `ok()` - 14 edges
5. `fetch_ownership()` - 14 edges
6. `section()` - 13 edges
7. `compute_quarterly_cashflow()` - 13 edges
8. `main()` - 13 edges
9. `load_cashflow()` - 12 edges
10. `load_cashflow_from_screener()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `get_connection()` --calls--> `run_all_dedup()`  [INFERRED]
  database\db.py → database\dedup.py
- `get_connection()` --calls--> `init_db()`  [INFERRED]
  database\db.py → database\init_db.py
- `get_connection()` --calls--> `audit_table()`  [INFERRED]
  database\db.py → database\validator.py
- `get_connection()` --calls--> `load_cashflow()`  [INFERRED]
  database\db.py → etl\load\cashflow_loader.py
- `rebuild_annual_cashflow_derived()` --calls--> `get_connection()`  [INFERRED]
  etl\load\cashflow_loader.py → database\db.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (47): init_db(), database/init_db.py  v4.0 Reads schema.sql from same directory and creates all, Safely return a DataFrame only if non-None and non-empty.     Prevents: ValueEr, run_pipeline(), _safe_df(), fetch_corporate_actions(), Fetch dividends, splits, and all corporate actions., fetch_earnings() (+39 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (46): compute_fundamentals(), _compute_gross_margin_safe(), compute_growth_metrics(), compute_quarterly_cashflow(), compute_technicals(), fail(), fetch_corporate_actions(), fetch_earnings() (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (39): get_connection(), log_data_quality(), _backfill_net_debt(), _bs_completeness(), _cf_clean(), _cf_find_capex(), _cf_find_total(), _cf_is_total_label() (+31 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (36): _build_period_rows(), _build_raw_details(), _build_rows_from_toplevel(), _clean_num(), _extract_company_id(), _f(), fetch_cashflow(), _fetch_cf_schedule() (+28 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (27): audit_table(), compute_completeness(), _is_null(), database/validator.py  v2.0 ───────────────────────────────────────────────────, Count rows and NULL rates for key fields. Print summary., validate_before_insert(), _completeness(), _df_to_records() (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (22): _clean_num(), _clean_num_part(), _extract_company_id(), fetch_bs_schedules(), _fetch_schedule(), fetch_screener_data(), _get_html(), _merge_schedules_into_bs() (+14 more)

### Community 6 - "Community 6"
Cohesion: 0.23
Nodes (17): _completeness(), _div(), _ensure_bs_extra_cols(), _ensure_cashflow_extra_cols(), _f(), _pct(), etl/load/reconcile.py  v3.0 ───────────────────────────────────────────────────, Idempotently add completeness columns to cash_flow. (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.19
Nodes (13): compute_technicals(), _find_col(), load_technicals(), _obv(), technical_loader.py  —  v2 ─────────────────────────────────────────────────────, Daily rolling VWAP = sum(typical_price * volume, window), Compute ALL technical indicators on a full OHLCV DataFrame.      Input columns e, Load all technical indicators (incl. new ADX/VWAP/OBV/Supertrend).     Skips war (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.29
Nodes (11): dedup_all(), fix_eps_revisions_blobs(), fix_price_daily(), get_conn(), main(), _needs_rescale(), purge_interpolated_cashflow(), purge_technical_nulls() (+3 more)

### Community 9 - "Community 9"
Cohesion: 0.3
Nodes (11): _build_earnings_growth_json(), _compute_gross_margin_safe(), _cr(), fetch_fundamentals(), _get_row(), etl/extract/fundamentals.py  v4.0 ─────────────────────────────────────────────, Build {date: net_income_cr} JSON from annual IS. Newest → oldest., Compute all fundamentals metrics.     MONETARY VALUES → Rs. Crores     RATIOS (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.23
Nodes (7): _extract_company_id(), get_safe_path(), etl/extract/cashflow_scrapper.py  v2.0 ────────────────────────────────────────, Fetch all three CF schedule sections for self.symbol, combine into         a fl, Parameters         ----------         symbol_nse : str             NSE ticker, Fetch Screener company page; tries consolidated first, then standalone., ScreenerCashFlowScraper

### Community 11 - "Community 11"
Cohesion: 0.36
Nodes (10): _add_earnings_growth_json(), _add_ev_inputs(), _add_forward_pe(), _apply_all_patches(), _bs_first(), _cr(), etl/extract/fundamentals_extract_patch.py  v3.0 ───────────────────────────────, JSON of annual net-income in Rs. Crores, newest→oldest.     Example: {"2025-03- (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.29
Nodes (10): _compute_completeness(), _data_changed(), _get_today_row(), load_fundamentals(), load_fundamentals_from_screener(), _pct(), etl/load/fundamentals_loader.py  v5.0 ─────────────────────────────────────────, Merge Screener Ratios + latest quarterly opm_pct + annual dividend_payout_pct (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.18
Nodes (7): load_income(), load_income_from_screener(), _pct_str(), etl/load/income_loader.py  v3.0 ───────────────────────────────────────────────, Load Screener P&L data into scr_* columns of income_statement.     Creates row, 59%' → 59.0, also handles plain floats., Load yfinance income statement rows (detailed line items).

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (9): _fetch_fii_dii_flow(), fetch_ownership(), _fetch_screener_fallback(), _fetch_yf_holders(), _from_screener_df(), etl/extract/ownership.py  v4.0 ─────────────────────────────────────────────────, Extract latest-quarter shareholding from a Screener DataFrame., Fetch shareholding pattern + FII/DII trading flow.      Priority for promoter/FI (+1 more)

### Community 15 - "Community 15"
Cohesion: 0.36
Nodes (7): fetch_growth_metrics(), _pct_to_float(), etl/extract/growth.py  v3.0 ───────────────────────────────────────────────────, Parse one ranges-table., Try consolidated first, then standalone., _scrape_growth_table(), _scrape_symbol()

### Community 16 - "Community 16"
Cohesion: 0.46
Nodes (7): classify_doc(), download_pdf(), extract_documents(), extract_year(), fetch_page(), main(), safe_name()

### Community 17 - "Community 17"
Cohesion: 0.43
Nodes (6): fetch_statements(), _get_row_series(), _interpolate_qbs_from_annual(), Fetch all financial statements (annual + quarterly) with Q-BS interpolation., FIX-A: Interpolate missing Q-BS periods from annual BS., _safe_float()

### Community 18 - "Community 18"
Cohesion: 0.33
Nodes (6): load_ownership(), load_ownership_history(), _parse_period(), etl/load/ownership_loader.py  v2.0 ─────────────────────────────────────────────, Upsert today's ownership snapshot., Load full quarterly shareholding history from Screener DataFrame     into owners

### Community 19 - "Community 19"
Cohesion: 0.47
Nodes (5): _dedup_table(), database/dedup.py  v2.0 ───────────────────────────────────────────────────────, Run deduplication across all configured tables., run_all_dedup(), run_one_time_cleanup()

### Community 20 - "Community 20"
Cohesion: 0.4
Nodes (5): compute_technicals(), etl/extract/technicals.py  v2.0 ────────────────────────────────────────────────, Wilder's smoothing (used by RSI, ATR, ADX)., Compute all technical indicators.      Input df columns required: date, close, h, _wilder_smooth()

### Community 21 - "Community 21"
Cohesion: 0.4
Nodes (2): Checks if file is open in Excel/another app and returns a safe name., ScreenerProDetailed

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Return filename unchanged if free, else append _NEW before extension.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Dynamically extract Screener's numeric company ID from page HTML.         Tries

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): ╔══════════════════════════════════════════════════════════════╗ ║   BUFFETT-GR

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): FIX-C: Search df.index for candidates with priority:       1. Exact case-insens

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Return full row series for first matching candidate (strict-first).

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Return all rows whose index contains `pattern` (case-insensitive).

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): FIX-C: Dual-method gross margin with cross-validation.      Method 1: Gross Pr

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): FIX-A: When Q-BS has fewer periods than Q-IS, back-fill missing     Q-BS column

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): FIX-B: NSE requires a valid session cookie obtained by first     hitting the ma

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): FIX-B: Fetch shareholding pattern from NSE API.     Returns parsed dict with Pr

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): FIX-B: Parse NSE shareholding JSON into clean promoter/FII/DII/retail dict.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): FIX-B: Screener.in fallback for shareholding data.     Scrapes the public compa

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): FIX-B: Pretty-print shareholding as structured table.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): FIX-B: Systematically probe all nsepython function names     that might return

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): FIX-A: Full quarterly CF with Q-BS interpolation + revenue-prorated CapEx.

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Count rows and NULL rates for key fields. Print summary.

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Safely return a DataFrame only if non-None and non-empty.     Prevents: ValueErr

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Extract a metric row as {date_str: crore_value} dict.

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Build [{year, value_cr, yoy_pct}, ...] JSON. Newest → oldest.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Compute growth CAGRs + YoY trends.     All monetary JSON values in Rs. Crores.

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): etl/extract/quarterly_cashflow.py  v4.1 ────────────────────────────────────────

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Exact label match first, then substring — avoids wrong sub-rows.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Original substring-first row finder (kept for CF paths).

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Returns real quarterly cashflow records only.     quality_score: 3=direct_qcf, 2

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Robust number extractor for Screener values.     Handles:       "₹ 1,612"  →

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Like _clean_num but also strips ₹ from a single fragment.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Parse the company overview/ratios panel at the top of the Screener page.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Fetch all Screener.in tables + overview ratios.      Returns dict:       "ove

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Load yfinance cash flow. Sets best_* = yfinance values initially;     screener_

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): One-time migration: remove JSON blob columns from growth_metrics.     SQLite do

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Upsert yfinance-derived growth CAGRs (no JSON blobs).

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): etl/load/quarterly_cashflow_loader.py  v3.0 ────────────────────────────────────

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Look up a balance sheet row using SCREENER_BS_LABEL_MAP patterns.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Add any missing columns to balance_sheet (idempotent).

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Recompute and write completeness_pct + missing_fields_json for a BS row.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Writes Screener overview ratios into fundamentals.     Computes: graham_number,

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Loads Screener balance sheet into the fully normalized balance_sheet table.

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): # NOTE: receivables_over_6m / receivables_under_6m are intentionally

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Look up a balance sheet row using SCREENER_BS_LABEL_MAP patterns.

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Add any missing columns to balance_sheet (idempotent).

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Recompute and write completeness_pct + missing_fields_json for a BS row.

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Writes Screener overview ratios into fundamentals.     Computes: graham_number,

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Loads Screener balance sheet into the fully normalized balance_sheet table.

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): # NOTE: receivables_over_6m / receivables_under_6m are intentionally

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Add any missing columns to balance_sheet (idempotent).

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Recompute and write completeness_pct + missing_fields_json for a BS row.

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Writes Screener overview ratios into fundamentals.     Computes: graham_number,

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Loads Screener balance sheet into the fully normalized balance_sheet table.

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne

## Knowledge Gaps
- **184 isolated node(s):** `cleanup_existing_db.py  v3.0 ──────────────────────────────────────────────────`, `a) Fill adj_close = close where adj_close IS NULL (fallback)     b) Round price`, `database/dedup.py  v2.0 ───────────────────────────────────────────────────────`, `Run deduplication across all configured tables.`, `database/init_db.py  v4.0 Reads schema.sql from same directory and creates all` (+179 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 21`** (6 nodes): `balance_sheet_scrapper.py`, `Checks if file is open in Excel/another app and returns a safe name.`, `ScreenerProDetailed`, `.fetch_schedules()`, `.get_safe_path()`, `.__init__()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Return filename unchanged if free, else append _NEW before extension.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Dynamically extract Screener's numeric company ID from page HTML.         Tries`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `╔══════════════════════════════════════════════════════════════╗ ║   BUFFETT-GR`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `FIX-C: Search df.index for candidates with priority:       1. Exact case-insens`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `Return full row series for first matching candidate (strict-first).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Return all rows whose index contains `pattern` (case-insensitive).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `FIX-C: Dual-method gross margin with cross-validation.      Method 1: Gross Pr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `FIX-A: When Q-BS has fewer periods than Q-IS, back-fill missing     Q-BS column`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `FIX-B: NSE requires a valid session cookie obtained by first     hitting the ma`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `FIX-B: Fetch shareholding pattern from NSE API.     Returns parsed dict with Pr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `FIX-B: Parse NSE shareholding JSON into clean promoter/FII/DII/retail dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `FIX-B: Screener.in fallback for shareholding data.     Scrapes the public compa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `FIX-B: Pretty-print shareholding as structured table.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `FIX-B: Systematically probe all nsepython function names     that might return`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `FIX-A: Full quarterly CF with Q-BS interpolation + revenue-prorated CapEx.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Count rows and NULL rates for key fields. Print summary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Safely return a DataFrame only if non-None and non-empty.     Prevents: ValueErr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Extract a metric row as {date_str: crore_value} dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Build [{year, value_cr, yoy_pct}, ...] JSON. Newest → oldest.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Compute growth CAGRs + YoY trends.     All monetary JSON values in Rs. Crores.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `etl/extract/quarterly_cashflow.py  v4.1 ────────────────────────────────────────`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Exact label match first, then substring — avoids wrong sub-rows.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Original substring-first row finder (kept for CF paths).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Returns real quarterly cashflow records only.     quality_score: 3=direct_qcf, 2`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Robust number extractor for Screener values.     Handles:       "₹ 1,612"  →`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Like _clean_num but also strips ₹ from a single fragment.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Parse the company overview/ratios panel at the top of the Screener page.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Fetch all Screener.in tables + overview ratios.      Returns dict:       "ove`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Load yfinance cash flow. Sets best_* = yfinance values initially;     screener_`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `One-time migration: remove JSON blob columns from growth_metrics.     SQLite do`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Upsert yfinance-derived growth CAGRs (no JSON blobs).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `etl/load/quarterly_cashflow_loader.py  v3.0 ────────────────────────────────────`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Look up a balance sheet row using SCREENER_BS_LABEL_MAP patterns.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Add any missing columns to balance_sheet (idempotent).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Recompute and write completeness_pct + missing_fields_json for a BS row.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Writes Screener overview ratios into fundamentals.     Computes: graham_number,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Loads Screener balance sheet into the fully normalized balance_sheet table.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `# NOTE: receivables_over_6m / receivables_under_6m are intentionally`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Look up a balance sheet row using SCREENER_BS_LABEL_MAP patterns.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Add any missing columns to balance_sheet (idempotent).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Recompute and write completeness_pct + missing_fields_json for a BS row.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Writes Screener overview ratios into fundamentals.     Computes: graham_number,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Loads Screener balance sheet into the fully normalized balance_sheet table.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `# NOTE: receivables_over_6m / receivables_under_6m are intentionally`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Add any missing columns to balance_sheet (idempotent).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Recompute and write completeness_pct + missing_fields_json for a BS row.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Writes Screener overview ratios into fundamentals.     Computes: graham_number,`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Loads Screener balance sheet into the fully normalized balance_sheet table.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Dispatcher. Load order matters:       1. quarterly_results  (overview loader ne`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_pipeline()` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 9`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 17`, `Community 18`, `Community 19`?**
  _High betweenness centrality (0.398) - this node is a cross-community bridge._
- **Why does `load_cashflow()` connect `Community 4` to `Community 0`, `Community 2`?**
  _High betweenness centrality (0.157) - this node is a cross-community bridge._
- **Why does `get_connection()` connect `Community 2` to `Community 0`, `Community 4`, `Community 6`, `Community 7`, `Community 12`, `Community 13`, `Community 18`, `Community 19`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `run_pipeline()` (e.g. with `init_db()` and `insert_stock()`) actually correct?**
  _`run_pipeline()` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `get_connection()` (e.g. with `run_all_dedup()` and `init_db()`) actually correct?**
  _`get_connection()` has 37 INFERRED edges - model-reasoned connections that need verification._
- **What connects `cleanup_existing_db.py  v3.0 ──────────────────────────────────────────────────`, `a) Fill adj_close = close where adj_close IS NULL (fallback)     b) Round price`, `database/dedup.py  v2.0 ───────────────────────────────────────────────────────` to the rest of the system?**
  _184 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._