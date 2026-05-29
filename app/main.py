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
    yield
    logger.info("═══ Quant Copilot API shut down ════")


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Quant Copilot Equity Research Agent",
    version="2.0.0",
    description=(
        "ETL pipeline API that scrapes Screener.in + yfinance and loads "
        "financial data into a MySQL database for quantitative research."
    ),
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set ALLOWED_ORIGINS env var to a comma-separated list of origins in production.
# Default is open (fine for internal / local use; tighten for public deployment).
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