"""
pipeline_service.py
───────────────────
Thin service layer that bridges the FastAPI layer to both ETL pipelines:

  • execute_pipeline()     → MySQL financial data ETL  (Screener + yfinance)
  • execute_doc_pipeline() → PDF document ingestion    (Screener → MinIO → MySQL)
"""

import logging
from typing import List, Optional

from etl.mysql_pipeline import (
    ALL_SECTIONS,
    SECTION_LABELS,
    run_pipeline,
)
from etl.extract.balance_sheet_extractor import clean_ticker_for_screener
from etl.services.doc_pipeline_service import run_doc_pipeline

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Financial data ETL  (unchanged from v1)
# ─────────────────────────────────────────────────────────────────────────────

def execute_pipeline(
    symbol: str,
    sections: Optional[List[str]] = None,
) -> dict:
    """
    Execute the MySQL ETL pipeline for *symbol*.

    Parameters
    ----------
    symbol   : Raw ticker string, e.g. "RELIANCE", "HDFCBANK.NS"
    sections : Optional list of section codes to run.
               Must be a subset of mysql_pipeline.ALL_SECTIONS.
               Defaults to ALL_SECTIONS when None or empty.

    Returns
    -------
    dict compatible with PipelineResponse schema:
        status   – "success" | "partial" | "failed"
        symbol   – normalised ticker (uppercase, stripped)
        message  – human-readable summary
        sections_ok     – list of section codes that loaded successfully
        sections_failed – list of section codes that failed
    """
    # ── 1. Normalise symbol ───────────────────────────────────────────────
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker symbol cannot be empty.")

    # ── 2. Resolve section list ──────────────────────────────────────────
    if not sections:
        resolved_sections = ALL_SECTIONS
    else:
        invalid = [s for s in sections if s not in ALL_SECTIONS]
        if invalid:
            raise ValueError(
                f"Invalid section code(s): {invalid}. "
                f"Valid codes are: {ALL_SECTIONS}"
            )
        resolved_sections = sections

    # ── 3. Run the pipeline ───────────────────────────────────────────────
    logger.info("Starting pipeline for %s | sections=%s", symbol, resolved_sections)

    result = run_pipeline(symbol, resolved_sections)

    # ── 4. run_pipeline returns { "success": [...], "failed": [...] } ─────
    sections_ok     = result.get("success", [])
    sections_failed = result.get("failed",  [])

    # ── 5. Derive overall status ─────────────────────────────────────────
    if sections_failed and sections_ok:
        status = "partial"
    elif sections_failed and not sections_ok:
        status = "failed"
    else:
        status = "success"

    ok_labels     = [SECTION_LABELS[s] for s in sections_ok]
    failed_labels = [SECTION_LABELS[s] for s in sections_failed]

    message_parts = [f"Pipeline finished for {symbol}."]
    if ok_labels:
        message_parts.append(f"OK: {ok_labels}.")
    if failed_labels:
        message_parts.append(f"Failed: {failed_labels}.")
    message = " ".join(message_parts)

    logger.info(
        "Pipeline %s for %s | ok=%s failed=%s",
        status, symbol, sections_ok, sections_failed,
    )

    return {
        "status":           status,
        "symbol":           symbol,
        "message":          message,
        "sections_ok":      sections_ok,
        "sections_failed":  sections_failed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Document ingestion pipeline  (Screener → MinIO → MySQL)
# ─────────────────────────────────────────────────────────────────────────────

def execute_doc_pipeline(symbol: str) -> dict:
    """
    Scrape Screener.in for annual reports & concall transcripts,
    upload each PDF to MinIO, and save metadata to MySQL pdf_documents.

    Parameters
    ----------
    symbol : Raw ticker string, e.g. "TCS", "RELIANCE".

    Returns
    -------
    dict compatible with DocIngestResponse schema:
        status   – "success" | "partial" | "failed"
        symbol   – normalised ticker
        message  – human-readable summary
        total    – total docs found on Screener.in
        uploaded – list of MinIO object paths that succeeded
        failed   – list of document titles that could not be processed
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker symbol cannot be empty.")

    logger.info("Starting document ingestion for %s", symbol)

    result = run_doc_pipeline(symbol)

    logger.info(
        "Doc pipeline %s for %s | uploaded=%d failed=%d",
        result["status"],
        symbol,
        len(result["uploaded"]),
        len(result["failed"]),
    )

    return result