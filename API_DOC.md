# Quant Copilot — Read API Reference & Commands

## File placement

```
your_project/
├── app/
│   ├── db/
│   │   └── connection.py     ← NEW  (drop in here)
│   ├── models/
│   │   └── schemas.py        ← REPLACE
│   └── api/
│       └── routes.py         ← REPLACE
```

---

## Start the stack

```powershell
# First time (builds the image + runs migrations)
docker compose up --build -d

# Subsequent starts
docker compose up -d

# With Adminer (DB GUI on :8080) and MinIO Console (on :9001)
docker compose --profile tools up -d

# Tail logs
docker compose logs -f api
docker compose logs -f db
```

---

## Stop / rebuild after code changes

```powershell
docker compose down
docker compose up --build -d
```

---

## Swagger UI

```
http://localhost:8000/docs
```

All 24 endpoints are listed there with try-it-out support.

---

## curl quick-reference  (all GETs)

### Stocks
```bash
# List all stocks
curl "http://localhost:8000/api/v1/stocks"

# Filter by sector with pagination
curl "http://localhost:8000/api/v1/stocks?sector=Banking&limit=10&offset=0"

# Single stock
curl "http://localhost:8000/api/v1/stocks/HDFCBANK"
```

### Financials
```bash
# Annual P&L (last 10 years)
curl "http://localhost:8000/api/v1/stocks/RELIANCE/profit-loss?period_type=annual&limit=10"

# Quarterly P&L
curl "http://localhost:8000/api/v1/stocks/RELIANCE/profit-loss?period_type=quarterly&limit=8"

# P&L sub-items for a specific period
curl "http://localhost:8000/api/v1/stocks/RELIANCE/profit-loss/items?period_end=2024-03-31"

# Balance sheet (annual, consolidated)
curl "http://localhost:8000/api/v1/stocks/TCS/balance-sheet?period_type=annual&consolidated=true"

# Balance sheet sub-items
curl "http://localhost:8000/api/v1/stocks/TCS/balance-sheet/items?period_end=2024-03-31&parent_label=Liabilities"

# Cash flow
curl "http://localhost:8000/api/v1/stocks/INFY/cash-flow?period_type=annual"

# Cash flow sub-items
curl "http://localhost:8000/api/v1/stocks/INFY/cash-flow/items?period_end=2024-03-31"

# Quarterly results (last 8 quarters)
curl "http://localhost:8000/api/v1/stocks/HDFCBANK/quarterly?limit=8"

# Quarterly sub-items
curl "http://localhost:8000/api/v1/stocks/HDFCBANK/quarterly/items?period_end=2024-12-31"
```

### Market Data
```bash
# Daily price (last 252 trading days = 1 year)
curl "http://localhost:8000/api/v1/stocks/NIFTY50/price?limit=252"

# Price for a date range
curl "http://localhost:8000/api/v1/stocks/RELIANCE/price?from_date=2024-01-01&to_date=2024-12-31"

# Technical indicators
curl "http://localhost:8000/api/v1/stocks/RELIANCE/technicals?limit=30"

# Technicals for a date range
curl "http://localhost:8000/api/v1/stocks/TCS/technicals?from_date=2025-01-01&to_date=2025-06-15"
```

### Ownership
```bash
# Shareholding pattern history
curl "http://localhost:8000/api/v1/stocks/RELIANCE/shareholding"

# Corporate actions (all types)
curl "http://localhost:8000/api/v1/stocks/INFY/corporate-actions"

# Only dividends
curl "http://localhost:8000/api/v1/stocks/INFY/corporate-actions?action_type=dividend"
```

### Growth & Estimates
```bash
# Growth metrics (CAGR + ROE)
curl "http://localhost:8000/api/v1/stocks/RELIANCE/growth"

# EPS estimate trend
curl "http://localhost:8000/api/v1/stocks/TCS/eps-trend"

# EPS for a specific period code
curl "http://localhost:8000/api/v1/stocks/TCS/eps-trend?period_code=0y"
```

### Documents (MinIO PDFs)
```bash
# All documents for a stock
curl "http://localhost:8000/api/v1/stocks/TCS/documents"

# Only annual reports
curl "http://localhost:8000/api/v1/stocks/TCS/documents?doc_type=annual_report"

# Only concall transcripts
curl "http://localhost:8000/api/v1/stocks/TCS/documents?doc_type=concall_transcript"
```

