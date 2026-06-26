SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `psychology_rulesets`
--
DROP TABLE IF EXISTS `__PREFIX__psychology_rulesets`;
CREATE TABLE `__PREFIX__psychology_rulesets` (
    `id`            int(11)      NOT NULL AUTO_INCREMENT,
    `name`          VARCHAR(100) NOT NULL,
    `strategy_type` VARCHAR(50)  DEFAULT NULL,
    `description`   VARCHAR(500) DEFAULT NULL,
    `is_active`     TINYINT(1)   DEFAULT 1,
    `sort_order`    SMALLINT     DEFAULT 0,
    `environment`   ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
    `created_at`    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    `updated_at`    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    INDEX (`environment`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
