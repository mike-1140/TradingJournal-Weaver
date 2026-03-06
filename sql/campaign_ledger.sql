SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `campaign_ledger`
--
DROP TABLE IF EXISTS `__PREFIX__campaign_ledger`;
CREATE TABLE `__PREFIX__campaign_ledger` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `campaign_id` INT NOT NULL,
    `conid` BIGINT DEFAULT NULL, -- Eindeutige IBKR ID für das Instrument
    `assetCategory` varchar(20) DEFAULT NULL,
    `symbol` varchar(50) DEFAULT NULL, -- Optional, zur schnelleren Anzeige
    `currency` varchar(5) NOT NULL DEFAULT 'USD', -- Währung dieser Zeile

    `source_table` ENUM('TRADES_OPEN', 'TRADES_CLOSE', 'TRADES_RAW', 'VIRTUAL') NOT NULL,
    `source_id` INT NOT NULL,
    `linkID` VARCHAR(50) DEFAULT NULL, -- Zum Gruppieren von FX oder Assignments

    `tradePrice`  DECIMAL(19,4)  DEFAULT NULL, -- Ausführungspreis (Prämie, Aktienkurs)
    `strike`      DECIMAL(19,4)  DEFAULT NULL, -- Nur OPT: Strike-Preis
    `expiry`      DATE           DEFAULT NULL, -- Nur OPT: Verfallsdatum
    `multiplier`  DECIMAL(10,4)  DEFAULT NULL, -- Kontraktgröße (Standard: 100)
    `putCall`     VARCHAR(5)     DEFAULT NULL, -- 'P' oder 'C'
    `buySell`     VARCHAR(10)    DEFAULT NULL, -- 'BUY' oder 'SELL'

    `netcash` DECIMAL(19, 4) DEFAULT 0.0000, -- Tatsächlicher Cash-Fluss inkl. Gebühr
    `proceeds` DECIMAL(19, 4) DEFAULT 0.0000, -- Reiner Erlös
    `commission` DECIMAL(19, 4) DEFAULT 0.0000, -- Separat für Steuer-Reporting
    `fxRateToBase`   DECIMAL(10,6)  DEFAULT 1.000000,
    `netcash_eur`    DECIMAL(19,4)  DEFAULT 0.0000,
    `proceeds_eur`   DECIMAL(19,4)  DEFAULT 0.0000,
    `commission_eur` DECIMAL(19,4)  DEFAULT 0.0000,
    `realized_pnl` DECIMAL(19, 4) DEFAULT 0.0000,

    `inventory_delta` DECIMAL(19, 4) NOT NULL DEFAULT 0.0000, -- Aktien/Optionen Menge
    `action` VARCHAR(50), -- 'BUY', 'SELL', 'ASSIGNMENT', 'EXPIRATION', 'CASH_SETTLEMENT', 'FX_EXCHANGE'

    `dateTime` DATETIME NOT NULL, -- Handelszeitpunkt aus XML
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,

    PRIMARY KEY (`id`),
    FOREIGN KEY (`campaign_id`) REFERENCES `__PREFIX__trading_campaigns`(`id`) ON DELETE CASCADE,
    INDEX (`source_table`),
    INDEX (`source_id`),
    INDEX (`linkID`)
    -- INDEX (`campaign_id`),
    -- INDEX (`conid`),
    -- INDEX (`currency`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
