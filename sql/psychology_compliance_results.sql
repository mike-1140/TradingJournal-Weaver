SET AUTOCOMMIT=0;
SET FOREIGN_KEY_CHECKS = 0;
--
-- Tabellenstruktur für Tabelle `psychology_compliance_results`
--
DROP TABLE IF EXISTS `__PREFIX__psychology_compliance_results`;
CREATE TABLE `__PREFIX__psychology_compliance_results` (
    `id`       int(11)    NOT NULL AUTO_INCREMENT,
    `entry_id` int(11)    NOT NULL,
    `rule_id`  int(11)    NOT NULL,
    `complied` TINYINT(1) DEFAULT 0,
    `tempted`  TINYINT(1) DEFAULT 0,

    PRIMARY KEY (`id`),
    UNIQUE KEY `entry_rule` (`entry_id`, `rule_id`),
    FOREIGN KEY (`entry_id`) REFERENCES `__PREFIX__psychology_entries` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`rule_id`)  REFERENCES `__PREFIX__psychology_rules`  (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
