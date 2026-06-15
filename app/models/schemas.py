"""
app/models/schemas.py
──────────────────────
Pydantic request / response models for the Quant Copilot API.

Covers
──────
  Ingest (POST) requests & responses  — unchanged from v1
  Read    (GET) responses             — one model per DB table
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


# ═══════════════════════════════════════════════════════════════════════════════
# POST — ingest requests & responses  (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

class StockRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20,
                        description="Ticker symbol, e.g. 'RELIANCE'",
                        examples=["RELIANCE", "HDFCBANK.NS"])
    sections: Optional[List[str]] = Field(
        default=None,
        description="Section codes to run. Omit to run ALL sections.",
        examples=[["bs", "pl", "pr"]],
    )


class PipelineResponse(BaseModel):
    status: str
    symbol: str
    message: str
    sections_ok: List[str] = Field(default_factory=list)
    sections_failed: List[str] = Field(default_factory=list)


class DocRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20,
                        examples=["TCS", "RELIANCE"])


class DocIngestResponse(BaseModel):
    status: str
    symbol: str
    message: str
    total: int = 0
    uploaded: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# GET — stocks
# ═══════════════════════════════════════════════════════════════════════════════

class StockOut(BaseModel):
    symbol: str
    screener_id: Optional[int] = None
    name: Optional[str] = None
    exchange: str
    sector: Optional[str] = None
    broad_sector: Optional[str] = None
    industry: Optional[str] = None
    broad_industry: Optional[str] = None
    currency: str
    market_cap_cr: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StocksListResponse(BaseModel):
    data: List[StockOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — profit_loss
# ═══════════════════════════════════════════════════════════════════════════════

class ProfitLossOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    sales: Optional[float] = None
    expenses: Optional[float] = None
    operating_profit: Optional[float] = None
    opm_pct: Optional[float] = None
    other_income: Optional[float] = None
    interest: Optional[float] = None
    depreciation: Optional[float] = None
    profit_before_tax: Optional[float] = None
    tax_pct: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    dividend_payout_pct: Optional[float] = None
    data_source: str
    is_audited: bool
    completeness_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class ProfitLossResponse(BaseModel):
    data: List[ProfitLossOut]
    meta: PaginationMeta


class ProfitLossItemOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    parent_label: str
    item_label: str
    value: Optional[float] = None
    is_subtotal: bool
    sort_order: int
    data_source: str


class ProfitLossItemsResponse(BaseModel):
    data: List[ProfitLossItemOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — balance_sheet
# ═══════════════════════════════════════════════════════════════════════════════

class BalanceSheetOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    equity_capital: Optional[float] = None
    reserves: Optional[float] = None
    total_equity: Optional[float] = None
    borrowings: Optional[float] = None
    other_liabilities: Optional[float] = None
    total_liabilities: Optional[float] = None
    fixed_assets: Optional[float] = None
    cwip: Optional[float] = None
    investments: Optional[float] = None
    other_assets: Optional[float] = None
    inventories: Optional[float] = None
    trade_receivables: Optional[float] = None
    cash_equivalents: Optional[float] = None
    loans_advances: Optional[float] = None
    total_assets: Optional[float] = None
    net_debt: Optional[float] = None
    data_source: str
    completeness_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class BalanceSheetResponse(BaseModel):
    data: List[BalanceSheetOut]
    meta: PaginationMeta


class BalanceSheetItemOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    parent_label: str
    item_label: str
    value: Optional[float] = None
    is_subtotal: bool
    sort_order: int
    data_source: str


class BalanceSheetItemsResponse(BaseModel):
    data: List[BalanceSheetItemOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — cash_flow
# ═══════════════════════════════════════════════════════════════════════════════

class CashFlowOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    cfo: Optional[float] = None
    cfi: Optional[float] = None
    cff: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None
    net_cash_flow: Optional[float] = None
    data_source: str
    completeness_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class CashFlowResponse(BaseModel):
    data: List[CashFlowOut]
    meta: PaginationMeta


class CashFlowItemOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    period_type: str
    is_consolidated: bool
    parent_label: str
    item_label: str
    value: Optional[float] = None
    is_subtotal: bool
    sort_order: int
    data_source: str


class CashFlowItemsResponse(BaseModel):
    data: List[CashFlowItemOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — quarterly_results
# ═══════════════════════════════════════════════════════════════════════════════

class QuarterlyResultOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    is_consolidated: bool
    sales: Optional[float] = None
    expenses: Optional[float] = None
    operating_profit: Optional[float] = None
    opm_pct: Optional[float] = None
    other_income: Optional[float] = None
    interest: Optional[float] = None
    depreciation: Optional[float] = None
    profit_before_tax: Optional[float] = None
    tax_pct: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    data_source: str
    is_audited: bool
    completeness_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class QuarterlyResultsResponse(BaseModel):
    data: List[QuarterlyResultOut]
    meta: PaginationMeta


class QuarterlyResultItemOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    is_consolidated: bool
    parent_label: str
    item_label: str
    value: Optional[float] = None
    is_subtotal: bool
    sort_order: int
    data_source: str


class QuarterlyResultItemsResponse(BaseModel):
    data: List[QuarterlyResultItemOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — price_daily
# ═══════════════════════════════════════════════════════════════════════════════

class PriceDailyOut(BaseModel):
    id: int
    symbol: str
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adj_close: Optional[float] = None
    volume: Optional[int] = None
    source: str
    updated_at: Optional[datetime] = None


class PriceDailyResponse(BaseModel):
    data: List[PriceDailyOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — technical_indicators
# ═══════════════════════════════════════════════════════════════════════════════

class TechnicalIndicatorOut(BaseModel):
    id: int
    symbol: str
    date: date
    close: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_21: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
    adx_14: Optional[float] = None
    vwap_14: Optional[float] = None
    obv: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_dir: Optional[int] = None


class TechnicalsResponse(BaseModel):
    data: List[TechnicalIndicatorOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — shareholding
# ═══════════════════════════════════════════════════════════════════════════════

class ShareholdingOut(BaseModel):
    id: int
    symbol: str
    period_end: date
    promoter_pct: Optional[float] = None
    fii_pct: Optional[float] = None
    dii_pct: Optional[float] = None
    public_pct: Optional[float] = None
    government_pct: Optional[float] = None
    others_pct: Optional[float] = None
    total_institutional_pct: Optional[float] = None
    num_shareholders: Optional[int] = None
    data_source: str
    updated_at: Optional[datetime] = None


class ShareholdingResponse(BaseModel):
    data: List[ShareholdingOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — corporate_actions
# ═══════════════════════════════════════════════════════════════════════════════

class CorporateActionOut(BaseModel):
    id: int
    symbol: str
    action_date: date
    action_type: str
    value: Optional[float] = None
    notes: Optional[str] = None


class CorporateActionsResponse(BaseModel):
    data: List[CorporateActionOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — growth_metrics
# ═══════════════════════════════════════════════════════════════════════════════

class GrowthMetricsOut(BaseModel):
    id: int
    symbol: str
    as_of_date: date
    sales_cagr_10y: Optional[float] = None
    sales_cagr_5y: Optional[float] = None
    sales_cagr_3y: Optional[float] = None
    sales_ttm: Optional[float] = None
    profit_cagr_10y: Optional[float] = None
    profit_cagr_5y: Optional[float] = None
    profit_cagr_3y: Optional[float] = None
    profit_ttm: Optional[float] = None
    stock_cagr_10y: Optional[float] = None
    stock_cagr_5y: Optional[float] = None
    stock_cagr_3y: Optional[float] = None
    stock_ttm: Optional[float] = None
    roe_10y: Optional[float] = None
    roe_5y: Optional[float] = None
    roe_3y: Optional[float] = None
    roe_last: Optional[float] = None
    completeness_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class GrowthMetricsResponse(BaseModel):
    data: List[GrowthMetricsOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — eps_trend
# ═══════════════════════════════════════════════════════════════════════════════

class EpsTrendOut(BaseModel):
    id: int
    symbol: str
    snapshot_date: date
    period_code: str
    current_est: Optional[float] = None
    seven_days_ago: Optional[float] = None
    thirty_days_ago: Optional[float] = None
    sixty_days_ago: Optional[float] = None
    ninety_days_ago: Optional[float] = None
    updated_at: Optional[datetime] = None


class EpsTrendResponse(BaseModel):
    data: List[EpsTrendOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — macro tables
# ═══════════════════════════════════════════════════════════════════════════════

class RbiRatesOut(BaseModel):
    id: int
    effective_date: date
    repo_rate: Optional[float] = None
    reverse_repo: Optional[float] = None
    sdf_rate: Optional[float] = None
    msf_rate: Optional[float] = None
    bank_rate: Optional[float] = None
    crr: Optional[float] = None
    slr: Optional[float] = None
    source: Optional[str] = None


class RbiRatesResponse(BaseModel):
    data: List[RbiRatesOut]
    meta: PaginationMeta


class MarketIndexOut(BaseModel):
    id: int
    snapshot_date: date
    index_name: str
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    direction: Optional[str] = None
    updated_at: Optional[datetime] = None


class MarketIndicesResponse(BaseModel):
    data: List[MarketIndexOut]
    meta: PaginationMeta


class ForexCommodityOut(BaseModel):
    id: int
    snapshot_date: date
    instrument: str
    last_price: Optional[float] = None
    change_pct: Optional[float] = None
    updated_at: Optional[datetime] = None


class ForexCommoditiesResponse(BaseModel):
    data: List[ForexCommodityOut]
    meta: PaginationMeta


class MacroIndicatorOut(BaseModel):
    id: int
    snapshot_date: date
    indicator_name: str
    source: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    year: Optional[int] = None
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None


class MacroIndicatorsResponse(BaseModel):
    data: List[MacroIndicatorOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — documents (pdf_documents table, created by minio_init.sql)
# ═══════════════════════════════════════════════════════════════════════════════

class PdfDocumentOut(BaseModel):
    id: int
    symbol: str
    doc_type: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    minio_bucket: Optional[str] = None
    minio_key: Optional[str] = None
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PdfDocumentsResponse(BaseModel):
    data: List[PdfDocumentOut]
    meta: PaginationMeta


# ═══════════════════════════════════════════════════════════════════════════════
# GET — operational / ETL logs
# ═══════════════════════════════════════════════════════════════════════════════

class EtlRunLogOut(BaseModel):
    id: int
    symbol: str
    run_at: datetime
    script_name: str
    script_version: Optional[str] = None
    status: str
    modules_ok: Optional[str] = None
    modules_warn: Optional[str] = None
    notes: Optional[str] = None


class EtlRunLogResponse(BaseModel):
    data: List[EtlRunLogOut]
    meta: PaginationMeta


class DataQualityLogOut(BaseModel):
    id: int
    run_at: datetime
    symbol: str
    table_name: str
    rows_inserted: int
    rows_null_heavy: int
    avg_completeness: Optional[float] = None
    critical_nulls_json: Optional[Any] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class DataQualityLogResponse(BaseModel):
    data: List[DataQualityLogOut]
    meta: PaginationMeta