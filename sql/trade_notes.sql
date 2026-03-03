SET AUTOCOMMIT=0;

--
-- Datenbank: `trading-journal`
--
--
-- Tabellenstruktur für Tabelle `trade_notes`
--

DROP TABLE IF EXISTS `__PREFIX__trade_notes`;

CREATE TABLE `__PREFIX__trade_notes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `trade_id` varchar(50) COLLATE latin1_german1_ci DEFAULT NULL,
  `strategyID` varchar(50) COLLATE latin1_german1_ci DEFAULT NULL,
  `trade_type` ENUM('open','closed','spread') NOT NULL,
  `note_type` ENUM('entry_plan','exit_reason','lesson_learned','general') NOT NULL DEFAULT 'general',
  `title` varchar(200) COLLATE latin1_german1_ci DEFAULT NULL,
  `content` text COLLATE latin1_german1_ci NOT NULL,
  `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_trade_id` (`trade_id`),
  INDEX `idx_strategyID` (`strategyID`),
  INDEX `idx_trade_type_environment` (`trade_type`, `environment`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1 COLLATE=latin1_german1_ci AUTO_INCREMENT=1;
