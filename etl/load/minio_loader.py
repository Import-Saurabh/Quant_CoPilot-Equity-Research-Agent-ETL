"""
minio_loader.py
───────────────
MinIO upload helpers for scraped PDF documents.

Bucket layout
    annual-reports/{symbol_lower}/{year}_{safe_title}.pdf
    concall-transcripts/{symbol_lower}/{year}_{safe_title}.pdf

Environment variables (with defaults):
    MINIO_ENDPOINT     localhost:9000    ← S3 API port (console is 9001)
    MINIO_ACCESS_KEY   minioadmin
    MINIO_SECRET_KEY   minioadmin
    MINIO_SECURE       false

Inside Docker: set MINIO_ENDPOINT to your MinIO container name, e.g. minio:9000

Retry policy
────────────
Three attempts: immediate → ~20 s → ~60 s → ~120 s (each ×0.8–1.4 jitter).
On 403 / 429 the HTTP status code and a diagnostic hint are written to the
debug log so you can distinguish IP-reputation blocks from cookie issues
without changing code.  No session warm-up or proxy rotation is attempted;
the pipeline continues and unresolvable failures are collected for a
separate delayed-retry pass by retry_failed_docs.py.
"""

import io
import os
import re
import random
import logging
import time
import requests
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = "debug-597278.log"

# ── Bucket names per doc_type ─────────────────────────────────────────────────
BUCKET_MAP = {
    "annual_report": "annual-reports",
    "concall":       "concall-transcripts",
}

# ── Retry / back-off ──────────────────────────────────────────────────────────
# Three retries.  Base waits are conservative so a transient rate-limit can
# clear; each is multiplied by a random jitter factor to avoid uniform timing.
_RETRY_DELAYS = [20, 60, 120]   # seconds
_JITTER_RANGE = (0.8, 1.4)

# ── Lazy MinIO singleton ──────────────────────────────────────────────────────
_client: Minio | None = None


# ── Logging helpers ───────────────────────────────────────────────────────────

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


def _block_hint(status: int, url: str) -> str:
    """
    Return a one-line diagnostic hint written to the log on 403 / 429.

    This is intentionally informational — the caller should NOT branch on it.
    Use it to decide manually whether you're hitting an IP block (hint ends
    with [ip_reputation]) vs a simple cookie issue ([session]) vs a WAF
    challenge ([challenge]).
    """
    lowered = url.lower()
    if status == 429:
        return "rate-limited — back off and retry [rate_limit]"
    # Persistent 403 from Akamai / Cloudflare / TCS CDN is usually one of:
    #   • missing browser-challenge token  → [challenge]
    #   • IP reputation score too low      → [ip_reputation]
    #   • session/cookie absent            → [session]
    # We can't tell from the status code alone; log the host for manual triage.
    if "tcs.com" in lowered:
        return (
            "TCS CDN 403 — could be IP reputation, WAF challenge, or missing "
            "cookie. Test: open URL in browser from same machine. If browser "
            "succeeds, issue is fingerprint/challenge [challenge]. If browser "
            "also fails, issue is IP reputation [ip_reputation]."
        )
    if "bseindia.com" in lowered or "nseindia.com" in lowered:
        return "exchange CDN 403 — likely missing Referer or session cookie [session]"
    return "403 from unknown host — inspect manually [unknown]"


# ── MinIO client ──────────────────────────────────────────────────────────────

def get_client() -> Minio:
    global _client
    if _client is None:
        endpoint   = os.getenv("MINIO_ENDPOINT",   "localhost:9000")
        access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        secure     = os.getenv("MINIO_SECURE",     "false").lower() == "true"

        _client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        logger.info("MinIO client ready → %s  (secure=%s)", endpoint, secure)

    return _client


def ping_minio() -> bool:
    """Lightweight connectivity check. Returns True if MinIO is reachable."""
    try:
        get_client().list_buckets()
        return True
    except Exception as exc:
        logger.error("MinIO unreachable: %s", exc)
        return False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def _safe_name(s: str) -> str:
    """Strip characters that are unsafe in S3 object keys."""
    return re.sub(r"[^\w\-_.]", "_", s)[:80]


def _is_probable_pdf_url(url: str) -> bool:
    """
    Return False only for known non-PDF destinations (YouTube, empty href).
    Overlay and filing URLs are resolved to a direct PDF before download.
    """
    lowered = url.lower()
    if not lowered.startswith("http"):
        return False
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return False
    return True


# ── Public upload function ────────────────────────────────────────────────────

