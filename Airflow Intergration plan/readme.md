# Airflow Integration Plan: Quant Copilot ETL Orchestration

## 1. Current Architecture Overview (from Graph Analysis)

The Quant Copilot project is a **FastAPI‑based equity research ETL system** with the following characteristics:

- **51 source files** (~34k words) → **639 code nodes** (functions/classes) connected by **671 edges**.
- **229 communities** discovered – indicating a highly modular design with many utility functions, single‑purpose extractors, and dedicated loaders.
- **God nodes** (most connected functions) reveal the core orchestration logic:
  - `_load_result()` – central dispatcher routing extracted data to the correct MySQL loader (17 edges).
  - `clean_ticker_for_screener()` – used by almost every Screener extractor to normalise tickers (16 edges).
  - `run_doc_pipeline()` – runs the document ingestion pipeline (14 edges).
  - `load_cash_flow()`, `get_connection()` – heavy data loading and DB connection helpers.
- **Surprising connections** (inferred edges) show cross‑module calls that are currently implicit (e.g., `execute_pipeline()` → `run_pipeline()`, `log_data_quality()` → `get_connection()`). These represent **hidden dependencies** that must be made explicit in Airflow.

Key modules identified from communities:

| Community | Focus | Files (examples) |
|-----------|-------|------------------|
| 0 | FastAPI app, CLI entry | `main.py`, `_cli_ingest`, `_cli_retry` |
| 2 | Extractors – Screener data | `extract_balance_sheet`, `extract_cash_flow`, `extract_earnings_estimates` |
| 3,8,9,10,13,18 | Loaders – earnings, balance sheet, P&L, quarterly, growth, corporate actions | `load_earnings_estimates`, `load_balance_sheet`, `load_profit_loss` |
| 4 | API routes – triggers | `ingest_stock()`, `ingest_docs()` |
| 5 | Document pipeline | `extract_annual_reports`, `extract_concalls`, `download_pdf`, `upload_document` |
| 12,14‑17 | Screener helpers | `clean_ticker_for_screener`, `get_screener_id_and_slug`, `parse_html_table` |
| 1,23,47‑51 | Database utilities | `init_db`, `dedup`, `validator`, `audit_table` |
| 7,81‑84 | Macro indicators | `extract_macro`, `fetch_rbi_rates`, `fetch_world_bank` |
| 11,103‑105 | Technicals | `compute_technicals`, `load_technicals` |
| 20 | Stock master | `load_stock_master` |
| 21,24,85‑87 | Ownership & corp actions | `fetch_corporate_actions`, `fetch_shareholding` |
| 22,90‑91 | Profit & Loss extract | `fetch_profit_and_loss` |
| 106‑116 | Cash flow loader (with derived tables) | `load_cash_flow`, `rebuild_annual_cashflow_derived` |

> **Important**: Many communities are singletons (e.g., 23, 36‑238). These represent individual utility functions or scripts that are currently **not connected in the graph** – they will become Airflow `PythonOperator` tasks.

## 2. Production Airflow Integration Strategy

### 2.1 High‑Level Design

We will **replace the existing ad‑hoc orchestration** (e.g., `run_pipeline()`, `_load_result()`) with explicit **Airflow DAGs**. The philosophy:

- **Every ETL step becomes an idempotent Airflow task**.
- **Dependencies are declared** (no more hidden cross‑module calls).
- **Data passes via XCom or, for large DataFrames, via object storage (MinIO/S3)**.
- **Retries, alerts, and monitoring** are managed by Airflow, not by custom code.

### 2.2 DAG Decomposition

We propose **three primary DAGs**:

1. **`stock_etl_dag`** – Daily run for a configurable list of tickers.
2. **`document_etl_dag`** – Daily document ingestion (annual reports, concalls).
3. **`macro_etl_dag`** – Weekly/monthly macro indicator refresh.

All DAGs will:
- Use **Airflow Connections** for MySQL, MinIO, and external APIs.
- Use **Airflow Variables** for ticker lists, thresholds, and environment flags.
- Log data quality as Airflow **task callbacks** or via **custom sensors**.

### 2.3 Task Mapping (Existing Functions → Airflow Tasks)

The following mapping is derived from the graph communities. Each row becomes one `PythonOperator` (or `BranchPythonOperator`) task.

