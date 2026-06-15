"""
app/api/routes.py
─────────────────
FastAPI router for the Quant Copilot Equity Research API.

Write endpoints (POST)
──────────────────────
  POST /ingest          — MySQL financial-data ETL for a stock
  POST /ingest-docs     — Scrape Screener.in PDFs → MinIO + MySQL metadata

Read endpoints (GET) — one per table
─────────────────────────────────────
  Stocks
    GET /stocks                              — list all stocks
    GET /stocks/{symbol}                     — single stock detail

  Financials  (all support ?period_type, ?consolidated, ?limit, ?offset)
    GET /stocks/{symbol}/profit-loss         — profit_loss rows
    GET /stocks/{symbol}/profit-loss/items   — profit_loss_items rows
    GET /stocks/{symbol}/balance-sheet       — balance_sheet rows
    GET /stocks/{symbol}/balance-sheet/items — balance_sheet_items rows
    GET /stocks/{symbol}/cash-flow           — cash_flow rows
    GET /stocks/{symbol}/cash-flow/items     — cash_flow_items rows
    GET /stocks/{symbol}/quarterly           — quarterly_results rows
    GET /stocks/{symbol}/quarterly/items     — quarterly_results_items rows

  Market data
    GET /stocks/{symbol}/price               — price_daily  (?from, ?to, ?limit)
    GET /stocks/{symbol}/technicals          — technical_indicators

  Ownership
    GET /stocks/{symbol}/shareholding        — shareholding pattern
    GET /stocks/{symbol}/corporate-actions   — dividends / splits / bonuses

  Growth & estimates
    GET /stocks/{symbol}/growth              — growth_metrics
    GET /stocks/{symbol}/eps-trend           — eps_trend

  Documents
    GET /stocks/{symbol}/documents           — pdf_documents (?doc_type)

  Macro  (no symbol filter)
    GET /macro/rbi-rates                     — rbi_rates
    GET /macro/indices                       — market_indices  (?index_name)
    GET /macro/forex                         — forex_commodities  (?instrument)
    GET /macro/indicators                    — macro_indicators  (?indicator_name)

  Operational
    GET /ops/etl-logs                        — etl_run_log  (?symbol)
    GET /ops/quality-logs                    — data_quality_log  (?symbol, ?table_name)
"""

from __future__ import annotations

import logging
from typing import List, Optional

import mysql.connector
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.db.connection import get_cursor
from app.models.schemas import (
    # ingest
    DocRequest, DocIngestResponse, StockRequest, PipelineResponse,
    # stocks
    StockOut, StocksListResponse,
    # financials
    ProfitLossResponse, ProfitLossItemsResponse,
    BalanceSheetResponse, BalanceSheetItemsResponse,
    CashFlowResponse, CashFlowItemsResponse,
    QuarterlyResultsResponse, QuarterlyResultItemsResponse,
    # market
    PriceDailyResponse, TechnicalsResponse,
    # ownership
    ShareholdingResponse, CorporateActionsResponse,
    # growth
    GrowthMetricsResponse, EpsTrendResponse,
    # documents
    PdfDocumentsResponse,
    # macro
    RbiRatesResponse, MarketIndicesResponse,
    ForexCommoditiesResponse, MacroIndicatorsResponse,
    # ops
    EtlRunLogResponse, DataQualityLogResponse,
    PaginationMeta,
)
from app.services.pipeline_service import execute_pipeline, execute_doc_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _paginate(limit: int, offset: int):
    """Clamp pagination params to sane bounds."""
    return max(1, min(limit, 500)), max(0, offset)


def _run(sql: str, params: tuple = ()) -> list[dict]:
    """Execute *sql* with *params* and return all rows as dicts."""
    try:
        with get_cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except mysql.connector.Error as exc:
        logger.error("DB error: %s | sql=%s", exc, sql)
        raise HTTPException(status_code=500, detail=f"Database error: {exc.msg}")


def _one(sql: str, params: tuple = ()) -> dict | None:
    rows = _run(sql, params)
    return rows[0] if rows else None


def _count(table: str, where_sql: str, params: tuple) -> int:
    row = _one(f"SELECT COUNT(*) AS n FROM {table} {where_sql}", params)
    return row["n"] if row else 0


def _require_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="Symbol cannot be empty.")
    return sym


