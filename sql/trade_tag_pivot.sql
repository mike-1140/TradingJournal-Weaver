SET AUTOCOMMIT=0;

--
-- Datenbank: `trading-journal`
--
--
-- Tabellenstruktur für Tabelle `trade_tag_pivot`
--

DROP TABLE IF EXISTS `__PREFIX__trade_tag_pivot`;

CREATE TABLE `__PREFIX__trade_tag_pivot` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tag_id` bigint(20) UNSIGNED NOT NULL,
  `trade_id` varchar(50) COLLATE latin1_german1_ci NOT NULL,
  `trade_type` ENUM('open','closed','spread','fx') NOT NULL,
  `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
  `tagged_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_tag_trade_type` (`tag_id`, `trade_id`, `trade_type`),
  INDEX `idx_tag_id` (`tag_id`),
  INDEX `idx_trade_id` (`trade_id`),
  INDEX `idx_trade_type_environment` (`trade_type`, `environment`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1 COLLATE=latin1_german1_ci AUTO_INCREMENT=1;

