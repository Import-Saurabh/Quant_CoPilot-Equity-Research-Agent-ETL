# [Quant\_CoPilot — Equity Research Agent](https://github.com/Import-Saurabh/Quant_CoPilot-Equity-Research-Agent)

**An institutional-grade, local-first multi-agent system for portfolio research, risk analysis, and equity intelligence on Nifty 500 universe.**

> "I can't run my fund without this every day." — That's the goal.

---

## What This Is

Quant CoPilot is not a stock-picker. It is not a chatbot. It is a **Portfolio Command Center** that fuses 10+ years of Nifty fundamental data with intelligent LLM agents that read, reason, and alert — so portfolio managers and equity researchers spend time on judgment, not data wrangling.

Every answer is attributed to either `Structured Database (Screener Q3 FY24)` or `Annual Report 2023, pg 47`. Attribution is the product. Trust is the addictive feature.

---

## Architecture

The system is built as a **local ETL backbone** feeding a **multi-agent LLM layer** on top of a structured SQLite/Postgres database.
<p align="center">
  <img src="images/quant_copilot_pipeline_diagram.svg" 
       alt="Quant CoPilot Pipeline Diagram" 
       width="100%">
</p>
```
Scrapper Blueprints  →  ETL Pipeline  →  Database  →  Agent Modules
  (Screener / NSE)      (Extract /          (SQLite)     (Analyst /
                         Transform /                       Risk /
                         Load)                             Quant)
```

**Key components extracted from the codebase graph:**

| Layer | Modules |
|-------|---------|
| **Data Ingestion** | `balance_sheet_scrapper`, `cashflow_scrapper`, `profit_and_loss_scrapper`, `growth_metric_scrapper`, `screener_downloader` |
| **ETL — Extract** | `fundamentals`, `earnings`, `price`, `ownership`, `cashflow`, `growth`, `macro`, `news`, `technicals`, `corporate_actions` |
| **ETL — Transform** | `financials.py`, `normalizer.py` |
| **ETL — Load** | Dedicated loader per domain: `fundamentals_loader`, `price_loader`, `ownership_loader`, `earnings_loader`, `screener_loader`, `run_log_loader`, `reconcile` |
| **Database** | `init_db`, `dedup`, `db`, `validator`, `cleanup_existing_db` (rescaling, null purges, EPS revision repair) |
| **Orchestration** | `etl/pipeline.py`, `main.py` |

---

## The Four Modules

### Module 1 — Instant Intelligence (The Daily Habit)

Natural language Q&A over a structured fundamental database with source citations. Ask in plain English; get a cited, precise answer in seconds.

**Example queries:**
- `Show me Nifty stocks with ROE > 20% and debt/equity < 0.5 where promoter holding increased last quarter.`
- `Which companies in my watchlist have reported new regulatory risk factors in the last two quarters?`

Proactive push/email alerts surface anomalies before you think to ask: liquidity crunches, sudden promoter dilution, unusual revenue divergence from sector peers.

---

### Module 2 — One-Click Deep Dives (Hours to Seconds)

**Research Note Generator** produces a PDF-ready, two-page brief per stock containing 5-year ratio sparklines, quarterly momentum tables, extracted risk factors from filings, and a structured analyst debate (Value / Growth / Risk lens). No buy/sell signal. Always cited.

**Peer Battle Cards** put a stock head-to-head against its three closest peers across 10+ metrics with spider charts. Competitive context in one click.

---

### Module 3 — Portfolio Command Center (Institutional Core)

The analytical core of the system. Operates on the full holdings list.

**Exposure Analysis** — aggregate exposure to conglomerates (Adani, Tata, Reliance entities), FX sensitivity, commodity pass-through.

**Sector and Theme Concentration** — auto-classifies holdings into sectors and emerging investment themes (EV supply chain, PLI beneficiaries, capex cycle plays) using RAG on annual reports. Warns on dangerous over-concentration before it becomes a headline.

**Risk Clustering** — groups portfolio companies by risk factor type (regulatory, forex, debt structure, litigation) extracted directly from exchange filings. Surfaces when multiple bets are actually the same underlying risk wearing different ticker symbols.

**Correlation Matrix** — 10 years of daily price data driving both price correlation and factor correlation (size, value, momentum) as a heatmap. Not just "do these stocks move together" but "why."

