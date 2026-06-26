SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `psychology_rules`
--
DROP TABLE IF EXISTS `__PREFIX__psychology_rules`;
CREATE TABLE `__PREFIX__psychology_rules` (
    `id`          int(11)      NOT NULL AUTO_INCREMENT,
    `ruleset_id`  int(11)      NOT NULL,
    `rule_key`    VARCHAR(50)  NOT NULL,
    `label`       VARCHAR(200) NOT NULL,
    `description` VARCHAR(500) DEFAULT NULL,
    `error_type`  ENUM('greed','fear','hope','impulse','discipline') DEFAULT NULL,
    `sort_order`  SMALLINT     DEFAULT 0,

    PRIMARY KEY (`id`),
    INDEX (`ruleset_id`),
    FOREIGN KEY (`ruleset_id`) REFERENCES `__PREFIX__psychology_rulesets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
