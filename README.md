## Architecture

The system is built as a modular **FastAPI + ETL + MySQL** architecture designed for institutional-grade equity research workflows.

A structured ETL backbone continuously ingests and normalizes financial data, which is then exposed through API services and consumed by downstream LLM agents, research modules, and portfolio analytics systems.

<p align="center">
  <img src="images/quant_copilot_pipeline_diagram.svg" 
       alt="Quant CoPilot Pipeline Diagram" 
       width="100%">
</p>

```text
        FastAPI Backend
               │
               ▼
        Service Layer
               │
               ▼
        ETL Orchestrator
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Extract    Transform     Load
               │
               ▼
          MySQL Database
               │
               ▼
        Agent / Research Layer
```

### Key Components Extracted from the Codebase Graph

| Layer                          | Modules                                                                                                                                                                                                                           |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **API Layer**                  | `app/main.py`, `api/routes.py`, `services/pipeline_service.py`, `models/schemas.py`                                                                                                                                               |
| **ETL — Extract**              | `balance_sheet_extractor`, `profit_and_loss`, `cash_flow_mysql`, `quarterly_result_mysql`, `growth_metrcis`, `shareholding_mysql`, `stocks_mysql`, `earnings`, `macro_mysql`, `corporate_actions`                                 |
| **ETL — Transform**            | `financials.py`, `normalizer.py`                                                                                                                                                                                                  |
| **ETL — Load**                 | `bs_loader`, `pl_loader`, `cf_loader`, `qr_loader`, `gm_loader`, `sh_loader`, `ca_loader`, `earnings_loader_mysql`, `macro_loader_mysql`, `price_loader_mysql`, `stocks_loader_mysql`, `technical_loader_mysql`, `run_log_loader` |
| **Database Infrastructure**    | `db_mysql`, `init_db_mysql`, `dedup_mysql`, `validator_mysql`, `mysql_schema_v2.sql`                                                                                                                                              |
| **Pipeline Orchestration**     | `etl/mysql_pipeline.py`, `pipeline_service.py`                                                                                                                                                                                    |
| **Architecture Visualization** | `graphify-out/graph.html`, `graphify-out/graph.json`, `GRAPH_REPORT.md`                                                                                                                                                           |
| **Containerization**           | `Dockerfile`, `docker-compose.yml`                                                                                                                                                                                                |

---

## Project Structure

```text
Quant_CoPilot-Equity-Research-Agent/
│
├── app/                                      # FastAPI application layer
│   │
│   ├── main.py                               # FastAPI entry point
│   ├── __init__.py
│   │
│   ├── api/                                  # API route layer
│   │   ├── routes.py                         # REST endpoints
│   │   └── __init__.py
│   │
│   ├── services/                             # Business logic / orchestration
│   │   ├── pipeline_service.py               # Triggers ETL workflows
│   │   └── __init__.py
│   │
│   ├── models/                               # Request/response schemas
│   │   ├── schemas.py
│   │   └── __init__.py
│   │
│   ├── core/                                 # Config, constants, security
│   │
│   └── utils/                                # Shared utility helpers
│
├── etl/                                      # ETL pipeline layer
│   │
│   ├── mysql_pipeline.py                     # Main ETL orchestrator
│   ├── __init__.py
│   │
│   ├── extract/                              # Data extraction modules
│   │   ├── balance_sheet_extractor.py
│   │   ├── profit_and_loss.py
│   │   ├── cash_flow_mysql.py
│   │   ├── quarterly_result_mysql.py
│   │   ├── growth_metrcis.py
│   │   ├── shareholding_mysql.py
│   │   ├── stocks_mysql.py
│   │   ├── earnings.py
│   │   ├── macro_mysql.py
│   │   ├── corporate_actions.py
│   │   └── __init__.py
│   │
│   ├── transform/                            # Data normalization & metrics
│   │   ├── financials.py
│   │   └── normalizer.py
│   │
│   └── load/                                 # Database loading layer
│       ├── bs_loader.py
│       ├── pl_loader.py
│       ├── cf_loader.py
│       ├── qr_loader.py
│       ├── gm_loader.py
│       ├── sh_loader.py
│       ├── ca_loader.py
│       ├── earnings_loader_mysql.py
│       ├── macro_loader_mysql.py
│       ├── price_loader_mysql.py
│       ├── stocks_loader_mysql.py
│       ├── technical_loader_mysql.py
│       ├── run_log_loader.py
│       └── __init__.py
│
├── database/                                 # Database infrastructure
│   ├── db_mysql.py                           # MySQL connection management
│   ├── init_db_mysql.py                      # Schema initialization
│   ├── dedup_mysql.py                        # Deduplication utilities
│   ├── validator_mysql.py                    # Data quality validation
│   ├── mysql_schema_v2.sql                   # Main production schema
│   └── __init__.py
│
├── graphify-out/                             # Architecture dependency graph
│   ├── graph.html
│   ├── graph.json
│   └── GRAPH_REPORT.md
│
├── images/
│   └── quant_copilot_pipeline_diagram.svg
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── .dockerignore
└── .gitignore
```

---

## Setup

```bash
git clone https://github.com/Import-Saurabh/Quant_CoPilot-Equity-Research-Agent.git

cd Quant_CoPilot-Equity-Research-Agent

python -m venv .venv

# Linux / Mac
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

# Initialise MySQL schema
python -m database.init_db_mysql

# Run FastAPI backend
uvicorn app.main:app --reload
```

---

## Tech Stack

| Component             | Technology             |
| --------------------- | ---------------------- |
| Backend API           | FastAPI                |
| Database              | MySQL                  |
| ETL Engine            | Python                 |
| Data Sources          | Screener.in, NSE       |
| Data Processing       | pandas, numpy          |
| Containerization      | Docker, Docker Compose |
| Architecture Analysis | Graphify               |
| Visualization         | Matplotlib, Plotly     |
| LLM Layer             | OpenAI / Anthropic     |
| Future Orchestration  | Apache Airflow         |
