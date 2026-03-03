SET AUTOCOMMIT=0;

--
-- Datenbank: `trading-journal`
--
-- --------------------------------------------------------
--
-- Tabellenstruktur für Tabelle `trades_raw`
--
DROP TABLE IF EXISTS `__PREFIX__trades_raw`;
CREATE TABLE `__PREFIX__trades_raw` (
   `id` int(11) NOT NULL auto_increment,
   `symID` int(11) DEFAULT NULL,
   `assetCategory` varchar(20) DEFAULT NULL,
   `subCategory` varchar(20) DEFAULT NULL,
   `symbol` varchar(50) DEFAULT NULL,
   `description` varchar(250) DEFAULT NULL,
   `underlyingSymbol` varchar(20) DEFAULT NULL,
   `conid` varchar(20)  DEFAULT NULL,
   `underlyingConid` varchar(20) DEFAULT NULL,
   `multiplier` DECIMAL(19, 4) DEFAULT 0.00,
   `strike` DECIMAL(19, 4) DEFAULT 0.00,
   `expiry` dateTime DEFAULT NULL,
   `putCall` varchar(20) DEFAULT NULL,
   `buySell` varchar(20) DEFAULT NULL,
   `dateTime` datetime DEFAULT NULL,
   `quantity` DECIMAL(19, 4) DEFAULT 0.00,
   `tradePrice` DECIMAL(19, 4) DEFAULT 0.00,
   `netCash` DECIMAL(19, 4) DEFAULT 0.00,
   `proceeds` DECIMAL(19, 4) DEFAULT 0.00,
   `ibCommission` DECIMAL(19, 4) DEFAULT 0.00,
   `currency`      varchar(5)      DEFAULT NULL,
   `fxRateToBase`  DECIMAL(10,6)   DEFAULT 1.000000,
   `fifoPnlRealized` DECIMAL(19, 4) DEFAULT 0.00,
   `strategy` varchar(50) DEFAULT NULL,
   `status` varchar(50) DEFAULT NULL,
   `closedBy` varchar(50) DEFAULT NULL, -- z.B. SELL / EXPIRY / ASSIGNMENT
   `tradeID` varchar(20) DEFAULT NULL,
   `ibOrderID` varchar(50) DEFAULT NULL,
   `source` varchar(20) DEFAULT NULL,
   `is_split`  int(11) DEFAULT NULL,
   `split_type` varchar(20) DEFAULT NULL,
   `actionID` varchar(20) DEFAULT NULL,
   `linkID` varchar(50) DEFAULT NULL,
   `opt_strategy`  int(11) DEFAULT NULL,
   `opt_strategyName` varchar(50) DEFAULT NULL,
   `opt_strategyID` varchar(50) DEFAULT NULL,
   `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
   `checksum` varchar(50) DEFAULT NULL,
   `processed`  int(11) DEFAULT 0,

  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
