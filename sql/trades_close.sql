
SET AUTOCOMMIT=0;

--
-- Datenbank: `trading-journal`
--
--
-- Tabellenstruktur für Tabelle `trades_close`
--
DROP TABLE IF EXISTS `__PREFIX__trades_close`;
CREATE TABLE `__PREFIX__trades_close` (
   `id` int(11) NOT NULL AUTO_INCREMENT,
   `symID` int(11) DEFAULT NULL,
   `conid` varchar(20) DEFAULT NULL,           -- IBKR Contract ID
   `assetCategory` varchar(20) DEFAULT NULL,
   `subCategory` varchar(20) DEFAULT NULL,
   `symbol` varchar(50) DEFAULT NULL,
   `description` varchar(250) DEFAULT NULL,
   `underlyingSymbol` varchar(20) DEFAULT NULL,
   `underlyingConid` varchar(20) DEFAULT NULL,
   `multiplier` DECIMAL(19, 4) DEFAULT 1.00,               -- Wichtig für P&L Berechnung
   `strike` DECIMAL(19, 4) DEFAULT 0.00,                -- Fehlt für Optionen
   `expiry` dateTime DEFAULT NULL,                 -- Fehlt für Optionen
   `dateTimeOpen` datetime DEFAULT NULL,
   `dateTimeClose` datetime DEFAULT NULL,
   `putCall` varchar(20) DEFAULT NULL,
   `buySellOpen` varchar(20) DEFAULT NULL,
   `buySellClose` varchar(20) DEFAULT NULL,
   `quantity` DECIMAL(19, 4) DEFAULT 0.00,
   `tradePriceOpen` DECIMAL(19, 4) DEFAULT 0.00,
   `tradePriceClose` DECIMAL(19, 4) DEFAULT 0.00,
   `netCashOpen` DECIMAL(19, 4) DEFAULT 0.00,
   `netCashClose` DECIMAL(19, 4) DEFAULT 0.00,
   `proceedsOpen` DECIMAL(19, 4) DEFAULT 0.00,
   `proceedsClose` DECIMAL(19, 4) DEFAULT 0.00,
   `daysHeld` int(11) DEFAULT NULL,
   `totalSeconds` BIGINT DEFAULT NULL,
   `durationStr`  varchar(30) DEFAULT NULL,
   `profit` DECIMAL(19, 4) DEFAULT 0.00,
   `ROI` DECIMAL(19, 4) DEFAULT 0.00,
   `tradeIDOpen` varchar(70) DEFAULT NULL,
   `tradeIDClose` varchar(70) DEFAULT NULL,
   `ibOrderIDOpen` varchar(50) DEFAULT NULL,
   `ibOrderIDClose` varchar(50) DEFAULT NULL,
   `ibCommission` DECIMAL(19, 4) DEFAULT 0.00,
   `currency`           varchar(5)     DEFAULT NULL,
   `fxRateToBase_open`  DECIMAL(10,6)  DEFAULT 1.000000,
   `fxRateToBase_close` DECIMAL(10,6)  DEFAULT 1.000000,
   `netCashOpen_EUR`    DECIMAL(19,4)  DEFAULT 0.00,
   `netCashClose_EUR`   DECIMAL(19,4)  DEFAULT 0.00,
   `ibCommission_EUR`   DECIMAL(19,4)  DEFAULT 0.00,
   `profit_EUR`         DECIMAL(19,4)  DEFAULT 0.00,
   `closedBy` varchar(50) DEFAULT NULL, -- z.B. SELL / EXPIRY / ASSIGNMENT
   `strategy` varchar(50) DEFAULT NULL,
   `status` varchar(50) DEFAULT NULL,          -- Assigned, Expired, Closed
   `opt_strategy`  int(11) DEFAULT NULL,
   `opt_strategyName` varchar(50) DEFAULT NULL,
   `opt_strategyID` varchar(50) DEFAULT NULL,
   `linkID` varchar(50) DEFAULT NULL,
   `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,

   PRIMARY KEY (`id`),
   INDEX (`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
