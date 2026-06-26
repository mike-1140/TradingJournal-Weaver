SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `psychology_entries`
--
DROP TABLE IF EXISTS `__PREFIX__psychology_entries`;
CREATE TABLE `__PREFIX__psychology_entries` (
    `id`              int(11)       NOT NULL AUTO_INCREMENT,
    `trade_id`        VARCHAR(70)   DEFAULT NULL,
    `opt_strategyID`  VARCHAR(50)   DEFAULT NULL,
    `trade_type`      ENUM('closed','spread') DEFAULT NULL,
    `ruleset_id`      int(11)       DEFAULT NULL,
    `symbol`          VARCHAR(100)  NOT NULL,
    `trade_date`      DATE          NOT NULL,
    `pnl`             DECIMAL(10,2) DEFAULT NULL,
    `emotion_pre`     TINYINT UNSIGNED DEFAULT NULL,
    `emotion_post`    TINYINT UNSIGNED DEFAULT NULL,
    `motivation`      ENUM('SYSTEM','FOMO','REVENGE','BOREDOM','IMPULSE') DEFAULT NULL,
    `market_context`  ENUM('trending','choppy','high_iv','low_iv','news') DEFAULT NULL,
    `lesson`          TEXT          DEFAULT NULL,
    `environment`     ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
    `created_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    INDEX (`environment`, `trade_date`),
    INDEX (`symbol`),
    INDEX (`motivation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
