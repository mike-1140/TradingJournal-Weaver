SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `trading_campaigns`
--
DROP TABLE IF EXISTS `__PREFIX__trading_campaigns`;
CREATE TABLE `__PREFIX__trading_campaigns` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(50) NOT NULL,
    `symbol` VARCHAR(20) NOT NULL,
    `strategy` VARCHAR(50) DEFAULT 'STANDARD',
    `assetCategory` VARCHAR(10),
    `status` ENUM('ACTIVE', 'PENDING', 'CLOSED') DEFAULT 'ACTIVE',
    `start_date` DATETIME NOT NULL,
    `end_date` DATETIME,
    `closed_at` DATETIME NULL,
    `environment` ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,

    PRIMARY KEY (`id`),
    INDEX (`symbol`),
    INDEX (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
