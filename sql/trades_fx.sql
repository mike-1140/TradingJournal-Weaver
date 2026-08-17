SET AUTOCOMMIT=0;
--
-- Tabellenstruktur für Tabelle `trades_fx`
--
DROP TABLE IF EXISTS `__PREFIX__trades_fx`;
CREATE TABLE `__PREFIX__trades_fx` (
   `id` int(11) NOT NULL auto_increment,
   `assetCategory` varchar(20) DEFAULT NULL,
   `tradeID` varchar(20) DEFAULT NULL,
   `ibOrderID` varchar(50) DEFAULT NULL,
   `symbol` varchar(50) DEFAULT NULL,
   `baseCurrency` varchar(20) DEFAULT NULL,
   `quoteCurrency` varchar(20) DEFAULT NULL,
   `baseAmount`DECIMAL(19, 4) DEFAULT 0.00,
   `quoteAmount`DECIMAL(19, 4) DEFAULT 0.00,
   `fxRate`DECIMAL(19, 4) DEFAULT 0.00,
   `commission`DECIMAL(19, 4) DEFAULT 0.00,
   `dateTime` datetime DEFAULT NULL,
   `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
   `checksum` varchar(50) DEFAULT NULL,

  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
