"""
doc_pipeline_service.py
───────────────────────
Orchestrates the PDF document ingestion pipeline:

    Screener.in scrape  →  MinIO upload  →  MySQL metadata save

Called programmatically:
    from etl.doc_pipeline_service import run_doc_pipeline, run_retry_pipeline

Run as a script:
    # Fresh ingest
    python -m etl.doc_pipeline_service --symbol TCS

    # Retry CDN-blocked docs from a previous run
    python -m etl.doc_pipeline_service --retry --queue-file ./retry_queues/retry_TCS_*.json

    # Inspect queue without making any requests
    python -m etl.doc_pipeline_service --retry --queue-file ./retry_queues/retry_TCS_*.json --dry-run

Retry queue
───────────
Documents that fail with a likely CDN / IP-reputation block are written to a
timestamped JSON file under RETRY_QUEUE_DIR (default: ./retry_queues/).
run_retry_pipeline() reads that file, honours a minimum cooldown since the
original failure, and rewrites the file in place after each run so progress
accumulates across multiple attempts.
"""

import argparse
import glob
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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

_CRAWL_DELAY_MIN = 6.0
_CRAWL_DELAY_MAX = 14.0

# Domains whose 403s are more likely IP-reputation / WAF than a fixable
# session issue.  Failures from these hosts go to the retry queue instead
# of being counted as permanent failures.
_CDN_PROTECTED_DOMAINS = {
    "tcs.com",
    # "wipro.com",
    # "infosys.com",
}

RETRY_QUEUE_DIR = Path(os.getenv("RETRY_QUEUE_DIR", "./retry_queues"))


# ── Logging helper ────────────────────────────────────────────────────────────

def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # #region agent log
    try:
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


# ── CDN helpers ───────────────────────────────────────────────────────────────

def _is_cdn_protected(url: str) -> bool:
    lowered = url.lower()
    return any(d in lowered for d in _CDN_PROTECTED_DOMAINS)


# ── Retry queue I/O ───────────────────────────────────────────────────────────

