"""
schemas.py
──────────
Pydantic request / response models for the Quant Copilot API.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Stock ETL request / response ──────────────────────────────────────────────

class StockRequest(BaseModel):
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Ticker symbol, e.g. 'RELIANCE', 'HDFCBANK.NS'",
        examples=["RELIANCE", "HDFCBANK.NS"],
    )
    sections: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional list of section codes to run. "
            "Valid codes: sm bs pl cf qr sh gm pr ti mc ca. "
            "Omit (or pass null) to run ALL sections."
        ),
        examples=[["bs", "pl", "pr"]],
    )


class PipelineResponse(BaseModel):
    status: str = Field(
        ...,
        description="'success' | 'partial' | 'failed'",
    )
    symbol: str = Field(..., description="Normalised ticker symbol used by the pipeline.")
    message: str = Field(..., description="Human-readable summary of the run.")
    sections_ok: List[str] = Field(
        default_factory=list,
        description="Section codes that loaded successfully.",
    )
    sections_failed: List[str] = Field(
        default_factory=list,
        description="Section codes that failed (extraction or load).",
    )


# ── Document ingestion request / response ─────────────────────────────────────

class DocRequest(BaseModel):
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description=(
            "Ticker symbol to scrape documents for, e.g. 'TCS', 'RELIANCE'. "
            "Must match a valid Screener.in company slug."
        ),
        examples=["TCS", "RELIANCE", "HDFCBANK"],
    )


class DocIngestResponse(BaseModel):
    status: str = Field(
        ...,
        description="'success' | 'partial' | 'failed'",
    )
    symbol: str = Field(
        ...,
        description="Normalised ticker symbol used during scraping.",
    )
    message: str = Field(
        ...,
        description="Human-readable summary of the document ingestion run.",
    )
    total: int = Field(
        default=0,
        description="Total number of documents found on Screener.in.",
    )
    uploaded: List[str] = Field(
        default_factory=list,
        description="MinIO object paths for PDFs that were uploaded successfully.",
        examples=[["annual-reports/tcs/2024_TCS_Annual_Report.pdf"]],
    )
    failed: List[str] = Field(
        default_factory=list,
        description="Document titles that could not be downloaded or uploaded.",
    )