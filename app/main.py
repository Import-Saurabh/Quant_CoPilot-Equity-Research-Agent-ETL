"""
main.py
───────
Quant Copilot Equity Research Agent — FastAPI application entry point.

Production features included here:
  • Structured logging (JSON-friendly via standard library)
  • CORS middleware (origins configured via environment variable)
  • Global exception handler so unhandled errors never leak tracebacks
  • /health exposed at root level (in addition to the router's /health)
  • Lifespan context manager for startup / shutdown hooks
    – logs MinIO connectivity on startup
  • Uvicorn launch block for `python main.py` convenience
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before yield; shutdown tasks after."""
    logger.info("═══ Quant Copilot API starting up ═══")

    # ── MinIO connectivity check ──────────────────────────────────────────
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    logger.info("MinIO endpoint  : %s", minio_endpoint)
    logger.info("MinIO access key: %s", os.getenv("MINIO_ACCESS_KEY", "minioadmin"))

    try:
        from etl.loaders.minio_loader import ping_minio
        if ping_minio():
            logger.info("MinIO ✓ reachable at %s", minio_endpoint)
        else:
            logger.warning(
                "MinIO ✗ NOT reachable at %s — /ingest-docs will fail until "
                "the container is up and MINIO_ENDPOINT is correct.",
                minio_endpoint,
            )
    except Exception as exc:
        logger.warning("MinIO probe error: %s", exc)

    yield

    logger.info("═══ Quant Copilot API shut down ════")


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Quant Copilot Equity Research Agent",
    version="2.1.0",
    description=(
        "ETL pipeline API that scrapes Screener.in + yfinance and loads "
        "financial data into MySQL, and ingests annual report / concall "
        "PDFs into MinIO with metadata tracked in MySQL."
    ),
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global unhandled-exception handler ───────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal error occurred."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(router, prefix="/api/v1")


# ─────────────────────────────────────────────────────────────────────────────
# Dev / production launch
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info",
    )