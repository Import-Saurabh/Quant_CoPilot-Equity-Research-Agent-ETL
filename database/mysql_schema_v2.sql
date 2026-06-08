-- =============================================================================
-- Quant Copilot — ai_hedge_fund database schema
-- Generated: 2026-06-08
-- Engine: MySQL 8.0 | Charset: utf8mb4
-- =============================================================================

CREATE DATABASE IF NOT EXISTS ai_hedge_fund
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE ai_hedge_fund;

SET FOREIGN_KEY_CHECKS = 0;

-- =============================================================================
-- CORE — stocks (parent of all symbol-keyed tables)
-- =============================================================================

CREATE TABLE IF NOT EXISTS stocks (
  symbol           varchar(30)    NOT NULL,
  screener_id      bigint         DEFAULT NULL,
  name             varchar(255)   DEFAULT NULL,
  exchange         varchar(10)    NOT NULL DEFAULT 'NSE',
  sector           varchar(100)   DEFAULT NULL,
  broad_sector     varchar(100)   DEFAULT NULL,
  industry         varchar(100)   DEFAULT NULL,
  broad_industry   varchar(100)   DEFAULT NULL,
  currency         varchar(5)     NOT NULL DEFAULT 'INR',
  market_cap_cr    decimal(18,2)  DEFAULT NULL,
  created_at       datetime       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       datetime       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol),
  UNIQUE KEY uq_screener_id (screener_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- FINANCIALS — P&L
-- =============================================================================

CREATE TABLE IF NOT EXISTS profit_loss (
  id                   bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol               varchar(30)     NOT NULL,
  period_end           date            NOT NULL,
  period_type          enum('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
  is_consolidated      tinyint(1)      NOT NULL DEFAULT '1',
  sales                decimal(18,2)   DEFAULT NULL,
  expenses             decimal(18,2)   DEFAULT NULL,
  operating_profit     decimal(18,2)   DEFAULT NULL,
  opm_pct              decimal(8,4)    DEFAULT NULL,
  other_income         decimal(18,2)   DEFAULT NULL,
  interest             decimal(18,2)   DEFAULT NULL,
  depreciation         decimal(18,2)   DEFAULT NULL,
  profit_before_tax    decimal(18,2)   DEFAULT NULL,
  tax_pct              decimal(8,4)    DEFAULT NULL,
  net_profit           decimal(18,2)   DEFAULT NULL,
  eps                  decimal(12,4)   DEFAULT NULL,
  dividend_payout_pct  decimal(8,4)    DEFAULT NULL,
  data_source          varchar(50)     NOT NULL DEFAULT 'screener',
  is_audited           tinyint(1)      NOT NULL DEFAULT '0',
  completeness_pct     decimal(5,2)    DEFAULT NULL,
  missing_fields_json  json            DEFAULT NULL,
  updated_at           datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pl (symbol,period_end,period_type,is_consolidated),
  KEY idx_pl_sym (symbol,period_type,period_end DESC),
  CONSTRAINT profit_loss_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS profit_loss_items (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  period_end       date            NOT NULL,
  period_type      enum('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
  is_consolidated  tinyint(1)      NOT NULL DEFAULT '1',
  parent_label     varchar(100)    NOT NULL,
  item_label       varchar(100)    NOT NULL,
  value            decimal(18,2)   DEFAULT NULL,
  is_subtotal      tinyint(1)      NOT NULL DEFAULT '0',
  sort_order       smallint        NOT NULL DEFAULT '0',
  data_source      varchar(50)     NOT NULL DEFAULT 'screener',
  PRIMARY KEY (id),
  UNIQUE KEY uq_pl_item (symbol,period_end,period_type,is_consolidated,parent_label,item_label),
  KEY idx_pl_items_sym (symbol,period_type,period_end DESC),
  CONSTRAINT profit_loss_items_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- FINANCIALS — Balance Sheet
-- =============================================================================

CREATE TABLE IF NOT EXISTS balance_sheet (
  id                   bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol               varchar(30)     NOT NULL,
  period_end           date            NOT NULL,
  period_type          enum('annual','quarterly') NOT NULL DEFAULT 'annual',
  is_consolidated      tinyint(1)      NOT NULL DEFAULT '1',
  equity_capital       decimal(18,2)   DEFAULT NULL,
  reserves             decimal(18,2)   DEFAULT NULL,
  total_equity         decimal(18,2)   DEFAULT NULL,
  borrowings           decimal(18,2)   DEFAULT NULL,
  other_liabilities    decimal(18,2)   DEFAULT NULL,
  total_liabilities    decimal(18,2)   DEFAULT NULL,
  fixed_assets         decimal(18,2)   DEFAULT NULL,
  cwip                 decimal(18,2)   DEFAULT NULL,
  investments          decimal(18,2)   DEFAULT NULL,
  other_assets         decimal(18,2)   DEFAULT NULL,
  inventories          decimal(18,2)   DEFAULT NULL,
  trade_receivables    decimal(18,2)   DEFAULT NULL,
  cash_equivalents     decimal(18,2)   DEFAULT NULL,
  loans_advances       decimal(18,2)   DEFAULT NULL,
  total_assets         decimal(18,2)   DEFAULT NULL,
  net_debt             decimal(18,2)   DEFAULT NULL,
  data_source          varchar(50)     NOT NULL DEFAULT 'screener',
  completeness_pct     decimal(5,2)    DEFAULT NULL,
  missing_fields_json  json            DEFAULT NULL,
  updated_at           datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_bs (symbol,period_end,period_type,is_consolidated),
  KEY idx_bs_sym (symbol,period_type,period_end DESC),
  CONSTRAINT balance_sheet_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS balance_sheet_items (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  period_end       date            NOT NULL,
  period_type      enum('annual','quarterly') NOT NULL DEFAULT 'annual',
  is_consolidated  tinyint(1)      NOT NULL DEFAULT '1',
  parent_label     varchar(100)    NOT NULL,
  item_label       varchar(100)    NOT NULL,
  value            decimal(18,2)   DEFAULT NULL,
  is_subtotal      tinyint(1)      NOT NULL DEFAULT '0',
  sort_order       smallint        NOT NULL DEFAULT '0',
  data_source      varchar(50)     NOT NULL DEFAULT 'screener',
  PRIMARY KEY (id),
  UNIQUE KEY uq_bs_item (symbol,period_end,period_type,is_consolidated,parent_label,item_label),
  KEY idx_bs_items_sym (symbol,period_type,period_end DESC),
  CONSTRAINT balance_sheet_items_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- FINANCIALS — Cash Flow
-- =============================================================================

CREATE TABLE IF NOT EXISTS cash_flow (
  id                   bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol               varchar(30)     NOT NULL,
  period_end           date            NOT NULL,
  period_type          enum('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
  is_consolidated      tinyint(1)      NOT NULL DEFAULT '1',
  cfo                  decimal(18,2)   DEFAULT NULL,
  cfi                  decimal(18,2)   DEFAULT NULL,
  cff                  decimal(18,2)   DEFAULT NULL,
  capex                decimal(18,2)   DEFAULT NULL,
  free_cash_flow       decimal(18,2)   DEFAULT NULL,
  net_cash_flow        decimal(18,2)   DEFAULT NULL,
  data_source          varchar(50)     NOT NULL DEFAULT 'screener',
  completeness_pct     decimal(5,2)    DEFAULT NULL,
  missing_fields_json  json            DEFAULT NULL,
  updated_at           datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cf (symbol,period_end,period_type,is_consolidated),
  KEY idx_cf_sym (symbol,period_type,period_end DESC),
  CONSTRAINT cash_flow_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS cash_flow_items (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  period_end       date            NOT NULL,
  period_type      enum('annual','quarterly','ttm') NOT NULL DEFAULT 'annual',
  is_consolidated  tinyint(1)      NOT NULL DEFAULT '1',
  parent_label     varchar(100)    NOT NULL,
  item_label       varchar(100)    NOT NULL,
  value            decimal(18,2)   DEFAULT NULL,
  is_subtotal      tinyint(1)      NOT NULL DEFAULT '0',
  sort_order       smallint        NOT NULL DEFAULT '0',
  data_source      varchar(50)     NOT NULL DEFAULT 'screener',
  PRIMARY KEY (id),
  UNIQUE KEY uq_cf_item (symbol,period_end,period_type,is_consolidated,parent_label,item_label),
  KEY idx_cf_items_sym (symbol,period_type,period_end DESC),
  CONSTRAINT cash_flow_items_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- FINANCIALS — Quarterly Results
-- =============================================================================

CREATE TABLE IF NOT EXISTS quarterly_results (
  id                bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol            varchar(30)     NOT NULL,
  period_end        date            NOT NULL,
  is_consolidated   tinyint(1)      NOT NULL DEFAULT '1',
  sales             decimal(18,2)   DEFAULT NULL,
  expenses          decimal(18,2)   DEFAULT NULL,
  operating_profit  decimal(18,2)   DEFAULT NULL,
  opm_pct           decimal(8,4)    DEFAULT NULL,
  other_income      decimal(18,2)   DEFAULT NULL,
  interest          decimal(18,2)   DEFAULT NULL,
  depreciation      decimal(18,2)   DEFAULT NULL,
  profit_before_tax decimal(18,2)   DEFAULT NULL,
  tax_pct           decimal(8,4)    DEFAULT NULL,
  net_profit        decimal(18,2)   DEFAULT NULL,
  eps               decimal(12,4)   DEFAULT NULL,
  data_source       varchar(50)     NOT NULL DEFAULT 'screener',
  is_audited        tinyint(1)      NOT NULL DEFAULT '0',
  completeness_pct  decimal(5,2)    DEFAULT NULL,
  updated_at        datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_qr (symbol,period_end,is_consolidated),
  KEY idx_qr_sym (symbol,period_end DESC),
  CONSTRAINT quarterly_results_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS quarterly_results_items (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  period_end       date            NOT NULL,
  is_consolidated  tinyint(1)      NOT NULL DEFAULT '1',
  parent_label     varchar(100)    NOT NULL,
  item_label       varchar(100)    NOT NULL,
  value            decimal(18,2)   DEFAULT NULL,
  is_subtotal      tinyint(1)      NOT NULL DEFAULT '0',
  sort_order       smallint        NOT NULL DEFAULT '0',
  data_source      varchar(50)     NOT NULL DEFAULT 'screener',
  PRIMARY KEY (id),
  UNIQUE KEY uq_qri (symbol,period_end,is_consolidated,parent_label,item_label),
  KEY idx_qri_sym (symbol,period_end DESC),
  CONSTRAINT quarterly_results_items_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- MARKET DATA — Price, Technical Indicators
-- =============================================================================

CREATE TABLE IF NOT EXISTS price_daily (
  id         bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol     varchar(30)     NOT NULL,
  date       date            NOT NULL,
  open       decimal(14,4)   DEFAULT NULL,
  high       decimal(14,4)   DEFAULT NULL,
  low        decimal(14,4)   DEFAULT NULL,
  close      decimal(14,4)   DEFAULT NULL,
  adj_close  decimal(14,4)   DEFAULT NULL,
  volume     bigint          DEFAULT NULL,
  source     varchar(30)     NOT NULL DEFAULT 'yfinance',
  updated_at datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_price_daily (symbol,date),
  CONSTRAINT price_daily_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS technical_indicators (
  id             bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol         varchar(30)     NOT NULL,
  date           date            NOT NULL,
  close          decimal(14,4)   DEFAULT NULL,
  rsi_14         decimal(8,4)    DEFAULT NULL,
  macd           decimal(12,4)   DEFAULT NULL,
  macd_signal    decimal(12,4)   DEFAULT NULL,
  macd_hist      decimal(12,4)   DEFAULT NULL,
  sma_50         decimal(14,4)   DEFAULT NULL,
  sma_200        decimal(14,4)   DEFAULT NULL,
  ema_21         decimal(14,4)   DEFAULT NULL,
  bb_mid         decimal(14,4)   DEFAULT NULL,
  bb_upper       decimal(14,4)   DEFAULT NULL,
  bb_lower       decimal(14,4)   DEFAULT NULL,
  atr_14         decimal(12,4)   DEFAULT NULL,
  adx_14         decimal(8,4)    DEFAULT NULL,
  vwap_14        decimal(14,4)   DEFAULT NULL,
  obv            decimal(18,2)   DEFAULT NULL,
  supertrend     decimal(14,4)   DEFAULT NULL,
  supertrend_dir tinyint         DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ti (symbol,date),
  KEY idx_ti_sym (symbol,date DESC),
  CONSTRAINT technical_indicators_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- SHAREHOLDING & CORPORATE ACTIONS
-- =============================================================================

CREATE TABLE IF NOT EXISTS shareholding (
  id                      bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol                  varchar(30)     NOT NULL,
  period_end              date            NOT NULL,
  promoter_pct            decimal(8,4)    DEFAULT NULL,
  fii_pct                 decimal(8,4)    DEFAULT NULL,
  dii_pct                 decimal(8,4)    DEFAULT NULL,
  public_pct              decimal(8,4)    DEFAULT NULL,
  government_pct          decimal(8,4)    DEFAULT NULL,
  others_pct              decimal(8,4)    DEFAULT NULL,
  total_institutional_pct decimal(8,4)    DEFAULT NULL,
  num_shareholders        int             DEFAULT NULL,
  data_source             varchar(50)     NOT NULL DEFAULT 'screener',
  updated_at              datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sh (symbol,period_end),
  KEY idx_sh_sym (symbol,period_end DESC),
  CONSTRAINT shareholding_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS corporate_actions (
  id          bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol      varchar(30)     NOT NULL,
  action_date date            NOT NULL,
  action_type varchar(50)     NOT NULL,
  value       decimal(14,4)   DEFAULT NULL,
  notes       text,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ca (symbol,action_date,action_type),
  CONSTRAINT corporate_actions_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- GROWTH & ESTIMATES
-- =============================================================================

CREATE TABLE IF NOT EXISTS growth_metrics (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  as_of_date       date            NOT NULL,
  sales_cagr_10y   decimal(8,4)    DEFAULT NULL,
  sales_cagr_5y    decimal(8,4)    DEFAULT NULL,
  sales_cagr_3y    decimal(8,4)    DEFAULT NULL,
  sales_ttm        decimal(18,2)   DEFAULT NULL,
  profit_cagr_10y  decimal(8,4)    DEFAULT NULL,
  profit_cagr_5y   decimal(8,4)    DEFAULT NULL,
  profit_cagr_3y   decimal(8,4)    DEFAULT NULL,
  profit_ttm       decimal(18,2)   DEFAULT NULL,
  stock_cagr_10y   decimal(8,4)    DEFAULT NULL,
  stock_cagr_5y    decimal(8,4)    DEFAULT NULL,
  stock_cagr_3y    decimal(8,4)    DEFAULT NULL,
  stock_ttm        decimal(8,4)    DEFAULT NULL,
  roe_10y          decimal(8,4)    DEFAULT NULL,
  roe_5y           decimal(8,4)    DEFAULT NULL,
  roe_3y           decimal(8,4)    DEFAULT NULL,
  roe_last         decimal(8,4)    DEFAULT NULL,
  completeness_pct decimal(5,2)    DEFAULT NULL,
  updated_at       datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_gm (symbol,as_of_date),
  CONSTRAINT growth_metrics_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS eps_trend (
  id               bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol           varchar(30)     NOT NULL,
  snapshot_date    date            NOT NULL,
  period_code      varchar(10)     NOT NULL,
  current_est      decimal(12,4)   DEFAULT NULL,
  seven_days_ago   decimal(12,4)   DEFAULT NULL,
  thirty_days_ago  decimal(12,4)   DEFAULT NULL,
  sixty_days_ago   decimal(12,4)   DEFAULT NULL,
  ninety_days_ago  decimal(12,4)   DEFAULT NULL,
  updated_at       datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_et (symbol,snapshot_date,period_code),
  CONSTRAINT eps_trend_ibfk_1 FOREIGN KEY (symbol) REFERENCES stocks (symbol) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- MACRO — RBI Rates, Market Indices, Forex/Commodities, Macro Indicators
-- =============================================================================

CREATE TABLE IF NOT EXISTS rbi_rates (
  id             bigint unsigned NOT NULL AUTO_INCREMENT,
  effective_date date            NOT NULL,
  repo_rate      decimal(6,3)    DEFAULT NULL,
  reverse_repo   decimal(6,3)    DEFAULT NULL,
  sdf_rate       decimal(6,3)    DEFAULT NULL,
  msf_rate       decimal(6,3)    DEFAULT NULL,
  bank_rate      decimal(6,3)    DEFAULT NULL,
  crr            decimal(6,3)    DEFAULT NULL,
  slr            decimal(6,3)    DEFAULT NULL,
  source         varchar(100)    DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rbi (effective_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS market_indices (
  id            bigint unsigned NOT NULL AUTO_INCREMENT,
  snapshot_date date            NOT NULL,
  index_name    varchar(60)     NOT NULL,
  last_price    decimal(14,4)   DEFAULT NULL,
  change_pct    decimal(8,4)    DEFAULT NULL,
  direction     varchar(5)      DEFAULT NULL,
  updated_at    datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_mi (snapshot_date,index_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS forex_commodities (
  id            bigint unsigned NOT NULL AUTO_INCREMENT,
  snapshot_date date            NOT NULL,
  instrument    varchar(60)     NOT NULL,
  last_price    decimal(16,6)   DEFAULT NULL,
  change_pct    decimal(8,4)    DEFAULT NULL,
  updated_at    datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_fc (snapshot_date,instrument)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS macro_indicators (
  id             bigint unsigned NOT NULL AUTO_INCREMENT,
  snapshot_date  date            NOT NULL,
  indicator_name varchar(100)    NOT NULL,
  source         varchar(100)    DEFAULT NULL,
  value          decimal(16,4)   DEFAULT NULL,
  unit           varchar(30)     DEFAULT NULL,
  year           smallint        DEFAULT NULL,
  year_key       smallint        GENERATED ALWAYS AS (COALESCE(year, 0)) STORED NOT NULL,
  notes          text,
  updated_at     datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_macro (snapshot_date,indicator_name,year_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================
-- OPERATIONAL — ETL logs, Data Quality
-- =============================================================================

CREATE TABLE IF NOT EXISTS etl_run_log (
  id             bigint unsigned NOT NULL AUTO_INCREMENT,
  symbol         varchar(30)     NOT NULL,
  run_at         datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  script_name    varchar(100)    NOT NULL,
  script_version varchar(20)     DEFAULT NULL,
  status         enum('ok','warn','error') NOT NULL DEFAULT 'ok',
  modules_ok     text,
  modules_warn   text,
  notes          text,
  PRIMARY KEY (id),
  KEY idx_rl_sym (symbol,run_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS data_quality_log (
  id                  bigint unsigned NOT NULL AUTO_INCREMENT,
  run_at              datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  symbol              varchar(30)     NOT NULL,
  table_name          varchar(60)     NOT NULL,
  rows_inserted       int             NOT NULL DEFAULT '0',
  rows_null_heavy     int             NOT NULL DEFAULT '0',
  avg_completeness    decimal(5,2)    DEFAULT NULL,
  critical_nulls_json json            DEFAULT NULL,
  source              varchar(50)     DEFAULT NULL,
  notes               text,
  PRIMARY KEY (id),
  KEY idx_dql_sym (symbol,run_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- =============================================================================

SET FOREIGN_KEY_CHECKS = 1;
