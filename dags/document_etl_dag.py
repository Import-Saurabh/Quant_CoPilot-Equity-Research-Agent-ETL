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


def _as_tickers(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip().upper() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return ["RELIANCE", "TCS", "HDFCBANK"]


@dag(
    dag_id="document_etl_dag",
    schedule="30 3 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["quant", "etl", "documents"],
)
def document_etl_dag():
    @task
    def list_document_tickers() -> list[str]:
        return _as_tickers(
            Variable.get(
                "document_tickers",
                default_var=["RELIANCE", "TCS", "HDFCBANK"],
                deserialize_json=True,
            )
        )

    @task
    def ingest_documents(symbol: str) -> dict:
        from app.services.pipeline_service import execute_doc_pipeline

        result = execute_doc_pipeline(symbol)
        if result["status"] == "failed":
            raise RuntimeError(result["message"])
        return result

    ingest_documents.expand(symbol=list_document_tickers())


document_etl_dag()