def upload_document(doc: dict, session: requests.Session) -> str | None:
    """
    Download a PDF from *doc["url"]* and upload it to the appropriate MinIO bucket.

    Parameters
    ----------
    doc     : dict produced by screener_downloader.extract_documents(), plus
              doc["symbol"] must be set by the caller before passing in.
    session : requests.Session with browser-like headers already applied.

    Returns
    -------
    object_path (str)  — e.g. "annual-reports/tcs/2024_TCS_Annual_Report.pdf"
    None               — on any download or upload failure (already logged).

    Failures
    --------
    Persistent 403s from CDN-protected hosts (tcs.com) may be IP-reputation
    or WAF-challenge blocks that a session reset cannot fix.  The failure is
    logged with a diagnostic hint; the caller (doc_pipeline_service) queues
    the doc for a delayed retry pass rather than retrying inline.
    """
    from etl.extract.screener_downloader import resolve_pdf_url

    url      = resolve_pdf_url(doc["url"], session) or doc["url"]
    dtype    = doc["doc_type"]
    year     = str(doc.get("year") or "unknown")
    symbol   = doc.get("symbol", "unknown").lower()
    title    = _safe_name(doc.get("title", "document"))

    bucket   = BUCKET_MAP.get(dtype, "other-documents")
    obj_name = f"{symbol}/{year}_{title}.pdf"

    if not _is_probable_pdf_url(url):
        _debug_log(
            "pre-fix", "H3",
            "etl/load/minio_loader.py:_is_probable_pdf_url",
            "Skipped non-direct/non-PDF URL before download",
            {"url": url, "doc_type": dtype, "title": doc.get("title", "")},
        )
        logger.warning("Skipped %s — not a direct PDF URL", url)
        return None

    # ── Per-request headers ───────────────────────────────────────────────────
    dl_headers: dict[str, str] = {
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if "bseindia.com" in url:
        dl_headers["Referer"] = "https://www.bseindia.com/"
    elif "nseindia.com" in url:
        dl_headers["Referer"] = "https://www.nseindia.com/"
    elif "tcs.com" in url:
        dl_headers["Referer"] = "https://www.tcs.com/investor-relations/financial-statements"

    # ── 1. Download with conservative retry ───────────────────────────────────
    pdf_bytes: bytes | None = None
    last_status: int | None = None

    delays = [0] + _RETRY_DELAYS   # attempt 0 = immediate; 1-3 are retries
    for attempt, base_wait in enumerate(delays):
        if base_wait:
            wait = base_wait * random.uniform(*_JITTER_RANGE)
            logger.info(
                "Retry %d/%d for %s — waiting %.0f s",
                attempt, len(_RETRY_DELAYS), url[:120], wait,
            )
            time.sleep(wait)

        _debug_log(
            "pre-fix", "H3",
            "etl/load/minio_loader.py:download_attempt",
            "Attempting document download",
            {
                "url":          url[:200],
                "original_url": doc["url"][:200],
                "attempt":      attempt,
            },
        )

        try:
            resp = session.get(url, headers=dl_headers, timeout=60, stream=True)
            last_status = resp.status_code

            if resp.status_code in (403, 429):
                hint = _block_hint(resp.status_code, url)
                logger.warning(
                    "HTTP %d on %s (attempt %d/%d) — %s",
                    resp.status_code, url[:120], attempt, len(_RETRY_DELAYS), hint,
                )
                _debug_log(
                    "pre-fix", "H3",
                    "etl/load/minio_loader.py:download_blocked",
                    f"HTTP {resp.status_code}",
                    {
                        "url":     url[:200],
                        "attempt": attempt,
                        "hint":    hint,
                    },
                )
                continue   # retry with back-off

            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")
            if "html" in content_type.lower():
                logger.warning("Skipped %s — server returned HTML (not a PDF)", url)
                return None

            pdf_bytes = b"".join(resp.iter_content(65_536))

            if len(pdf_bytes) < 10_240:   # < 10 KB → error page
                logger.warning("Skipped %s — too small (%d bytes)", url, len(pdf_bytes))
                return None

            break   # success

        except Exception as exc:
            logger.error(
                "Download error (attempt %d/%d) for %s: %s",
                attempt, len(_RETRY_DELAYS), url, exc,
            )
            _debug_log(
                "pre-fix", "H3",
                "etl/load/minio_loader.py:download_exception",
                "Download raised exception",
                {"url": url[:200], "attempt": attempt, "error": str(exc)},
            )
            if attempt == len(_RETRY_DELAYS):
                return None

    if pdf_bytes is None:
        logger.error(
            "Download failed after all retries (last HTTP %s): %s",
            last_status, url,
        )
        _debug_log(
            "pre-fix", "H3",
            "etl/load/minio_loader.py:download_exhausted",
            "All retries exhausted",
            {"url": url[:200], "last_status": last_status},
        )
        return None

    # ── 2. Upload to MinIO ────────────────────────────────────────────────────
    try:
        client = get_client()
        _ensure_bucket(client, bucket)

        client.put_object(
            bucket_name=bucket,
            object_name=obj_name,
            data=io.BytesIO(pdf_bytes),
            length=len(pdf_bytes),
            content_type="application/pdf",
        )

        full_path = f"{bucket}/{obj_name}"
        logger.info(
            "Uploaded → minio://%s  (%d KB)",
            full_path,
            len(pdf_bytes) // 1024,
        )
        return full_path

    except S3Error as exc:
        logger.error("MinIO S3Error uploading %s: %s", obj_name, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected MinIO error for %s: %s", obj_name, exc)
        return None