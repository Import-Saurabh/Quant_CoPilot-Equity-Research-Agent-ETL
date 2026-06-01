"""
doc_pipeline_service.py
───────────────────────
Orchestrates the PDF document ingestion pipeline:

    Screener.in scrape  →  MinIO upload  →  MySQL metadata save

Called by app/services/pipeline_service.py → execute_doc_pipeline().
"""

import logging
import time
import requests

from etl.extract.screener_downloader import fetch_page, extract_documents
from etl.load.minio_loader import upload_document, ping_minio
from etl.load.pdf_db_loader import load_pdf_document
from etl.mysql_pipeline import DB_CONFIG

logger = logging.getLogger(__name__)

_SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_CRAWL_DELAY_S = 1.0     # seconds between PDF downloads — stay polite


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

    logger.info("%d document(s) found for %s", len(docs), symbol)

    # ── 2. Upload each doc → MinIO + MySQL ────────────────────────────────────
    uploaded:      list[str] = []
    failed_titles: list[str] = []

    for doc in docs:
        doc["symbol"] = symbol          # needed by minio_loader for object path

        object_path = upload_document(doc, session)

        if object_path:
            file_name = object_path.split("/")[-1]

            load_pdf_document(
                db_config   = DB_CONFIG,
                symbol      = symbol,
                doc_type    = doc["doc_type"],
                fiscal_year = doc.get("year"),
                file_name   = file_name,
                object_path = object_path,
            )
            uploaded.append(object_path)
        else:
            failed_titles.append(doc.get("title", "unknown"))

        time.sleep(_CRAWL_DELAY_S)

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