**Downside Scenario Sandbox** — parameterised stress test: `INR -10%, Brent +$20, rates flat`. Uses historical elasticities from structured data to project revenue, margin, and debt-servicing impact per holding. Not Monte Carlo speculation — empirical regression on actual company financials.

---

### Module 4 — Alpha Miner (Quant Street Cred)

**Factor Research Workbench** computes canonical quant factors — value, quality, momentum, low-volatility — from 10 years of fundamentals and prices across the Nifty 500 universe. Produces decile return tables and an annual rebalance backtest. This is empirical, not conversational: the output is a factor exposure table and a performance attribution, not a narrative.

---

## What Is Explicitly Not Included

To keep the system credible:

- No stock-picking signals or mock P&L
- No verbose agent chat logs as default UI
- No supply chain speculative simulations
- No intraday or minute-level technical analysis
- No manual file upload front-end — the ETL engine runs silently on a schedule

---

## Project Structure

```
Quant_CoPilot-Equity-Research-Agent/
│
├── main.py                          # Orchestration entry point
│
├── Scrapper_Blueprints/             # Data acquisition layer
│   ├── balance_sheet_scrapper.py
│   ├── cashflow_scrapper.py
│   ├── growth_metric_scrapper.py
│   ├── profit_and_loss_scrapper.py
│   ├── screener_downloader.py
│   └── test.py                      # Scraper integration tests
│
├── etl/                             # Extract → Transform → Load pipeline
│   ├── pipeline.py                  # Pipeline orchestrator
│   ├── extract/                     # Domain-specific extractors
│   │   ├── fundamentals.py
│   │   ├── earnings.py
│   │   ├── price.py
│   │   ├── ownership.py
│   │   ├── cashflow.py
│   │   ├── growth.py
│   │   ├── macro.py
│   │   ├── news.py
│   │   ├── technicals.py
│   │   ├── corporate_actions.py
│   │   └── ...
│   ├── transform/
│   │   ├── financials.py            # Ratio computation, normalization
│   │   └── normalizer.py
│   └── load/                        # Loaders per domain table
│       ├── fundamentals_loader.py
│       ├── price_loader.py
│       ├── ownership_loader.py
│       ├── earnings_loader.py
│       ├── reconcile.py
│       └── ...
│
└── database/                        # DB bootstrap and maintenance
    ├── db.py                        # Connection management
    ├── init_db.py                   # Schema creation
    ├── dedup.py                     # Cross-table deduplication
    ├── validator.py                 # Data quality checks
    └── Cleanup_existing db.py       # EPS blob repair, price rescaling, null purges
```

---

## Setup

```bash
git clone https://github.com/Import-Saurabh/Quant_CoPilot-Equity-Research-Agent.git
cd Quant_CoPilot-Equity-Research-Agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Initialise the database schema
python -m database.init_db

# Run the full ETL pipeline
python main.py
```

An `.env` file is expected at project root with your Screener.in credentials and API keys. See `.env.example` for the required variables.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Database | SQLite (local) / PostgreSQL (production) |
| Data sources | Screener.in, NSE, Moneycontrol (via scrapers) |
| LLM layer | Anthropic Claude / OpenAI (configurable) |
| RAG | LangChain / LlamaIndex over annual report PDFs |
| Factor engine | pandas, numpy, scipy |
| Visualization | Matplotlib, Plotly |
| Orchestration | Python, custom ETL pipeline |

---

## Design Principles

**Local-first** — your portfolio data and research never leave your machine. The LLM calls go out; your holdings do not.

**Attribution by default** — every agent output is anchored to a data source. The system refuses to answer without a citation. Hallucination is structurally harder when every claim needs a page number.

**No signals, only analysis** — the system tells you what the data says, not what to do. The PM makes the decision; the agent does the legwork.

**Extensible by design** — new data domains plug in as an extractor + transformer + loader triple. New agent capabilities are additive, not surgical.

---

## Why This Exists

For a quant firm, this demonstrates understanding of not just AI, but how PMs and analysts actually manage risk, construct portfolios, and consume research — and the ability to build systems they depend on daily.

The gap between "LLM can summarise filings" and "institution trusts this system to run morning risk review" is entirely about data architecture, attribution, and the right things being left out.

---

## License

MIT