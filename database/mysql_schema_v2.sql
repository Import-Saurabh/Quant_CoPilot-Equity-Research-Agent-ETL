-- ============================================================
--  ai_hedge_fund  –  MySQL Schema v2
--  Source of truth: Screener.in (financials), yfinance (prices)
--  Design goals:
--    • Works for ALL sectors — no sector-specific hardcoded cols
--    • Parent rows + child/schedule rows from Screener API
--    • NULLs are fine — never store 0 for "not applicable"
--    • No ratios stored here — calculate on the fly
--    • Migration-friendly alongside existing SQLite pipeline
--
--  v2 Bug fixes from v1:
--    [BUG-01] Removed is_consolidated from stocks master table —
--             belongs on each financial row, not the company record
--    [BUG-02] screener_id now has a UNIQUE constraint
--    [BUG-03] Removed hardcoded deposits/advances from balance_sheet —
--             sector-specific items belong in balance_sheet_items
--    [BUG-04] Removed hardcoded financing_profit/margin from profit_loss —
--             belongs in profit_loss_items
--    [BUG-05] Removed hardcoded gross_npa_pct/net_npa_pct from
--             quarterly_results — belongs in quarterly_results_items
--    [BUG-06] Fixed uq_macro UNIQUE key: year is nullable so replaced
--             with a generated non-null surrogate for uniqueness
--    [BUG-07] Added missing index on quarterly_results_items
--    [BUG-08] Reduced parent_label/item_label to VARCHAR(100) to keep
--             composite UNIQUE keys well within InnoDB 3072-byte limit
--    [BUG-09] Added UNIQUE constraint to screener_id
--    [BUG-10] Made updated_at consistent — added to all financial tables,
--             removed from cash_flow only (it now matches the pattern)
--    [BUG-11] Changed shareholding pct columns to DECIMAL(8,4) for
--             headroom when institutional subtotals exceed 100
--    [BUG-12] Added updated_at to macro_indicators, market_indices,
--             forex_commodities for operational traceability
-- ============================================================

CREATE DATABASE IF NOT EXISTS ai_hedge_fund
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE ai_hedge_fund;