| Task ID | Python Callable | Source Module | Dependencies (example) |
|---------|----------------|---------------|------------------------|
| `clean_ticker` | `clean_ticker_for_screener` | Community 12 | None |
| `get_screener_metadata` | `get_screener_id_and_slug` | Community 12 | `clean_ticker` |
| `extract_balance_sheet` | `extract_balance_sheet` | Community 2 | `clean_ticker`, `get_screener_metadata` |
| `extract_cash_flow` | `extract_cash_flow` | Community 2 | same |
| `extract_profit_loss` | `extract_profit_loss` | Community 22 | same |
| `extract_quarterly` | `extract_quarterly_results` | Community 2 | same |
| `extract_earnings` | `extract_earnings_estimates`, etc. | Community 2 | same |
| `load_balance_sheet` | `load_balance_sheet` | Community 8 | `extract_balance_sheet` |
| `load_cash_flow` | `load_cash_flow` | Community 6 | `extract_cash_flow` |
| `load_profit_loss` | `load_profit_loss` | Community 9 | `extract_profit_loss` |
| `load_quarterly` | `load_quarterly_results` | Community 10 | `extract_quarterly` |
| `load_earnings` | `load_earnings_estimates`, etc. | Community 3 | `extract_earnings` |
| `load_growth` | `load_growth_metrics` | Community 13 | depends on PL/BS |
| `load_corporate_actions` | `load_corporate_actions` | Community 18 | from yfinance extract |
| `load_technicals` | `load_technicals` | Community 11 | from price extract |
| `load_ownership` | `load_ownership` | Community 127‑129 | from screener/NSE |
| `rebuild_derived_cashflow` | `rebuild_annual_cashflow_derived` | Community 116 | after `load_cash_flow` & `load_profit_loss` |
| `dedup_tables` | `run_all_dedup` | Community 1 | after all loads for a ticker |
| `validate_completeness` | `log_data_quality`, `audit_table` | Community 1 | after loads |

> **Note**: The `_load_result()` dispatcher will be removed – each load task is called explicitly.

### 2.4 Handling Document Pipeline

The document DAG (`document_etl_dag`) maps:

| Task | Function | Community |
|------|----------|-----------|
| `fetch_doc_list` | `extract_documents()` / `extract_concalls()` | 5 |
| `classify_doc` | `classify_doc()` | 5 |
| `download_pdf` | `download_pdf()` | 5 (community 44) |
| `upload_to_minio` | `upload_document()` | (from community 44) |
| `store_metadata` | (custom) | – |

Use Airflow `TaskGroup` for per‑document parallelisation.

## 3. Production‑Grade Configuration

### 3.1 Connections (Airflow UI / CLI)

Create the following connections:

- `mysql_default` – Type: MySQL, with host, port, database, login, password.
- `minio_default` – Type: S3 (with MinIO endpoint URL, access key, secret).
- `screener_api` – Type: HTTP (base URL `https://www.screener.in`, no auth needed).
- `yfinance` – No connection required (direct library call).

### 3.2 Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `daily_tickers` | `["RELIANCE", "TCS", "HDFC"]` | List of symbols for stock DAG |
| `max_parallel_tickers` | `4` | Airflow parallelism level |
| `screener_retry_attempts` | `3` | Retry for Screener HTTP calls |
| `enable_minio_upload` | `True` | Toggle document storage |
| `data_quality_threshold` | `0.95` | Acceptable completeness ratio |

### 3.3 Idempotency & Retry

- **Extract tasks**: use `GET` with `allow_redirects`; store raw response JSON as XCom or in MinIO.
- **Load tasks**: use `INSERT … ON DUPLICATE KEY UPDATE` (already present in many `_loader.py` modules – verified from community 18, 106, etc.).
- **Airflow retry**: `retries=3, retry_delay=timedelta(minutes=2)` on every task.

### 3.4 Monitoring & Alerts

- **Data quality** – after each load task, call `compute_completeness()` (community 1) and check against `data_quality_threshold`. Fail task if below threshold.
- **Airflow callbacks** – send failure alerts to Slack/PagerDuty via `on_failure_callback`.
- **Task duration** – track with Airflow metrics; add `sla=timedelta(minutes=30)` for critical tasks.

## 4. Example DAG Definition

Below is a simplified version of `stock_etl_dag`. The full implementation would use `DynamicTaskMapping` or `expand()` to process multiple tickers in parallel.

```python
from airflow import DAG
from airflow.decorators import task
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from airflow.models import Variable

default_args = {
    'owner': 'quant_copilot',
    'depends_on_past': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=2),
    'start_date': datetime(2025, 1, 1),
    'sla': timedelta(minutes=30),
}

@task
def clean_ticker(symbol: str):
    from etl.extract.screener import clean_ticker_for_screener
    return clean_ticker_for_screener(symbol)

@task
def get_screener_id(cleaned_symbol: str):
    from etl.extract.screener import get_screener_id_and_slug
    return get_screener_id_and_slug(cleaned_symbol)

@task
def extract_balance_sheet(symbol: str, screener_id: dict):
    from etl.extract.balance_sheet import extract_balance_sheet
    return extract_balance_sheet(symbol, screener_id)

@task
def load_balance_sheet(bs_data: dict):
    from etl.load.bs_loader import load_balance_sheet
    load_balance_sheet(bs_data)
    return "OK"

# ... similarly for cash flow, P&L, quarterly, etc.

@task
def rebuild_derived(symbol: str):
    from etl.load.cashflow_loader import rebuild_annual_cashflow_derived
    rebuild_annual_cashflow_derived(symbol)

with DAG(
    'stock_etl_dag',
    schedule='0 2 * * *',  # daily at 2 AM
    default_args=default_args,
    catchup=False,
    tags=['quant', 'etl'],
) as dag:
    symbols = Variable.get("daily_tickers", deserialize_json=True)  # list of strings

    for sym in symbols:
        cleaned = clean_ticker(sym)
        screener_id = get_screener_id(cleaned)
        bs_data = extract_balance_sheet(cleaned, screener_id)
        bs_load = load_balance_sheet(bs_data)
        # … other extracts and loads …
        derived = rebuild_derived(cleaned)

        bs_load >> derived