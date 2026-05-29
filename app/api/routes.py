"""
routes.py
─────────
FastAPI router for the Quant Copilot Equity Research API.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.schemas import StockRequest, PipelineResponse
from app.services.pipeline_service import execute_pipeline

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


# ── Ingest / run pipeline ─────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=PipelineResponse,
    summary="Run ETL pipeline for a stock",
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

        # If every section failed treat it as a 500 so callers can detect it
        # without inspecting the body.
        if result["status"] == "failed":
            raise HTTPException(
                status_code=500,
                detail=result["message"],
            )

        return result

    except HTTPException:
        raise  # already formatted

    except ValueError as exc:
        logger.warning("Bad request for symbol=%s: %s", payload.symbol, exc)
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        logger.exception("Unexpected error running pipeline for %s", payload.symbol)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {exc}",
        )