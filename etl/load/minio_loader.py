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
import requests
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

# ── Bucket names per doc_type ─────────────────────────────────────────────────
BUCKET_MAP = {
    "annual_report": "annual-reports",
    "concall":       "concall-transcripts",
}

# ── Lazy MinIO singleton ──────────────────────────────────────────────────────
_client: Minio | None = None


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
    url      = doc["url"]
    dtype    = doc["doc_type"]                          # "annual_report" | "concall"
    year     = str(doc.get("year") or "unknown")
    symbol   = doc.get("symbol", "unknown").lower()
    title    = _safe_name(doc.get("title", "document"))

    bucket   = BUCKET_MAP.get(dtype, "other-documents")
    obj_name = f"{symbol}/{year}_{title}.pdf"           # path inside the bucket

    # ── 1. Stream PDF bytes ───────────────────────────────────────────────────
    try:
        dl_headers = {}
        if "bseindia.com" in url:
            dl_headers["Referer"] = "https://www.bseindia.com/"
        elif "nseindia.com" in url:
            dl_headers["Referer"] = "https://www.nseindia.com/"

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