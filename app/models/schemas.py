"""
schemas.py
──────────
Pydantic request / response models for the Quant Copilot API.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────────────

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
            "Valid codes: sm bs pl cf qr sh gm pr ti eh ee et er mc ca. "
            "Omit (or pass null) to run ALL sections."
        ),
        examples=[["bs", "pl", "pr"]],
    )


# ── Response ──────────────────────────────────────────────────────────────────

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