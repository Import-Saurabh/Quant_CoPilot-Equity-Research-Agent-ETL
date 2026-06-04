"""
doc_pipeline_service.py
───────────────────────
Orchestrates the PDF document ingestion pipeline:

    Screener.in scrape  →  MinIO upload  →  MySQL metadata save

Called by app/services/pipeline_service.py → execute_doc_pipeline().
"""

import logging
import random
import time
import requests

from etl.extract.screener_downloader import fetch_page, extract_documents
from etl.load.minio_loader import upload_document, ping_minio
from etl.load.pdf_db_loader import load_pdf_document
from etl.mysql_pipeline import DB_CONFIG

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = "debug-597278.log"

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Inter-document crawl delay: actual sleep = uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX).
# Randomised bounds prevent the uniform-interval timing signature that CDNs detect.
_CRAWL_DELAY_MIN = 6.0
_CRAWL_DELAY_MAX = 14.0


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        import json
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "sessionId": "597278",
                "runId": run_id,
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }, ensure_ascii=True) + "\n")
    except Exception:
        pass
    # #endregion


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_doc_pipeline(symbol: str) -> dict:
    """
    End-to-end document ingestion for *symbol*.

    Steps
    -----
    1. Scrape Screener.in document section for annual reports & concall transcripts.
    2. For each document: download PDF bytes → upload to MinIO → save metadata to MySQL.
    3. Return a structured result dict compatible with DocIngestResponse.

    Returns
    -------
    {
        "status":   "success" | "partial" | "failed",
        "symbol":   str,
        "message":  str,
        "total":    int,
        "uploaded": list[str],    # MinIO object paths that succeeded
        "failed":   list[str],    # document titles that failed
    }
    """
    symbol = symbol.strip().upper()
    _debug_log(
        "pre-fix",
        "H4",
        "etl/doc_pipeline_service.py:80",
        "Doc pipeline started",
        {"symbol": symbol},
    )

    # ── Pre-flight: MinIO reachability ────────────────────────────────────────
    if not ping_minio():
        return _result(
            status="failed",
            symbol=symbol,
            message=(
                "MinIO is unreachable. "
                "Check MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY env vars."
            ),
        )

    # ── 1. Scrape document list ───────────────────────────────────────────────
    session = requests.Session()
    session.headers.update(_SCRAPER_HEADERS)

    try:
        soup, page_url = fetch_page(session, symbol)
        docs           = extract_documents(soup, page_url)
    except SystemExit as exc:
        # fetch_page() calls sys.exit() on HTTP failure — catch it gracefully
        return _result(
            status="failed",
            symbol=symbol,
            message=f"Could not fetch Screener.in page for '{symbol}': {exc}",
        )
    except Exception as exc:
        logger.exception("Scrape error for %s", symbol)
        return _result(
            status="failed",
            symbol=symbol,
            message=f"Unexpected scrape error for '{symbol}': {exc}",
        )

    if not docs:
        return _result(
            status="success",
            symbol=symbol,
            message=f"No documents (annual reports / concalls) found for '{symbol}'.",
        )

    annual_n = sum(1 for d in docs if d["doc_type"] == "annual_report")
    concall_n = sum(1 for d in docs if d["doc_type"] == "concall")
    logger.info(
        "%d document(s) found for %s (%d annual, %d concall)",
        len(docs), symbol, annual_n, concall_n,
    )
    _debug_log(
        "pre-fix",
        "H1",
        "etl/doc_pipeline_service.py:131",
        "Extracted document counts by type",
        {"symbol": symbol, "total": len(docs), "annual": annual_n, "concall": concall_n},
    )

    # ── 2. Upload each doc → MinIO + MySQL ────────────────────────────────────
    uploaded:      list[str] = []
    failed_titles: list[str] = []

    for i, doc in enumerate(docs):
        doc["symbol"] = symbol          # needed by minio_loader for object path

        object_path = upload_document(doc, session)

        _debug_log(
            "pre-fix",
            "H2",
            "etl/doc_pipeline_service.py:145",
            "Upload attempt finished",
            {
                "symbol": symbol,
                "doc_type": doc.get("doc_type"),
                "title": doc.get("title", "unknown"),
                "url": doc.get("url", "")[:200],
                "success": bool(object_path),
            },
        )

        if object_path:
            file_name = object_path.split("/")[-1]

            db_saved = load_pdf_document(
                db_config   = DB_CONFIG,
                symbol      = symbol,
                doc_type    = doc["doc_type"],
                fiscal_year = doc.get("year"),
                file_name   = file_name,
                object_path = object_path,
            )
            if db_saved:
                uploaded.append(object_path)
            else:
                failed_titles.append(doc.get("title", "unknown"))
                _debug_log(
                    "pre-fix",
                    "H4",
                    "etl/doc_pipeline_service.py:151",
                    "DB save failed after upload; marking doc as failed",
                    {"symbol": symbol, "object_path": object_path, "title": doc.get("title", "unknown")},
                )
        else:
            failed_titles.append(doc.get("title", "unknown"))

        # Randomised inter-document delay — avoids the uniform-interval timing
        # fingerprint that CDN rate-limiters use to detect bots.
        if i < len(docs) - 1:
            time.sleep(random.uniform(_CRAWL_DELAY_MIN, _CRAWL_DELAY_MAX))

    # ── 3. Compose result ─────────────────────────────────────────────────────
    total = len(docs)

    if not uploaded and failed_titles:
        status = "failed"
    elif uploaded and failed_titles:
        status = "partial"
    else:
        status = "success"

    parts = [f"Document pipeline finished for {symbol}."]
    if uploaded:
        parts.append(f"{len(uploaded)}/{total} PDF(s) uploaded to MinIO.")
    if failed_titles:
        parts.append(f"{len(failed_titles)} failed: {failed_titles}.")

    return _result(
        status=status,
        symbol=symbol,
        message=" ".join(parts),
        total=total,
        uploaded=uploaded,
        failed=failed_titles,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _result(
    *,
    status: str,
    symbol: str,
    message: str,
    total: int = 0,
    uploaded: list | None = None,
    failed: list | None = None,
) -> dict:
    return {
        "status":   status,
        "symbol":   symbol,
        "message":  message,
        "total":    total,
        "uploaded": uploaded or [],
        "failed":   failed   or [],
    }