def _write_retry_queue(symbol: str, candidates: list[dict]) -> Path:
    """
    Persist *candidates* to a timestamped JSON file under RETRY_QUEUE_DIR.
    Each entry carries a ``failure_epoch`` so run_retry_pipeline() can
    honour a minimum cooldown.  Returns the path written.
    """
    RETRY_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RETRY_QUEUE_DIR / f"retry_{symbol}_{ts}.json"
    path.write_text(
        json.dumps(
            {
                "symbol":     symbol,
                "created_at": ts,
                "note":       (
                    "python -m etl.doc_pipeline_service "
                    "--retry --queue-file <this file> --min-cooldown-minutes 60"
                ),
                "docs":        candidates,
                "succeeded":  [],
                "hard_failed": [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _load_queue(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_queue(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Upload + DB save (shared by both pipelines) ───────────────────────────────

def _upload_and_save(doc: dict, session: requests.Session) -> tuple[str | None, bool]:
    """
    Upload *doc* to MinIO and write metadata to MySQL.

    Returns (object_path, db_saved).
    object_path is None on download/upload failure.
    db_saved is False if the upload succeeded but the DB write failed.
    """
    object_path = upload_document(doc, session)
    if not object_path:
        return None, False

    file_name = object_path.split("/")[-1]
    db_saved  = load_pdf_document(
        db_config   = DB_CONFIG,
        symbol      = doc["symbol"],
        doc_type    = doc["doc_type"],
        fiscal_year = doc.get("year"),
        file_name   = file_name,
        object_path = object_path,
    )
    return object_path, db_saved


# ── Result builder ────────────────────────────────────────────────────────────

def _result(
    *,
    status:            str,
    symbol:            str,
    message:           str,
    total:             int         = 0,
    uploaded:          list | None = None,
    failed:            list | None = None,
    retry_queue:       str | None  = None,
    retry_queue_count: int         = 0,
) -> dict:
    return {
        "status":            status,
        "symbol":            symbol,
        "message":           message,
        "total":             total,
        "uploaded":          uploaded or [],
        "failed":            failed   or [],
        "retry_queue":       retry_queue,
        "retry_queue_count": retry_queue_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: fresh ingest
# ─────────────────────────────────────────────────────────────────────────────

def run_doc_pipeline(symbol: str) -> dict:
    """
    End-to-end document ingestion for *symbol*.

    1. Scrape Screener.in for annual reports + concall transcripts.
    2. Download → MinIO upload → MySQL metadata save for each doc.
    3. Write CDN-likely failures to a retry queue JSON file.

    Returns
    -------
    {
        "status":            "success" | "partial" | "failed",
        "symbol":            str,
        "message":           str,
        "total":             int,
        "uploaded":          list[str],   # MinIO object paths
        "failed":            list[str],   # hard-failure titles
        "retry_queue":       str | None,  # path to queue file if written
        "retry_queue_count": int,
    }
    """
    symbol = symbol.strip().upper()
    _debug_log("pre-fix", "H4", "etl/doc_pipeline_service.py:run_doc_pipeline",
               "Doc pipeline started", {"symbol": symbol})

    if not ping_minio():
        return _result(
            status="failed", symbol=symbol,
            message="MinIO is unreachable. Check MINIO_* env vars.",
        )

    session = requests.Session()
    session.headers.update(_SCRAPER_HEADERS)

    try:
        soup, page_url = fetch_page(session, symbol)
        docs           = extract_documents(soup, page_url)
    except SystemExit as exc:
        return _result(status="failed", symbol=symbol,
                       message=f"Could not fetch Screener.in page for '{symbol}': {exc}")
    except Exception as exc:
        logger.exception("Scrape error for %s", symbol)
        return _result(status="failed", symbol=symbol,
                       message=f"Unexpected scrape error for '{symbol}': {exc}")

    if not docs:
        return _result(status="success", symbol=symbol,
                       message=f"No documents found for '{symbol}'.")

    annual_n  = sum(1 for d in docs if d["doc_type"] == "annual_report")
    concall_n = sum(1 for d in docs if d["doc_type"] == "concall")
    logger.info("%d doc(s) for %s (%d annual, %d concall)",
                len(docs), symbol, annual_n, concall_n)
    _debug_log("pre-fix", "H1", "etl/doc_pipeline_service.py:docs_found",
               "Extracted document counts",
               {"symbol": symbol, "total": len(docs), "annual": annual_n, "concall": concall_n})

    uploaded:         list[str]  = []
    failed_titles:    list[str]  = []
    retry_candidates: list[dict] = []

    for i, doc in enumerate(docs):
        doc["symbol"] = symbol
        object_path, db_saved = _upload_and_save(doc, session)

        _debug_log("pre-fix", "H2", "etl/doc_pipeline_service.py:upload_result",
                   "Upload attempt finished",
                   {"symbol": symbol, "doc_type": doc.get("doc_type"),
                    "title": doc.get("title", "unknown"),
                    "url": doc.get("url", "")[:200], "success": bool(object_path)})

        if object_path and db_saved:
            uploaded.append(object_path)
        elif object_path and not db_saved:
            # Upload OK but DB write failed — hard failure.
            failed_titles.append(doc.get("title", "unknown"))
            _debug_log("pre-fix", "H4", "etl/doc_pipeline_service.py:db_save_failed",
                       "DB save failed after successful upload",
                       {"symbol": symbol, "object_path": object_path})
        else:
            # Upload failed — CDN block or hard failure.
            if _is_cdn_protected(doc.get("url", "")):
                retry_candidates.append({**doc, "failure_epoch": int(time.time())})
                logger.info("Queued for retry (CDN block): %s", doc.get("title", "unknown"))
            else:
                failed_titles.append(doc.get("title", "unknown"))

        if i < len(docs) - 1:
            time.sleep(random.uniform(_CRAWL_DELAY_MIN, _CRAWL_DELAY_MAX))

    # Write retry queue if needed.
    retry_queue_path: Path | None = None
    if retry_candidates:
        try:
            retry_queue_path = _write_retry_queue(symbol, retry_candidates)
            logger.info("%d CDN-blocked doc(s) queued → %s",
                        len(retry_candidates), retry_queue_path)
        except Exception as exc:
            logger.error("Failed to write retry queue: %s", exc)
            failed_titles.extend(c.get("title", "unknown") for c in retry_candidates)
            retry_candidates = []

    all_failed = failed_titles + [c.get("title", "unknown") for c in retry_candidates]
    if not uploaded and all_failed:
        status = "failed"
    elif uploaded and all_failed:
        status = "partial"
    else:
        status = "success"

    parts = [f"Document pipeline finished for {symbol}."]
    if uploaded:
        parts.append(f"{len(uploaded)}/{len(docs)} PDF(s) uploaded.")
    if failed_titles:
        parts.append(f"{len(failed_titles)} hard failure(s): {failed_titles}.")
    if retry_candidates:
        parts.append(f"{len(retry_candidates)} CDN-blocked doc(s) queued → {retry_queue_path}.")

    return _result(
        status=status, symbol=symbol, message=" ".join(parts),
        total=len(docs), uploaded=uploaded, failed=failed_titles,
        retry_queue=str(retry_queue_path) if retry_queue_path else None,
        retry_queue_count=len(retry_candidates),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public: retry from queue
# ─────────────────────────────────────────────────────────────────────────────

def run_retry_pipeline(
    queue_path:           Path,
    min_cooldown_minutes: int   = 60,
    inter_doc_delay:      float = 120.0,
    dry_run:              bool  = False,
) -> dict:
    """
    Re-attempt CDN-blocked docs written by run_doc_pipeline().

    Reads *queue_path*, honours *min_cooldown_minutes* since the original
    failure, then uploads each doc with *inter_doc_delay* seconds (×0.8–1.4
    jitter) between documents.

    The queue file is rewritten in place after every run:
      • succeeded docs move to ``"succeeded"``
      • still-failing docs stay in ``"docs"`` with a refreshed ``failure_epoch``

    Returns the same shape as run_doc_pipeline() so callers handle both uniformly.
    """
    payload = _load_queue(queue_path)
    symbol  = payload.get("symbol", "UNKNOWN")
    docs    = payload.get("docs", [])

    logger.info("Retry queue: %s | symbol: %s | %d doc(s)", queue_path.name, symbol, len(docs))

    if not docs:
        logger.info("Queue is empty — nothing to retry.")
        return _result(status="success", symbol=symbol,
                       message="Retry queue was empty.")

    if not dry_run and not ping_minio():
        return _result(status="failed", symbol=symbol,
                       message="MinIO is unreachable.")

    min_cooldown_secs = min_cooldown_minutes * 60
    now               = int(time.time())

    session = requests.Session()
    session.headers.update(_SCRAPER_HEADERS)

    still_queued: list[dict] = []
    uploaded:     list[str]  = []
    hard_failed:  list[str]  = []

    for i, doc in enumerate(docs):
        title         = doc.get("title", "unknown")
        elapsed       = now - doc.get("failure_epoch", 0)
        wait_more     = max(0, min_cooldown_secs - elapsed)

        if dry_run:
            logger.info("[DRY-RUN %d/%d] would retry: %s  (%s)",
                        i + 1, len(docs), title, doc.get("url", "")[:80])
            continue

        if wait_more > 0:
            logger.info("[%d/%d] %s — cooldown: waiting %.0f s …",
                        i + 1, len(docs), title, wait_more)
            time.sleep(wait_more)

        logger.info("[%d/%d] Retrying: %s", i + 1, len(docs), title)

        object_path, db_saved = _upload_and_save(doc, session)

        if object_path and db_saved:
            logger.info("  ✓ %s", object_path)
            uploaded.append(object_path)
        elif object_path and not db_saved:
            logger.error("  ✗ upload OK but DB save failed: %s", title)
            hard_failed.append(title)
        else:
            logger.warning("  ✗ still failing — keeping in queue: %s", title)
            still_queued.append({**doc, "failure_epoch": int(time.time())})

        if i < len(docs) - 1:
            delay = inter_doc_delay * random.uniform(0.8, 1.4)
            logger.info("  sleeping %.0f s …", delay)
            time.sleep(delay)

    # Rewrite queue file in place.
    if not dry_run:
        payload["docs"]        = still_queued
        payload["last_retry"]  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        payload["succeeded"]   = payload.get("succeeded",   []) + uploaded
        payload["hard_failed"] = payload.get("hard_failed", []) + hard_failed
        _save_queue(queue_path, payload)

    all_failed = hard_failed + [d.get("title", "unknown") for d in still_queued]
    if not uploaded and all_failed:
        status = "failed"
    elif uploaded and all_failed:
        status = "partial"
    else:
        status = "success"

    parts = [f"Retry pipeline finished for {symbol}."]
    if uploaded:
        parts.append(f"{len(uploaded)} PDF(s) uploaded.")
    if hard_failed:
        parts.append(f"{len(hard_failed)} hard failure(s).")
    if still_queued:
        parts.append(f"{len(still_queued)} doc(s) still blocked — queue updated.")

    logger.info("\n══ Retry summary ══\n  ✓ %d  ✗ %d  still-queued: %d",
                len(uploaded), len(hard_failed), len(still_queued))

    return _result(
        status=status, symbol=symbol, message=" ".join(parts),
        total=len(docs), uploaded=uploaded, failed=all_failed,
        retry_queue=str(queue_path),
        retry_queue_count=len(still_queued),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli_ingest(args: argparse.Namespace) -> None:
    result = run_doc_pipeline(args.symbol)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "failed" else 1)


def _cli_retry(args: argparse.Namespace) -> None:
    paths = [Path(p) for p in glob.glob(args.queue_file)]
    if not paths:
        logger.error("No queue files matched: %s", args.queue_file)
        sys.exit(1)

    exit_code = 0
    for qf in sorted(paths):
        result = run_retry_pipeline(
            queue_path           = qf,
            min_cooldown_minutes = args.min_cooldown_minutes,
            inter_doc_delay      = args.inter_doc_delay,
            dry_run              = args.dry_run,
        )
        print(json.dumps(result, indent=2))
        if result["status"] == "failed":
            exit_code = 1

    sys.exit(exit_code)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Fund document ingestion pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = ap.add_subparsers(dest="command")

    # --- ingest ---
    p_ingest = sub.add_parser("ingest", help="Fresh scrape + upload for a symbol")
    p_ingest.add_argument("--symbol", required=True, help="Ticker, e.g. TCS")

    # --- retry ---
    p_retry = sub.add_parser("retry", help="Re-attempt CDN-blocked docs from a queue file")
    p_retry.add_argument("--queue-file", required=True, metavar="PATH_OR_GLOB",
                         help="Queue JSON file produced by a previous ingest run")
    p_retry.add_argument("--min-cooldown-minutes", type=int, default=60, metavar="N",
                         help="Minimum minutes since original failure before retrying")
    p_retry.add_argument("--inter-doc-delay", type=float, default=120.0, metavar="SECS",
                         help="Base delay between document retries (actual = delay × 0.8–1.4)")
    p_retry.add_argument("--dry-run", action="store_true",
                         help="Print what would be retried without making any requests")

    return ap


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    parser = _build_parser()
    args   = parser.parse_args()

    if args.command == "ingest":
        _cli_ingest(args)
    elif args.command == "retry":
        _cli_retry(args)
    else:
        parser.print_help()
        sys.exit(1)