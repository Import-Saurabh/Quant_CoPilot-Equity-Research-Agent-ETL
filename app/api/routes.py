"""
routes.py
─────────
FastAPI router for the Quant Copilot Equity Research API.

Endpoints
─────────
GET  /health          — liveness probe
POST /ingest          — run MySQL financial-data ETL for a stock
POST /ingest-docs     — scrape Screener.in PDFs → MinIO + MySQL metadata
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.schemas import (
    StockRequest,
    PipelineResponse,
    DocRequest,
    DocIngestResponse,
)
from app.services.pipeline_service import execute_pipeline, execute_doc_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    summary="Health check",
    tags=["ops"],
)
def health_check():
    """Lightweight liveness probe — returns 200 when the service is up."""
    return {"status": "healthy"}


# ── Financial ETL pipeline ────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=PipelineResponse,
    summary="Run MySQL financial ETL for a stock",
    tags=["pipeline"],
    responses={
        200: {"description": "Pipeline ran (all or partial sections succeeded)."},
        400: {"description": "Bad request — invalid ticker or section code."},
        422: {"description": "Request body failed Pydantic validation."},
        500: {"description": "Unexpected server-side error."},
    },
)
def ingest_stock(payload: StockRequest, request: Request):
    """
    Trigger the MySQL ETL pipeline for the given ticker symbol.

    - **symbol**: Stock ticker, e.g. `RELIANCE` or `HDFCBANK.NS`.
    - **sections**: Optional subset of sections to run.
      Valid codes: `sm bs pl cf qr sh gm pr ti eh ee et er mc ca`.
      Leave empty to run **all** sections.
    """
    logger.info(
        "POST /ingest | symbol=%s sections=%s | client=%s",
        payload.symbol,
        payload.sections,
        request.client.host if request.client else "unknown",
    )

    try:
        result = execute_pipeline(payload.symbol, payload.sections)

        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except HTTPException:
        raise

    except ValueError as exc:
        logger.warning("Bad request for symbol=%s: %s", payload.symbol, exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error running pipeline for %s", payload.symbol)
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


# ── Document ingestion pipeline ───────────────────────────────────────────────

@router.post(
    "/ingest-docs",
    response_model=DocIngestResponse,
    summary="Scrape & upload PDFs to MinIO for a stock",
    tags=["documents"],
    responses={
        200: {"description": "Document pipeline ran (all or partial uploads succeeded)."},
        400: {"description": "Bad request — invalid or empty ticker symbol."},
        422: {"description": "Request body failed Pydantic validation."},
        500: {"description": "All uploads failed or MinIO is unreachable."},
    },
)
def ingest_docs(payload: DocRequest, request: Request):
    """
    Scrape Screener.in for annual reports and concall transcripts, upload
    each PDF to MinIO, and record metadata in MySQL `pdf_documents`.

    - **symbol**: Stock ticker, e.g. `TCS`, `RELIANCE`.

    Bucket layout in MinIO:
    - `annual-reports/{symbol}/{year}_{title}.pdf`
    - `concall-transcripts/{symbol}/{year}_{title}.pdf`
    """
    logger.info(
        "POST /ingest-docs | symbol=%s | client=%s",
        payload.symbol,
        request.client.host if request.client else "unknown",
    )

    try:
        result = execute_doc_pipeline(payload.symbol)

        # Surface a 500 when every document failed so callers can detect
        # total failure without inspecting the response body.
        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except HTTPException:
        raise

    except ValueError as exc:
        logger.warning("Bad request for symbol=%s: %s", payload.symbol, exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error in doc pipeline for %s", payload.symbol)
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")