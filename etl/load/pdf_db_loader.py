"""
pdf_db_loader.py
────────────────
MySQL loader — inserts / upserts rows into pdf_documents.

The table uses (symbol, document_type, fiscal_year, file_name) as its logical
unique key so re-running a scrape for the same symbol only updates object_path
and uploaded_at rather than creating duplicates.
"""

import logging
import mysql.connector

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public loader
# ─────────────────────────────────────────────────────────────────────────────

def load_pdf_document(
    db_config:   dict,
    symbol:      str,
    doc_type:    str,
    fiscal_year: int | None,
    file_name:   str,
    object_path: str,
) -> bool:
    """
    Upsert one row into pdf_documents.

    Parameters
    ----------
    db_config   : MySQL connection dict (same format used throughout the project).
    symbol      : Normalised ticker, e.g. "TCS".
    doc_type    : "annual_report" | "concall".
    fiscal_year : 4-digit year, or None if not determinable.
    file_name   : Bare filename, e.g. "2024_TCS_Annual_Report.pdf".
    object_path : Full MinIO path, e.g. "annual-reports/tcs/2024_…pdf".

    Returns
    -------
    True on success, False on failure (error is logged).
    """
    company_id = _get_company_id(db_config, symbol)   # best-effort; may be None

    sql = """
        INSERT INTO pdf_documents
            (symbol, company_id, document_type, fiscal_year, file_name, object_path)
        VALUES
            (%(symbol)s, %(company_id)s, %(doc_type)s,
             %(fiscal_year)s, %(file_name)s, %(object_path)s)
        ON DUPLICATE KEY UPDATE
            object_path = VALUES(object_path),
            company_id  = COALESCE(VALUES(company_id), company_id),
            uploaded_at = CURRENT_TIMESTAMP
    """

    params = {
        "symbol":      symbol,
        "company_id":  company_id,
        "doc_type":    doc_type,
        "fiscal_year": fiscal_year,
        "file_name":   file_name,
        "object_path": object_path,
    }

    try:
        conn   = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        cursor.close()
        conn.close()
        logger.debug("Saved pdf_document: %s / %s / %s", symbol, doc_type, fiscal_year)
        return True

    except Exception as exc:
        logger.error(
            "DB insert failed for %s / %s / %s: %s",
            symbol, doc_type, fiscal_year, exc,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_company_id(db_config: dict, symbol: str) -> int | None:
    """
    Look up id in stocks_master for *symbol*.
    Returns None silently if the table doesn't exist yet or the ticker isn't
    loaded — company_id is nullable in pdf_documents.
    """
    try:
        conn   = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM stocks_master WHERE symbol = %s LIMIT 1",
            (symbol,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None