### Macro
```bash
# Latest RBI policy rates
curl "http://localhost:8000/api/v1/macro/rbi-rates?limit=5"

# Market indices
curl "http://localhost:8000/api/v1/macro/indices"

# Filter by index name
curl "http://localhost:8000/api/v1/macro/indices?index_name=NIFTY+50"

# Forex & commodities
curl "http://localhost:8000/api/v1/macro/forex"

# Filter by instrument
curl "http://localhost:8000/api/v1/macro/forex?instrument=USD%2FINR"

# Macro indicators
curl "http://localhost:8000/api/v1/macro/indicators"

# Filter by indicator
curl "http://localhost:8000/api/v1/macro/indicators?indicator_name=CPI"
```

### Operational / DevOps
```bash
# ETL run logs (all stocks)
curl "http://localhost:8000/api/v1/ops/etl-logs?limit=20"

# ETL logs for a specific stock
curl "http://localhost:8000/api/v1/ops/etl-logs?symbol=RELIANCE"

# Only failed runs
curl "http://localhost:8000/api/v1/ops/etl-logs?status=error"

# Data quality logs
curl "http://localhost:8000/api/v1/ops/quality-logs"

# Quality logs for a specific table
curl "http://localhost:8000/api/v1/ops/quality-logs?table_name=profit_loss&symbol=TCS"
```

### Ingest (POST — existing, unchanged)
```bash
# Run full ETL for a stock
curl -X POST "http://localhost:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "RELIANCE"}'

# Run only specific sections
curl -X POST "http://localhost:8000/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "HDFCBANK", "sections": ["bs", "pl", "pr"]}'

# Ingest PDFs
curl -X POST "http://localhost:8000/api/v1/ingest-docs" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "TCS"}'
```

---

## All 24 GET endpoints at a glance

| Tag | Path | Description |
|-----|------|-------------|
| stocks | `GET /stocks` | List all stocks |
| stocks | `GET /stocks/{symbol}` | Single stock detail |
| financials | `GET /stocks/{symbol}/profit-loss` | P&L statements |
| financials | `GET /stocks/{symbol}/profit-loss/items` | P&L sub-items |
| financials | `GET /stocks/{symbol}/balance-sheet` | Balance sheet |
| financials | `GET /stocks/{symbol}/balance-sheet/items` | BS sub-items |
| financials | `GET /stocks/{symbol}/cash-flow` | Cash flow |
| financials | `GET /stocks/{symbol}/cash-flow/items` | CF sub-items |
| financials | `GET /stocks/{symbol}/quarterly` | Quarterly results |
| financials | `GET /stocks/{symbol}/quarterly/items` | QR sub-items |
| market | `GET /stocks/{symbol}/price` | Daily OHLCV |
| market | `GET /stocks/{symbol}/technicals` | RSI / MACD / BB / etc. |
| ownership | `GET /stocks/{symbol}/shareholding` | Promoter/FII/DII/Public % |
| ownership | `GET /stocks/{symbol}/corporate-actions` | Dividends / splits |
| growth | `GET /stocks/{symbol}/growth` | CAGR + ROE metrics |
| growth | `GET /stocks/{symbol}/eps-trend` | EPS estimate revisions |
| documents | `GET /stocks/{symbol}/documents` | Annual reports & concalls |
| macro | `GET /macro/rbi-rates` | RBI policy rates |
| macro | `GET /macro/indices` | NIFTY / SENSEX snapshots |
| macro | `GET /macro/forex` | USD-INR / Gold / Crude |
| macro | `GET /macro/indicators` | GDP / CPI / IIP / WPI |
| ops | `GET /ops/etl-logs` | Pipeline run history |
| ops | `GET /ops/quality-logs` | Data completeness log |
| ops | `GET /health` | Liveness probe |

---

## Common pagination params (all list endpoints)

| Param | Default | Max | Description |
|-------|---------|-----|-------------|
| `limit` | varies | 2000 (price) | Rows per page |
| `offset` | 0 | — | Skip N rows |

Response envelope:
```json
{
  "data": [ ... ],
  "meta": { "total": 142, "limit": 20, "offset": 0 }
}
```
