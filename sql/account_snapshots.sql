SET AUTOCOMMIT=0;
--
-- Tabellenstruktur für Tabelle `account_snapshots`
-- Tägliche NAV-Snapshots aus IBKR Activity Statement CSV
--
DROP TABLE IF EXISTS `__PREFIX__account_snapshots`;
CREATE TABLE `__PREFIX__account_snapshots` (
  `id`                     int(11) NOT NULL AUTO_INCREMENT,
  `snapshot_date`          date NOT NULL,
  `environment`            ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,

  -- Nettovermögenswert
  `nav_prior`              DECIMAL(19, 4) DEFAULT NULL,
  `nav_current`            DECIMAL(19, 4) DEFAULT NULL,
  `nav_change`             DECIMAL(19, 4) DEFAULT NULL,
  `twrr`                   DECIMAL(14, 8) DEFAULT NULL,

  -- Veränderung des NAV
  `starting_value`         DECIMAL(19, 4) DEFAULT NULL,
  `mtm_pnl`                DECIMAL(19, 4) DEFAULT NULL,
  `commissions_eur`        DECIMAL(19, 4) DEFAULT NULL,
  `ending_value`           DECIMAL(19, 4) DEFAULT NULL,

  -- Cash-Positionen
  `cash_eur`               DECIMAL(19, 4) DEFAULT NULL,
  `cash_usd`               DECIMAL(19, 4) DEFAULT NULL,
  `forex_translation_pnl`  DECIMAL(19, 4) DEFAULT NULL,

  -- Realisierter / unrealisierter P&L
  `realized_pnl_eur`       DECIMAL(19, 4) DEFAULT NULL,
  `unrealized_pnl_eur`     DECIMAL(19, 4) DEFAULT NULL,

  -- MTD / YTD
  `mtd_pnl`                DECIMAL(19, 4) DEFAULT NULL,
  `ytd_pnl`                DECIMAL(19, 4) DEFAULT NULL,

  `imported_at`            datetime DEFAULT NULL,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_date_env` (`snapshot_date`, `environment`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
