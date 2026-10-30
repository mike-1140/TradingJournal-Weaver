SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `__PREFIX__trade_planner`;

CREATE TABLE `__PREFIX__trade_planner` (
  `id`            int(11) NOT NULL AUTO_INCREMENT,
  `environment`   ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
  `campaign_id`   int(11) DEFAULT NULL, -- Verknüpfung zur echten Kampagne (trading_campaigns), nullable da nicht jeder Eintrag verknüpft ist
  `opened_at`     datetime DEFAULT NULL, -- Eröffnung innerhalb der Kampagne, zu der dieser Eintrag gehört (Zahlen kommen aus dem Ledger)
  `underlying`    varchar(20) NOT NULL,
  `date_open`     date NOT NULL,
  `price_open`    decimal(10,2) DEFAULT NULL,
  `fees_open`     decimal(10,2) DEFAULT NULL,
  `ivp_open`      tinyint(3) DEFAULT NULL,
  `ivr_open`      tinyint(3) DEFAULT NULL,
  `strategy`      varchar(50) DEFAULT NULL,
  `exit_plan`     text DEFAULT NULL,
  `mindset_entry` varchar(30)                                     DEFAULT NULL,
  `energy_level`  ENUM('fit','müde','gestresst','krank')          DEFAULT NULL,
  `rationale`     text                                            DEFAULT NULL,
  `confidence`    tinyint(2)                                      DEFAULT NULL,
  `market_regime` ENUM('bullish','bearish','seitwärts','volatil') DEFAULT NULL,
  `pre_mortem`    varchar(200)                                    DEFAULT NULL,
  `status`        ENUM('open','closed') NOT NULL DEFAULT 'open',
  `date_close`    date DEFAULT NULL,
  `price_close`   decimal(10,2) DEFAULT NULL,
  `ivp_close`     tinyint(3) DEFAULT NULL,
  `ivr_close`     tinyint(3) DEFAULT NULL,
  `premium_close` decimal(10,2) DEFAULT NULL,
  `fees_close`    decimal(10,2) DEFAULT NULL,
  `realized_pnl`  decimal(10,2) DEFAULT NULL,
  `actual_dte`    smallint(5) DEFAULT NULL,
  `mindset_exit`    varchar(30) DEFAULT NULL,
  `plan_adherence`  ENUM('yes','partial','no') DEFAULT NULL,
  `lessons_learned`  text DEFAULT NULL,
  `decision_quality` ENUM('gut','mittel','schlecht') DEFAULT NULL,
  `notes`            text DEFAULT NULL,
  `created_at`    timestamp NULL DEFAULT NULL,
  `updated_at`    timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  FOREIGN KEY (`campaign_id`) REFERENCES `__PREFIX__trading_campaigns`(`id`) ON DELETE SET NULL,
  INDEX `idx_environment` (`environment`),
  INDEX `idx_status` (`status`),
  INDEX `idx_underlying_date` (`underlying`, `date_open`),
  INDEX `idx_campaign_id` (`campaign_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
