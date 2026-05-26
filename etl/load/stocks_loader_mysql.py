"""
load/stocks_loader.py  –  Upsert master stock metadata into the `stocks` table.
================================================================================
Schema (as of 2026-05-26):
    symbol          VARCHAR(30)      PRIMARY KEY
    screener_id     BIGINT           UNIQUE (uq_screener_id)
    name            VARCHAR(255)
    exchange        VARCHAR(10)      NOT NULL
    sector          VARCHAR(100)
    broad_sector    VARCHAR(100)
    industry        VARCHAR(100)
    broad_industry  VARCHAR(100)
    currency        VARCHAR(5)       NOT NULL
    created_at      DATETIME         NOT NULL
    updated_at      DATETIME         NOT NULL
    market_cap_cr   DECIMAL(18,2)

Usage
-----
    from load.stocks_loader import load_stock_master

    load_stock_master(DB_CONFIG, master_data)

`master_data` is the dict returned by scrape_stock_master_details() in
stocks_mysql.py, optionally augmented with 'name', 'exchange', 'currency'.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import mysql.connector


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _get_connection(db_config: dict):
    cfg = {k: v for k, v in db_config.items() if k != "autocommit"}
    conn = mysql.connector.connect(**cfg)
    conn.autocommit = False
    return conn


def _infer_exchange(symbol: str) -> str:
    """
    Infer exchange from a raw ticker suffix if not explicitly supplied.
    HAL.NS  → NSE
    HAL.BO  → BSE
    Anything else (no suffix) → NSE   (safe default for Indian equities)
    """
    upper = symbol.upper()
    if upper.endswith(".BO") or upper.endswith(":BO"):
        return "BSE"
    return "NSE"


def _infer_currency(exchange: str) -> str:
    """INR for Indian exchanges; can be extended for other markets."""
    return "INR"


# ─────────────────────────────────────────────────────────────────
# Public loader
# ─────────────────────────────────────────────────────────────────

def load_stock_master(
    db_config: dict,
    master_data: dict,
    raw_ticker: str | None = None,
) -> bool:
    """
    Upsert one row in the `stocks` table.

    Parameters
    ----------
    db_config   : MySQL connection dict (same shape as DB_CONFIG in pipeline).
    master_data : Dict returned by scrape_stock_master_details().
                  Keys used:
                    symbol, screener_id,
                    broad_sector, sector, broad_industry, industry,
                    market_cap_cr
                  Optional keys (filled with sensible defaults if absent):
                    name, exchange, currency
    raw_ticker  : Original ticker string (e.g. "HAL.NS") used to infer
                  exchange when not present in master_data.

    Returns
    -------
    True on success, False on failure.
    """
    if not master_data:
        print("  [stocks_loader] Received empty master_data — skipping.")
        return False

    symbol = (master_data.get("symbol") or "").upper().strip()
    if not symbol:
        print("  [stocks_loader] No symbol in master_data — skipping.")
        return False

    # ── Resolve optional fields ──────────────────────────────────
    raw_for_exchange = raw_ticker or symbol
    exchange = (
        master_data.get("exchange")
        or _infer_exchange(raw_for_exchange)
    )
    currency = (
        master_data.get("currency")
        or _infer_currency(exchange)
    )
    name = master_data.get("name") or None          # NULL if not scraped yet

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        INSERT INTO stocks (
            symbol, screener_id,
            name, exchange,
            sector, broad_sector,
            industry, broad_industry,
            currency,
            market_cap_cr,
            created_at, updated_at
        )
        VALUES (
            %(symbol)s, %(screener_id)s,
            %(name)s, %(exchange)s,
            %(sector)s, %(broad_sector)s,
            %(industry)s, %(broad_industry)s,
            %(currency)s,
            %(market_cap_cr)s,
            %(now)s, %(now)s
        )
        ON DUPLICATE KEY UPDATE
            screener_id    = COALESCE(VALUES(screener_id),  screener_id),
            name           = COALESCE(VALUES(name),         name),
            exchange       = VALUES(exchange),
            sector         = COALESCE(VALUES(sector),       sector),
            broad_sector   = COALESCE(VALUES(broad_sector), broad_sector),
            industry       = COALESCE(VALUES(industry),     industry),
            broad_industry = COALESCE(VALUES(broad_industry), broad_industry),
            currency       = VALUES(currency),
            market_cap_cr  = COALESCE(VALUES(market_cap_cr), market_cap_cr),
            updated_at     = %(now)s
    """

    params: dict[str, Any] = {
        "symbol":        symbol,
        "screener_id":   master_data.get("screener_id"),
        "name":          name,
        "exchange":      exchange,
        "sector":        master_data.get("sector"),
        "broad_sector":  master_data.get("broad_sector"),
        "industry":      master_data.get("industry"),
        "broad_industry": master_data.get("broad_industry"),
        "currency":      currency,
        "market_cap_cr": master_data.get("market_cap_cr"),
        "now":           now,
    }

    conn = None
    try:
        conn = _get_connection(db_config)
        cur  = conn.cursor()
        cur.execute(sql, params)
        action = "inserted" if cur.rowcount == 1 else "updated"
        conn.commit()
        print(f"  [stocks_loader] ✔  {symbol} — row {action}.")
        return True

    except mysql.connector.Error as exc:
        if conn:
            conn.rollback()
        print(f"  [stocks_loader] ✗  MySQL error for {symbol}: {exc}")
        return False

    finally:
        if conn and conn.is_connected():
            conn.close()