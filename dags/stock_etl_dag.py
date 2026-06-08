from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.models import Variable

PROJECT_ROOT = Path("/opt/airflow/project")
if PROJECT_ROOT.exists() and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_ARGS = {
    "owner": "quant_copilot",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
}


def _as_tickers(value, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback
    if isinstance(value, str):
        return [item.strip().upper() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return fallback


def _as_sections(value, fallback: list[str]) -> list[str]:
    if value is None:
        return fallback
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return fallback


@dag(
    dag_id="stock_etl_dag",
    schedule="0 2 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["quant", "etl", "stocks"],
)
def stock_etl_dag():
    @task
    def build_work_items() -> list[dict]:
        from etl.mysql_pipeline import ALL_SECTIONS

        tickers = _as_tickers(
            Variable.get(
                "daily_tickers",
                default_var=["RELIANCE", "TCS", "HDFCBANK"],
                deserialize_json=True,
            ),
            ["RELIANCE", "TCS", "HDFCBANK"],
        )
        sections = _as_sections(
            Variable.get("daily_sections", default_var=ALL_SECTIONS, deserialize_json=True),
            list(ALL_SECTIONS),
        )
        invalid = sorted(set(sections) - set(ALL_SECTIONS))
        if invalid:
            raise ValueError(f"Invalid section code(s) in daily_sections: {invalid}")

        return [{"symbol": ticker, "sections": sections} for ticker in tickers]

    @task
    def run_stock_pipeline(work_item: dict) -> dict:
        from app.services.pipeline_service import execute_pipeline

        result = execute_pipeline(work_item["symbol"], work_item["sections"])
        if result["status"] == "failed":
            raise RuntimeError(result["message"])
        return result

    run_stock_pipeline.expand(work_item=build_work_items())


stock_etl_dag()
