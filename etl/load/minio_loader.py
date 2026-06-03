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
"""

import io
import os
import re
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

# ── Lazy MinIO singleton ──────────────────────────────────────────────────────
_client: Minio | None = None


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
    """
    from etl.extract.screener_downloader import resolve_pdf_url

    url      = resolve_pdf_url(doc["url"], session) or doc["url"]
    dtype    = doc["doc_type"]                          # "annual_report" | "concall"
    year     = str(doc.get("year") or "unknown")
    symbol   = doc.get("symbol", "unknown").lower()
    title    = _safe_name(doc.get("title", "document"))

    bucket   = BUCKET_MAP.get(dtype, "other-documents")
    obj_name = f"{symbol}/{year}_{title}.pdf"           # path inside the bucket

    if not _is_probable_pdf_url(url):
        _debug_log(
            "pre-fix",
            "H3",
            "etl/load/minio_loader.py:125",
            "Skipped non-direct/non-PDF URL before download",
            {"url": url, "doc_type": dtype, "title": doc.get("title", "")},
        )
        logger.warning("Skipped %s — not a direct PDF URL", url)
        return None

    # ── 1. Stream PDF bytes ───────────────────────────────────────────────────
    try:
        dl_headers = {
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

        _debug_log(
            "pre-fix",
            "H3",
            "etl/load/minio_loader.py:152",
            "Downloading document URL",
            {
                "url": url,
                "original_url": doc["url"][:200],
                "headers_set": sorted(list(dl_headers.keys())),
            },
        )

        resp = session.get(url, headers=dl_headers, timeout=60, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "html" in content_type.lower():
            logger.warning("Skipped %s — server returned HTML, not PDF", url)
            return None

        pdf_bytes = b"".join(resp.iter_content(65_536))

        if len(pdf_bytes) < 10_240:          # < 10 KB → likely an error page
            logger.warning("Skipped %s — too small (%d bytes)", url, len(pdf_bytes))
            return None

    except Exception as exc:
        _debug_log(
            "pre-fix",
            "H3",
            "etl/load/minio_loader.py:169",
            "Document download failed",
            {"url": url, "error": str(exc)},
        )
        logger.error("Download failed for %s: %s", url, exc)
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