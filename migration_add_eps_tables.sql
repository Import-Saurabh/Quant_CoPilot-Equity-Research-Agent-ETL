-- ─────────────────────────────────────────────────────────────────────────────
-- migration_add_eps_tables.sql
-- Run this once against ai_hedge_fund to create the two missing tables.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS `eps_trend` (
  `id`               bigint unsigned NOT NULL AUTO_INCREMENT,
  `symbol`           varchar(30)     NOT NULL,
  `snapshot_date`    date            NOT NULL,
  `period_code`      varchar(10)     NOT NULL,
  `current_est`      decimal(12,4)   DEFAULT NULL,
  `seven_days_ago`   decimal(12,4)   DEFAULT NULL,
  `thirty_days_ago`  decimal(12,4)   DEFAULT NULL,
  `sixty_days_ago`   decimal(12,4)   DEFAULT NULL,
  `ninety_days_ago`  decimal(12,4)   DEFAULT NULL,
  `updated_at`       datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_et` (`symbol`, `snapshot_date`, `period_code`),
  CONSTRAINT `eps_trend_ibfk_1`
    FOREIGN KEY (`symbol`) REFERENCES `stocks` (`symbol`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE IF NOT EXISTS `eps_revisions` (
  `id`            bigint unsigned NOT NULL AUTO_INCREMENT,
  `symbol`        varchar(30)     NOT NULL,
  `snapshot_date` date            NOT NULL,
  `period_code`   varchar(10)     NOT NULL,
  `up_last_7d`    smallint        DEFAULT NULL,
  `up_last_30d`   smallint        DEFAULT NULL,
  `down_last_30d` smallint        DEFAULT NULL,
  `down_last_7d`  smallint        DEFAULT NULL,
  `updated_at`    datetime        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_er` (`symbol`, `snapshot_date`, `period_code`),
  CONSTRAINT `eps_revisions_ibfk_1`
    FOREIGN KEY (`symbol`) REFERENCES `stocks` (`symbol`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;