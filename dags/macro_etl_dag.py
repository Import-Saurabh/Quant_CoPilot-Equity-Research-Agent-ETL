from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

PROJECT_ROOT = Path("/opt/airflow/project")
if PROJECT_ROOT.exists() and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_ARGS = {
    "owner": "quant_copilot",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
}


@dag(
    dag_id="macro_etl_dag",
    schedule="0 4 * * 1",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    max_active_runs=1,
    tags=["quant", "etl", "macro"],
)
def macro_etl_dag():
    @task
    def refresh_macro_data() -> dict:
        from app.services.pipeline_service import execute_pipeline

        result = execute_pipeline("MACRO", ["mc"])
        if result["status"] == "failed":
            raise RuntimeError(result["message"])
        return result

    refresh_macro_data()


macro_etl_dag()