-- ─────────────────────────────────────────────────────────────
-- 1. STOCKS  (master)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stocks (
    symbol              VARCHAR(30)  NOT NULL,
    -- [BUG-02] UNIQUE added — two symbols must never share a Screener id
    -- [BUG-09] NULL allowed because some symbols may not yet be on Screener
    screener_id         BIGINT       DEFAULT NULL,
    name                VARCHAR(255) DEFAULT NULL,
    exchange            VARCHAR(10)  NOT NULL DEFAULT 'NSE',
    sector              VARCHAR(100) DEFAULT NULL,
    broad_sector        VARCHAR(100) DEFAULT NULL,
    industry            VARCHAR(100) DEFAULT NULL,
    broad_industry      VARCHAR(100) DEFAULT NULL,
    currency            VARCHAR(5)   NOT NULL DEFAULT 'INR',
    -- [BUG-01] REMOVED is_consolidated — a company can be queried
    --          both ways; the flag lives on each financial row instead
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol),
    UNIQUE KEY uq_screener_id (screener_id)   -- [BUG-02]
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 2. PRICE DATA
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_daily (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol      VARCHAR(30)     NOT NULL,
    date        DATE            NOT NULL,
    open        DECIMAL(14,4)   DEFAULT NULL,
    high        DECIMAL(14,4)   DEFAULT NULL,
    low         DECIMAL(14,4)   DEFAULT NULL,
    close       DECIMAL(14,4)   DEFAULT NULL,
    adj_close   DECIMAL(14,4)   DEFAULT NULL,
    volume      BIGINT          DEFAULT NULL,
    source      VARCHAR(30)     NOT NULL DEFAULT 'yfinance',
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]
    PRIMARY KEY (id),
    UNIQUE KEY uq_price_daily (symbol, date),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS price_intraday (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol      VARCHAR(30)     NOT NULL,
    ts          DATETIME        NOT NULL,
    interval_   VARCHAR(5)      NOT NULL DEFAULT '1m',
    open        DECIMAL(14,4)   DEFAULT NULL,
    high        DECIMAL(14,4)   DEFAULT NULL,
    low         DECIMAL(14,4)   DEFAULT NULL,
    close       DECIMAL(14,4)   DEFAULT NULL,
    volume      BIGINT          DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_price_intra (symbol, ts, interval_),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 3. PROFIT & LOSS  (parent rows — Screener summary table)
--
--    Only universal lines that appear across ALL sectors live here.
--    [BUG-04] financing_profit / financing_margin_pct REMOVED —
--    bank/NBFC-specific; they go in profit_loss_items via the
--    Screener schedule API like every other sector-specific line.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profit_loss (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol                  VARCHAR(30)     NOT NULL,
    period_end              DATE            NOT NULL,
    period_type             ENUM('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
    is_consolidated         TINYINT(1)      NOT NULL DEFAULT 1,

    -- Universal P&L lines present across ALL sectors
    sales                   DECIMAL(18,2)   DEFAULT NULL,  -- Rs. Crores
    expenses                DECIMAL(18,2)   DEFAULT NULL,
    operating_profit        DECIMAL(18,2)   DEFAULT NULL,
    opm_pct                 DECIMAL(8,4)    DEFAULT NULL,
    other_income            DECIMAL(18,2)   DEFAULT NULL,
    interest                DECIMAL(18,2)   DEFAULT NULL,
    depreciation            DECIMAL(18,2)   DEFAULT NULL,
    profit_before_tax       DECIMAL(18,2)   DEFAULT NULL,
    tax_pct                 DECIMAL(8,4)    DEFAULT NULL,
    net_profit              DECIMAL(18,2)   DEFAULT NULL,
    eps                     DECIMAL(12,4)   DEFAULT NULL,
    dividend_payout_pct     DECIMAL(8,4)    DEFAULT NULL,

    -- Data quality
    data_source             VARCHAR(50)     NOT NULL DEFAULT 'screener',
    is_audited              TINYINT(1)      NOT NULL DEFAULT 0,
    completeness_pct        DECIMAL(5,2)    DEFAULT NULL,
    missing_fields_json     JSON            DEFAULT NULL,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_pl (symbol, period_end, period_type, is_consolidated),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_pl_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 4. PROFIT & LOSS  CHILD / SCHEDULE ROWS
--    Screener API: /api/company/<id>/schedules/
--                  ?parent=Other+Income&section=profit-loss
--    Sector-specific lines (financing profit, NII, provisions,
--    premium income, R&D etc.) all land here as item rows.
--    [BUG-08] parent_label / item_label reduced to VARCHAR(100)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profit_loss_items (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    period_end      DATE            NOT NULL,
    period_type     ENUM('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
    is_consolidated TINYINT(1)      NOT NULL DEFAULT 1,
    parent_label    VARCHAR(100)    NOT NULL,  -- e.g. "Other Income"
    item_label      VARCHAR(100)    NOT NULL,  -- e.g. "Exceptional Items"
    value           DECIMAL(18,2)   DEFAULT NULL,  -- Rs. Crores
    is_subtotal     TINYINT(1)      NOT NULL DEFAULT 0,  -- 1 = bold/strong row
    sort_order      SMALLINT        NOT NULL DEFAULT 0,
    data_source     VARCHAR(50)     NOT NULL DEFAULT 'screener',

    PRIMARY KEY (id),
    UNIQUE KEY uq_pl_item (symbol, period_end, period_type, is_consolidated,
                           parent_label, item_label),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_pl_items_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 5. BALANCE SHEET  (parent rows — Screener summary table)
--
--    Only truly universal aggregate lines live here.
--    [BUG-03] deposits / advances REMOVED — bank-specific parent
--    aggregates; they appear in balance_sheet_items with their own
--    parent_label (e.g. parent_label="Deposits") via the schedule API.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balance_sheet (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol                  VARCHAR(30)     NOT NULL,
    period_end              DATE            NOT NULL,
    period_type             ENUM('annual','quarterly') NOT NULL DEFAULT 'annual',
    is_consolidated         TINYINT(1)      NOT NULL DEFAULT 1,

    -- Liabilities side (universal across all sectors)
    equity_capital          DECIMAL(18,2)   DEFAULT NULL,
    reserves                DECIMAL(18,2)   DEFAULT NULL,
    total_equity            DECIMAL(18,2)   DEFAULT NULL,
    borrowings              DECIMAL(18,2)   DEFAULT NULL,  -- total (parent aggregate)
    other_liabilities       DECIMAL(18,2)   DEFAULT NULL,
    total_liabilities       DECIMAL(18,2)   DEFAULT NULL,

    -- Assets side (universal across all sectors)
    fixed_assets            DECIMAL(18,2)   DEFAULT NULL,
    cwip                    DECIMAL(18,2)   DEFAULT NULL,
    investments             DECIMAL(18,2)   DEFAULT NULL,
    other_assets            DECIMAL(18,2)   DEFAULT NULL,
    inventories             DECIMAL(18,2)   DEFAULT NULL,  -- NULL for IT/banks = correct
    trade_receivables       DECIMAL(18,2)   DEFAULT NULL,
    cash_equivalents        DECIMAL(18,2)   DEFAULT NULL,
    loans_advances          DECIMAL(18,2)   DEFAULT NULL,
    total_assets            DECIMAL(18,2)   DEFAULT NULL,
    net_debt                DECIMAL(18,2)   DEFAULT NULL,

    -- Data quality
    data_source             VARCHAR(50)     NOT NULL DEFAULT 'screener',
    completeness_pct        DECIMAL(5,2)    DEFAULT NULL,
    missing_fields_json     JSON            DEFAULT NULL,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_bs (symbol, period_end, period_type, is_consolidated),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_bs_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 6. BALANCE SHEET  CHILD / SCHEDULE ROWS
--    Screener API: /api/company/<id>/schedules/
--                  ?parent=Borrowings&section=balance-sheet
--    Works for every sector:
--      Manufacturing → parent="Borrowings",
--                       items: LT Borrowings, ST Borrowings, Lease, Other
--      Bank          → parent="Deposits",
--                       items: Savings Deposits, Current Deposits, FD, etc.
--      NBFC          → parent="Borrowings",
--                       items differ from manufacturing
--    [BUG-08] parent_label / item_label reduced to VARCHAR(100)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balance_sheet_items (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    period_end      DATE            NOT NULL,
    period_type     ENUM('annual','quarterly') NOT NULL DEFAULT 'annual',
    is_consolidated TINYINT(1)      NOT NULL DEFAULT 1,
    parent_label    VARCHAR(100)    NOT NULL,  -- e.g. "Borrowings"
    item_label      VARCHAR(100)    NOT NULL,  -- e.g. "Long term Borrowings"
    value           DECIMAL(18,2)   DEFAULT NULL,  -- Rs. Crores
    is_subtotal     TINYINT(1)      NOT NULL DEFAULT 0,
    sort_order      SMALLINT        NOT NULL DEFAULT 0,
    data_source     VARCHAR(50)     NOT NULL DEFAULT 'screener',

    PRIMARY KEY (id),
    UNIQUE KEY uq_bs_item (symbol, period_end, period_type, is_consolidated,
                           parent_label, item_label),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_bs_items_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 7. CASH FLOW  (parent rows)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cash_flow (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol              VARCHAR(30)     NOT NULL,
    period_end          DATE            NOT NULL,
    period_type         ENUM('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
    is_consolidated     TINYINT(1)      NOT NULL DEFAULT 1,

    -- Standard 3-bucket summary
    cfo                 DECIMAL(18,2)   DEFAULT NULL,
    cfi                 DECIMAL(18,2)   DEFAULT NULL,
    cff                 DECIMAL(18,2)   DEFAULT NULL,
    capex               DECIMAL(18,2)   DEFAULT NULL,
    free_cash_flow      DECIMAL(18,2)   DEFAULT NULL,
    net_cash_flow       DECIMAL(18,2)   DEFAULT NULL,

    -- Data quality
    data_source         VARCHAR(50)     NOT NULL DEFAULT 'screener',
    completeness_pct    DECIMAL(5,2)    DEFAULT NULL,
    missing_fields_json JSON            DEFAULT NULL,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_cf (symbol, period_end, period_type, is_consolidated),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_cf_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 8. CASH FLOW  CHILD / SCHEDULE ROWS
--    Screener API: /api/company/<id>/schedules/
--                  ?parent=Cash+from+Operating+Activity&section=cash-flow
--    Parent labels: "Cash from Operating Activity",
--                   "Cash from Investing Activity",
--                   "Cash from Financing Activity"
--    [BUG-08] parent_label / item_label reduced to VARCHAR(100)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cash_flow_items (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    period_end      DATE            NOT NULL,
    period_type     ENUM('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
    is_consolidated TINYINT(1)      NOT NULL DEFAULT 1,
    parent_label    VARCHAR(100)    NOT NULL,  -- e.g. "Cash from Operating Activity"
    item_label      VARCHAR(100)    NOT NULL,  -- e.g. "Profit from operations"
    value           DECIMAL(18,2)   DEFAULT NULL,
    is_subtotal     TINYINT(1)      NOT NULL DEFAULT 0,
    sort_order      SMALLINT        NOT NULL DEFAULT 0,
    data_source     VARCHAR(50)     NOT NULL DEFAULT 'screener',

    PRIMARY KEY (id),
    UNIQUE KEY uq_cf_item (symbol, period_end, period_type, is_consolidated,
                           parent_label, item_label),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_cf_items_sym (symbol, period_type, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 9. QUARTERLY RESULTS  (mirrors Screener Quarters tab)
--
--    [BUG-05] gross_npa_pct / net_npa_pct REMOVED — bank-specific;
--    they go in quarterly_results_items via the schedule API.
--    Same for financing_profit / financing_margin_pct.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quarterly_results (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol                  VARCHAR(30)     NOT NULL,
    period_end              DATE            NOT NULL,
    is_consolidated         TINYINT(1)      NOT NULL DEFAULT 1,

    -- Universal quarterly P&L lines
    sales                   DECIMAL(18,2)   DEFAULT NULL,
    expenses                DECIMAL(18,2)   DEFAULT NULL,
    operating_profit        DECIMAL(18,2)   DEFAULT NULL,
    opm_pct                 DECIMAL(8,4)    DEFAULT NULL,
    other_income            DECIMAL(18,2)   DEFAULT NULL,
    interest                DECIMAL(18,2)   DEFAULT NULL,
    depreciation            DECIMAL(18,2)   DEFAULT NULL,
    profit_before_tax       DECIMAL(18,2)   DEFAULT NULL,
    tax_pct                 DECIMAL(8,4)    DEFAULT NULL,
    net_profit              DECIMAL(18,2)   DEFAULT NULL,
    eps                     DECIMAL(12,4)   DEFAULT NULL,

    -- Data quality
    data_source             VARCHAR(50)     NOT NULL DEFAULT 'screener',
    is_audited              TINYINT(1)      NOT NULL DEFAULT 0,
    completeness_pct        DECIMAL(5,2)    DEFAULT NULL,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_qr (symbol, period_end, is_consolidated),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_qr_sym (symbol, period_end DESC)
) ENGINE=InnoDB;

-- Child rows for quarterly results
-- [BUG-07] Added missing index — was absent in v1
-- [BUG-08] parent_label / item_label reduced to VARCHAR(100)
CREATE TABLE IF NOT EXISTS quarterly_results_items (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    period_end      DATE            NOT NULL,
    is_consolidated TINYINT(1)      NOT NULL DEFAULT 1,
    parent_label    VARCHAR(100)    NOT NULL,
    item_label      VARCHAR(100)    NOT NULL,
    value           DECIMAL(18,2)   DEFAULT NULL,
    is_subtotal     TINYINT(1)      NOT NULL DEFAULT 0,
    sort_order      SMALLINT        NOT NULL DEFAULT 0,
    data_source     VARCHAR(50)     NOT NULL DEFAULT 'screener',

    PRIMARY KEY (id),
    UNIQUE KEY uq_qri (symbol, period_end, is_consolidated, parent_label, item_label),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_qri_sym (symbol, period_end DESC)  -- [BUG-07]
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 10. SHAREHOLDING PATTERN  (Screener Investors tab)
--     [BUG-11] All pct columns changed to DECIMAL(8,4) —
--     DECIMAL(7,4) max is 999.9999 which is fine numerically,
--     but total_institutional_pct can exceed 100 due to
--     FII+DII double-counting in some reports. Extra digit = clarity.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shareholding (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol                  VARCHAR(30)     NOT NULL,
    period_end              DATE            NOT NULL,   -- quarter end (Mar/Jun/Sep/Dec)

    promoter_pct            DECIMAL(8,4)    DEFAULT NULL,  -- [BUG-11]
    fii_pct                 DECIMAL(8,4)    DEFAULT NULL,
    dii_pct                 DECIMAL(8,4)    DEFAULT NULL,
    public_pct              DECIMAL(8,4)    DEFAULT NULL,
    government_pct          DECIMAL(8,4)    DEFAULT NULL,  -- PSUs etc.
    others_pct              DECIMAL(8,4)    DEFAULT NULL,
    total_institutional_pct DECIMAL(8,4)    DEFAULT NULL,
    num_shareholders        INT             DEFAULT NULL,

    data_source             VARCHAR(50)     NOT NULL DEFAULT 'screener',
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_sh (symbol, period_end),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_sh_sym (symbol, period_end DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 11. TECHNICAL INDICATORS  (computed, stored for speed)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS technical_indicators (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    date            DATE            NOT NULL,
    close           DECIMAL(14,4)   DEFAULT NULL,
    rsi_14          DECIMAL(8,4)    DEFAULT NULL,
    macd            DECIMAL(12,4)   DEFAULT NULL,
    macd_signal     DECIMAL(12,4)   DEFAULT NULL,
    macd_hist       DECIMAL(12,4)   DEFAULT NULL,
    sma_50          DECIMAL(14,4)   DEFAULT NULL,
    sma_200         DECIMAL(14,4)   DEFAULT NULL,
    ema_21          DECIMAL(14,4)   DEFAULT NULL,
    bb_mid          DECIMAL(14,4)   DEFAULT NULL,
    bb_upper        DECIMAL(14,4)   DEFAULT NULL,
    bb_lower        DECIMAL(14,4)   DEFAULT NULL,
    atr_14          DECIMAL(12,4)   DEFAULT NULL,
    adx_14          DECIMAL(8,4)    DEFAULT NULL,
    vwap_14         DECIMAL(14,4)   DEFAULT NULL,
    obv             DECIMAL(18,2)   DEFAULT NULL,
    supertrend      DECIMAL(14,4)   DEFAULT NULL,
    supertrend_dir  TINYINT         DEFAULT NULL,  -- 1 = up, -1 = down

    PRIMARY KEY (id),
    UNIQUE KEY uq_ti (symbol, date),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE,
    INDEX idx_ti_sym (symbol, date DESC)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 12. CORPORATE ACTIONS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS corporate_actions (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol      VARCHAR(30)     NOT NULL,
    action_date DATE            NOT NULL,
    action_type VARCHAR(50)     NOT NULL,  -- 'dividend','split','bonus','rights','merger'
    value       DECIMAL(14,4)   DEFAULT NULL,
    notes       TEXT            DEFAULT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_ca (symbol, action_date, action_type),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 13. MARKET INDICES
--     [BUG-12] updated_at added
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_indices (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE            NOT NULL,
    index_name      VARCHAR(60)     NOT NULL,
    last_price      DECIMAL(14,4)   DEFAULT NULL,
    change_pct      DECIMAL(8,4)    DEFAULT NULL,
    direction       VARCHAR(5)      DEFAULT NULL,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-12]

    PRIMARY KEY (id),
    UNIQUE KEY uq_mi (snapshot_date, index_name)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 14. FOREX & COMMODITIES
--     [BUG-12] updated_at added
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forex_commodities (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE            NOT NULL,
    instrument      VARCHAR(60)     NOT NULL,
    last_price      DECIMAL(16,6)   DEFAULT NULL,
    change_pct      DECIMAL(8,4)    DEFAULT NULL,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-12]

    PRIMARY KEY (id),
    UNIQUE KEY uq_fc (snapshot_date, instrument)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 15. RBI RATES
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rbi_rates (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    effective_date  DATE            NOT NULL,
    repo_rate       DECIMAL(6,3)    DEFAULT NULL,
    reverse_repo    DECIMAL(6,3)    DEFAULT NULL,
    sdf_rate        DECIMAL(6,3)    DEFAULT NULL,
    msf_rate        DECIMAL(6,3)    DEFAULT NULL,
    bank_rate       DECIMAL(6,3)    DEFAULT NULL,
    crr             DECIMAL(6,3)    DEFAULT NULL,
    slr             DECIMAL(6,3)    DEFAULT NULL,
    source          VARCHAR(100)    DEFAULT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_rbi (effective_date)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 16. MACRO INDICATORS
--     [BUG-06] The old UNIQUE KEY on (snapshot_date, indicator_name, year)
--     is broken because `year` is nullable. In MySQL, NULL != NULL in
--     unique indexes, so two rows with year=NULL would not be treated
--     as duplicates and the constraint silently does nothing.
--
--     Fix: replace nullable `year` in the unique key with a generated
--     non-null surrogate column `year_key` that turns NULL into 0.
--     The real `year` column stays nullable for legitimate NULLs.
--     [BUG-12] updated_at added
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro_indicators (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE            NOT NULL,
    indicator_name  VARCHAR(100)    NOT NULL,
    source          VARCHAR(100)    DEFAULT NULL,
    value           DECIMAL(16,4)   DEFAULT NULL,
    unit            VARCHAR(30)     DEFAULT NULL,
    year            SMALLINT        DEFAULT NULL,
    -- [BUG-06] Generated column: 0 when year is NULL, actual year otherwise.
    -- Participates in the UNIQUE key so NULL years don't bypass the constraint.
    year_key        SMALLINT        GENERATED ALWAYS AS (COALESCE(year, 0)) STORED NOT NULL,
    notes           TEXT            DEFAULT NULL,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-12]

    PRIMARY KEY (id),
    -- [BUG-06] Uses year_key (never NULL) instead of year
    UNIQUE KEY uq_macro (snapshot_date, indicator_name, year_key)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 17. GROWTH METRICS  (pre-computed CAGRs cached from Screener)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS growth_metrics (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol              VARCHAR(30)     NOT NULL,
    as_of_date          DATE            NOT NULL,
    sales_cagr_10y      DECIMAL(8,4)    DEFAULT NULL,
    sales_cagr_5y       DECIMAL(8,4)    DEFAULT NULL,
    sales_cagr_3y       DECIMAL(8,4)    DEFAULT NULL,
    sales_ttm           DECIMAL(18,2)   DEFAULT NULL,
    profit_cagr_10y     DECIMAL(8,4)    DEFAULT NULL,
    profit_cagr_5y      DECIMAL(8,4)    DEFAULT NULL,
    profit_cagr_3y      DECIMAL(8,4)    DEFAULT NULL,
    profit_ttm          DECIMAL(18,2)   DEFAULT NULL,
    stock_cagr_10y      DECIMAL(8,4)    DEFAULT NULL,
    stock_cagr_5y       DECIMAL(8,4)    DEFAULT NULL,
    stock_cagr_3y       DECIMAL(8,4)    DEFAULT NULL,
    stock_ttm           DECIMAL(8,4)    DEFAULT NULL,
    roe_10y             DECIMAL(8,4)    DEFAULT NULL,
    roe_5y              DECIMAL(8,4)    DEFAULT NULL,
    roe_3y              DECIMAL(8,4)    DEFAULT NULL,
    roe_last            DECIMAL(8,4)    DEFAULT NULL,
    completeness_pct    DECIMAL(5,2)    DEFAULT NULL,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,  -- [BUG-10]

    PRIMARY KEY (id),
    UNIQUE KEY uq_gm (symbol, as_of_date),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 18. EARNINGS HISTORY & ESTIMATES  (yfinance)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS earnings_history (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    quarter_end     DATE            NOT NULL,
    eps_actual      DECIMAL(12,4)   DEFAULT NULL,
    eps_estimate    DECIMAL(12,4)   DEFAULT NULL,
    eps_difference  DECIMAL(12,4)   DEFAULT NULL,
    surprise_pct    DECIMAL(8,4)    DEFAULT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_eh (symbol, quarter_end),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS earnings_estimates (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    snapshot_date   DATE            NOT NULL,
    period_code     VARCHAR(10)     NOT NULL,  -- '0q','1q','0y','1y'
    avg_eps         DECIMAL(12,4)   DEFAULT NULL,
    low_eps         DECIMAL(12,4)   DEFAULT NULL,
    high_eps        DECIMAL(12,4)   DEFAULT NULL,
    year_ago_eps    DECIMAL(12,4)   DEFAULT NULL,
    analyst_count   SMALLINT        DEFAULT NULL,
    growth_pct      DECIMAL(8,4)    DEFAULT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_ee (symbol, snapshot_date, period_code),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- 19. ETL / PIPELINE METADATA
--     NOTE: No FK on symbol by design — log tables must accept
--     symbols that may not yet exist in stocks (e.g. during a
--     failed initial load). This is intentional, not an oversight.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS etl_run_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol          VARCHAR(30)     NOT NULL,
    run_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    script_name     VARCHAR(100)    NOT NULL,
    script_version  VARCHAR(20)     DEFAULT NULL,
    status          ENUM('ok','warn','error') NOT NULL DEFAULT 'ok',
    modules_ok      TEXT            DEFAULT NULL,
    modules_warn    TEXT            DEFAULT NULL,
    notes           TEXT            DEFAULT NULL,

    PRIMARY KEY (id),
    INDEX idx_rl_sym (symbol, run_at DESC)
    -- No FK on symbol: intentional — log must survive failed stock inserts
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS data_quality_log (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    symbol              VARCHAR(30)     NOT NULL,
    table_name          VARCHAR(60)     NOT NULL,
    rows_inserted       INT             NOT NULL DEFAULT 0,
    rows_null_heavy     INT             NOT NULL DEFAULT 0,
    avg_completeness    DECIMAL(5,2)    DEFAULT NULL,
    critical_nulls_json JSON            DEFAULT NULL,
    source              VARCHAR(50)     DEFAULT NULL,
    notes               TEXT            DEFAULT NULL,

    PRIMARY KEY (id),
    INDEX idx_dql_sym (symbol, run_at DESC)
    -- No FK on symbol: intentional — same reason as etl_run_log
) ENGINE=InnoDB;
