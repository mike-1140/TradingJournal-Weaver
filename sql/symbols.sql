SET AUTOCOMMIT=0;
--
-- Tabellenstruktur für Tabelle `symbols`
--
DROP TABLE IF EXISTS `__PREFIX__symbols`;
CREATE TABLE `__PREFIX__symbols` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `assetCategory` varchar(20) DEFAULT NULL,
  `symbol` varchar(50) DEFAULT NULL,
  `underlyingSymbol` varchar(50) DEFAULT NULL,
  `isin` VARCHAR(12),
  `conid` varchar(20)  DEFAULT NULL,                   -- Verweis auf die Aktie (z.B. AAPL)
  `underlyingConid`  varchar(20) DEFAULT NULL,
  `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
  UNIQUE KEY unique_symbol (assetCategory, symbol),
  PRIMARY KEY  (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