def _stock_must_exist(symbol: str) -> None:
    row = _one("SELECT 1 FROM stocks WHERE symbol = %s", (symbol,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found.")


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["ops"], summary="Liveness probe")
def health_check():
    return {"status": "healthy"}


# ─────────────────────────────────────────────────────────────────────────────
# POST — financial ETL
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=PipelineResponse,
    tags=["pipeline"],
    summary="Run MySQL financial ETL for a stock",
)
def ingest_stock(payload: StockRequest, request: Request):
    logger.info("POST /ingest symbol=%s sections=%s", payload.symbol, payload.sections)
    try:
        result = execute_pipeline(payload.symbol, payload.sections)
        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /ingest for %s", payload.symbol)
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# POST — document ingestion
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/ingest-docs",
    response_model=DocIngestResponse,
    tags=["documents"],
    summary="Scrape & upload PDFs to MinIO for a stock",
)
def ingest_docs(payload: DocRequest, request: Request):
    logger.info("POST /ingest-docs symbol=%s", payload.symbol)
    try:
        result = execute_doc_pipeline(payload.symbol)
        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in /ingest-docs for %s", payload.symbol)
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# GET — STOCKS MASTER
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks",
    response_model=StocksListResponse,
    tags=["stocks"],
    summary="List all stocks",
)
def list_stocks(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    exchange: Optional[str] = Query(None, description="Filter by exchange (NSE/BSE)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    where_clauses, params = [], []

    if sector:
        where_clauses.append("sector = %s")
        params.append(sector)
    if exchange:
        where_clauses.append("exchange = %s")
        params.append(exchange.upper())

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    total = _count("stocks", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM stocks {where_sql} ORDER BY symbol LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return StocksListResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/stocks/{symbol}",
    response_model=StockOut,
    tags=["stocks"],
    summary="Get single stock detail",
)
def get_stock(symbol: str):
    symbol = _require_symbol(symbol)
    row = _one("SELECT * FROM stocks WHERE symbol = %s", (symbol,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found.")
    return row


# ═════════════════════════════════════════════════════════════════════════════
# GET — PROFIT & LOSS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/profit-loss",
    response_model=ProfitLossResponse,
    tags=["financials"],
    summary="Profit & Loss statements",
)
def get_profit_loss(
    symbol: str,
    period_type: Optional[str] = Query(None, description="annual | quarterly | ttm"),
    consolidated: Optional[bool] = Query(None, description="True = consolidated"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if consolidated is not None:
        clauses.append("is_consolidated = %s")
        params.append(int(consolidated))

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("profit_loss", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM profit_loss {where_sql} "
        f"ORDER BY period_end DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return ProfitLossResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/stocks/{symbol}/profit-loss/items",
    response_model=ProfitLossItemsResponse,
    tags=["financials"],
    summary="Profit & Loss expandable sub-items",
)
def get_profit_loss_items(
    symbol: str,
    period_type: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    parent_label: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if period_end:
        clauses.append("period_end = %s")
        params.append(period_end)
    if parent_label:
        clauses.append("parent_label = %s")
        params.append(parent_label)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("profit_loss_items", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM profit_loss_items {where_sql} "
        f"ORDER BY period_end DESC, sort_order LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return ProfitLossItemsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — BALANCE SHEET
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/balance-sheet",
    response_model=BalanceSheetResponse,
    tags=["financials"],
    summary="Balance sheet statements",
)
def get_balance_sheet(
    symbol: str,
    period_type: Optional[str] = Query(None, description="annual | quarterly"),
    consolidated: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if consolidated is not None:
        clauses.append("is_consolidated = %s")
        params.append(int(consolidated))

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("balance_sheet", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM balance_sheet {where_sql} "
        f"ORDER BY period_end DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return BalanceSheetResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/stocks/{symbol}/balance-sheet/items",
    response_model=BalanceSheetItemsResponse,
    tags=["financials"],
    summary="Balance sheet expandable sub-items",
)
def get_balance_sheet_items(
    symbol: str,
    period_type: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    parent_label: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if period_end:
        clauses.append("period_end = %s")
        params.append(period_end)
    if parent_label:
        clauses.append("parent_label = %s")
        params.append(parent_label)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("balance_sheet_items", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM balance_sheet_items {where_sql} "
        f"ORDER BY period_end DESC, sort_order LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return BalanceSheetItemsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — CASH FLOW
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/cash-flow",
    response_model=CashFlowResponse,
    tags=["financials"],
    summary="Cash flow statements",
)
def get_cash_flow(
    symbol: str,
    period_type: Optional[str] = Query(None, description="annual | quarterly | ttm"),
    consolidated: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if consolidated is not None:
        clauses.append("is_consolidated = %s")
        params.append(int(consolidated))

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("cash_flow", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM cash_flow {where_sql} "
        f"ORDER BY period_end DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return CashFlowResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/stocks/{symbol}/cash-flow/items",
    response_model=CashFlowItemsResponse,
    tags=["financials"],
    summary="Cash flow expandable sub-items",
)
def get_cash_flow_items(
    symbol: str,
    period_type: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    parent_label: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_type:
        clauses.append("period_type = %s")
        params.append(period_type)
    if period_end:
        clauses.append("period_end = %s")
        params.append(period_end)
    if parent_label:
        clauses.append("parent_label = %s")
        params.append(parent_label)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("cash_flow_items", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM cash_flow_items {where_sql} "
        f"ORDER BY period_end DESC, sort_order LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return CashFlowItemsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — QUARTERLY RESULTS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/quarterly",
    response_model=QuarterlyResultsResponse,
    tags=["financials"],
    summary="Quarterly results",
)
def get_quarterly_results(
    symbol: str,
    consolidated: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if consolidated is not None:
        clauses.append("is_consolidated = %s")
        params.append(int(consolidated))

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("quarterly_results", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM quarterly_results {where_sql} "
        f"ORDER BY period_end DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return QuarterlyResultsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/stocks/{symbol}/quarterly/items",
    response_model=QuarterlyResultItemsResponse,
    tags=["financials"],
    summary="Quarterly results expandable sub-items",
)
def get_quarterly_items(
    symbol: str,
    period_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    parent_label: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_end:
        clauses.append("period_end = %s")
        params.append(period_end)
    if parent_label:
        clauses.append("parent_label = %s")
        params.append(parent_label)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("quarterly_results_items", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM quarterly_results_items {where_sql} "
        f"ORDER BY period_end DESC, sort_order LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return QuarterlyResultItemsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — PRICE DAILY
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/price",
    response_model=PriceDailyResponse,
    tags=["market"],
    summary="Daily OHLCV price data",
)
def get_price(
    symbol: str,
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(252, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if from_date:
        clauses.append("date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("date <= %s")
        params.append(to_date)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("price_daily", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM price_daily {where_sql} "
        f"ORDER BY date DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return PriceDailyResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — TECHNICAL INDICATORS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/technicals",
    response_model=TechnicalsResponse,
    tags=["market"],
    summary="Technical indicators (RSI, MACD, Bollinger, etc.)",
)
def get_technicals(
    symbol: str,
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(252, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if from_date:
        clauses.append("date >= %s")
        params.append(from_date)
    if to_date:
        clauses.append("date <= %s")
        params.append(to_date)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("technical_indicators", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM technical_indicators {where_sql} "
        f"ORDER BY date DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return TechnicalsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — SHAREHOLDING
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/shareholding",
    response_model=ShareholdingResponse,
    tags=["ownership"],
    summary="Shareholding pattern (promoter / FII / DII / public)",
)
def get_shareholding(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    where_sql = "WHERE symbol = %s"
    total = _count("shareholding", where_sql, (symbol,))
    rows = _run(
        f"SELECT * FROM shareholding {where_sql} "
        f"ORDER BY period_end DESC LIMIT %s OFFSET %s",
        (symbol, limit, offset),
    )
    return ShareholdingResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — CORPORATE ACTIONS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/corporate-actions",
    response_model=CorporateActionsResponse,
    tags=["ownership"],
    summary="Corporate actions — dividends, splits, bonuses",
)
def get_corporate_actions(
    symbol: str,
    action_type: Optional[str] = Query(None, description="dividend | split | bonus | ..."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if action_type:
        clauses.append("action_type = %s")
        params.append(action_type)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("corporate_actions", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM corporate_actions {where_sql} "
        f"ORDER BY action_date DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return CorporateActionsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — GROWTH METRICS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/growth",
    response_model=GrowthMetricsResponse,
    tags=["growth"],
    summary="Sales / profit / stock CAGR and ROE metrics",
)
def get_growth_metrics(
    symbol: str,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    where_sql = "WHERE symbol = %s"
    total = _count("growth_metrics", where_sql, (symbol,))
    rows = _run(
        f"SELECT * FROM growth_metrics {where_sql} "
        f"ORDER BY as_of_date DESC LIMIT %s OFFSET %s",
        (symbol, limit, offset),
    )
    return GrowthMetricsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — EPS TREND
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/eps-trend",
    response_model=EpsTrendResponse,
    tags=["growth"],
    summary="EPS estimate trend (current vs 7/30/60/90 days ago)",
)
def get_eps_trend(
    symbol: str,
    period_code: Optional[str] = Query(None, description="e.g. '0q', '+1q', '0y'"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if period_code:
        clauses.append("period_code = %s")
        params.append(period_code)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("eps_trend", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM eps_trend {where_sql} "
        f"ORDER BY snapshot_date DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return EpsTrendResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — PDF DOCUMENTS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/stocks/{symbol}/documents",
    response_model=PdfDocumentsResponse,
    tags=["documents"],
    summary="Annual reports & concall transcripts stored in MinIO",
)
def get_documents(
    symbol: str,
    doc_type: Optional[str] = Query(None, description="annual_report | concall_transcript"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    symbol = _require_symbol(symbol)
    _stock_must_exist(symbol)
    limit, offset = _paginate(limit, offset)

    clauses = ["symbol = %s"]
    params: list = [symbol]
    if doc_type:
        clauses.append("doc_type = %s")
        params.append(doc_type)

    where_sql = "WHERE " + " AND ".join(clauses)
    total = _count("pdf_documents", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM pdf_documents {where_sql} "
        f"ORDER BY year DESC, created_at DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return PdfDocumentsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — MACRO: RBI RATES
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/macro/rbi-rates",
    response_model=RbiRatesResponse,
    tags=["macro"],
    summary="RBI policy rates — repo, reverse repo, CRR, SLR, etc.",
)
def get_rbi_rates(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    total = _count("rbi_rates", "", ())
    rows = _run(
        "SELECT * FROM rbi_rates ORDER BY effective_date DESC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    return RbiRatesResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — MACRO: MARKET INDICES
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/macro/indices",
    response_model=MarketIndicesResponse,
    tags=["macro"],
    summary="Market index snapshots — NIFTY50, SENSEX, etc.",
)
def get_market_indices(
    index_name: Optional[str] = Query(None, description="e.g. 'NIFTY 50'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    clauses, params = [], []
    if index_name:
        clauses.append("index_name = %s")
        params.append(index_name)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = _count("market_indices", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM market_indices {where_sql} "
        f"ORDER BY snapshot_date DESC, index_name LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return MarketIndicesResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — MACRO: FOREX / COMMODITIES
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/macro/forex",
    response_model=ForexCommoditiesResponse,
    tags=["macro"],
    summary="Forex & commodity prices — USD/INR, Gold, Crude, etc.",
)
def get_forex_commodities(
    instrument: Optional[str] = Query(None, description="e.g. 'USD/INR'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    clauses, params = [], []
    if instrument:
        clauses.append("instrument = %s")
        params.append(instrument)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = _count("forex_commodities", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM forex_commodities {where_sql} "
        f"ORDER BY snapshot_date DESC, instrument LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return ForexCommoditiesResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — MACRO: MACRO INDICATORS
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/macro/indicators",
    response_model=MacroIndicatorsResponse,
    tags=["macro"],
    summary="Macro indicators — GDP, CPI, IIP, WPI, etc.",
)
def get_macro_indicators(
    indicator_name: Optional[str] = Query(None, description="e.g. 'CPI'"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    clauses, params = [], []
    if indicator_name:
        clauses.append("indicator_name = %s")
        params.append(indicator_name)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = _count("macro_indicators", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM macro_indicators {where_sql} "
        f"ORDER BY snapshot_date DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return MacroIndicatorsResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — OPS: ETL RUN LOG
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/ops/etl-logs",
    response_model=EtlRunLogResponse,
    tags=["ops"],
    summary="ETL run log — per-symbol pipeline execution history",
)
def get_etl_logs(
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    status: Optional[str] = Query(None, description="ok | warn | error"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    clauses, params = [], []
    if symbol:
        clauses.append("symbol = %s")
        params.append(symbol.strip().upper())
    if status:
        clauses.append("status = %s")
        params.append(status)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = _count("etl_run_log", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM etl_run_log {where_sql} "
        f"ORDER BY run_at DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return EtlRunLogResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


# ═════════════════════════════════════════════════════════════════════════════
# GET — OPS: DATA QUALITY LOG
# ═════════════════════════════════════════════════════════════════════════════

@router.get(
    "/ops/quality-logs",
    response_model=DataQualityLogResponse,
    tags=["ops"],
    summary="Data quality log — completeness & null-heavy rows per ETL run",
)
def get_quality_logs(
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    table_name: Optional[str] = Query(None, description="Filter by table name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    limit, offset = _paginate(limit, offset)
    clauses, params = [], []
    if symbol:
        clauses.append("symbol = %s")
        params.append(symbol.strip().upper())
    if table_name:
        clauses.append("table_name = %s")
        params.append(table_name)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total = _count("data_quality_log", where_sql, tuple(params))
    rows = _run(
        f"SELECT * FROM data_quality_log {where_sql} "
        f"ORDER BY run_at DESC LIMIT %s OFFSET %s",
        (*params, limit, offset),
    )
    return DataQualityLogResponse(
        data=rows,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )