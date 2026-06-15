"""
app/db/connection.py
────────────────────
Shared MySQL connection pool for all read API endpoints.

Usage
-----
    from app.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT * FROM stocks WHERE symbol = %s", (symbol,))
        rows = cur.fetchall()
"""

import os
import logging
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

_pool: pooling.MySQLConnectionPool | None = None


def _build_pool() -> pooling.MySQLConnectionPool:
    return pooling.MySQLConnectionPool(
        pool_name="quant_api_pool",
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "ai_hedge_fund"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        charset="utf8mb4",
        use_pure=True,
        autocommit=True,
        time_zone="+05:30",
    )


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = _build_pool()
        logger.info("MySQL connection pool initialised (size=%s)", _pool.pool_size)
    return _pool


@contextmanager
def get_cursor():
    """Context manager that yields a dict-cursor and closes it on exit."""
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        yield cur
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()