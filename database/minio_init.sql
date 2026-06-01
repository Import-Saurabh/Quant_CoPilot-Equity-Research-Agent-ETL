-- ─────────────────────────────────────────────────────────────────────────────
-- minio_init.sql
-- PDF document metadata table — run after mysql_schema_v2.sql
--
-- Tracks every PDF stored in MinIO so we can serve signed URLs, run queries
-- like "all annual reports for TCS", and avoid re-downloading duplicates.
--
-- Placement:  database/minio_init.sql
-- Auto-load:  add to docker-compose.yml initdb volume as 02_minio.sql
--             - ./database/minio_init.sql:/docker-entrypoint-initdb.d/02_minio.sql:ro
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pdf_documents (
    id             INT           NOT NULL AUTO_INCREMENT,
    symbol         VARCHAR(20)   NOT NULL COMMENT 'Normalised ticker, e.g. TCS',
    company_id     INT               NULL COMMENT 'FK → stocks_master.id (nullable: filled lazily)',
    document_type  VARCHAR(100)  NOT NULL COMMENT 'annual_report | concall',
    fiscal_year    INT               NULL COMMENT '4-digit FY end year, e.g. 2024',
    file_name      VARCHAR(255)  NOT NULL COMMENT 'Bare filename stored in MinIO',
    object_path    TEXT          NOT NULL COMMENT 'Full MinIO path: bucket/symbol/year_title.pdf',
    uploaded_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    -- Prevent duplicate rows for the same document on re-runs.
    -- ON DUPLICATE KEY UPDATE in pdf_db_loader.py relies on this constraint.
    UNIQUE KEY uq_pdf_doc (symbol, document_type, fiscal_year, file_name),

    -- Speed up common lookups
    INDEX idx_symbol      (symbol),
    INDEX idx_doc_type    (document_type),
    INDEX idx_fiscal_year (fiscal_year),
    INDEX idx_company_id  (company_id)

) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Metadata for PDFs stored in MinIO (annual reports, concall transcripts)';