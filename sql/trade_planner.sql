DROP TABLE IF EXISTS `__PREFIX__trade_planner`;

CREATE TABLE `__PREFIX__trade_planner` (
  `id`            int(11) NOT NULL AUTO_INCREMENT,
  `environment`   ENUM('MONEY','PAPER','TEST','AUTOM_MONEY','AUTOM_PAPER') NOT NULL,
  `underlying`    varchar(20) NOT NULL,
  `date_open`     date NOT NULL,
  `price_open`    decimal(10,2) DEFAULT NULL,
  `ivp_open`      tinyint(3) DEFAULT NULL,
  `ivr_open`      tinyint(3) DEFAULT NULL,
  `strategy`      varchar(50) DEFAULT NULL,
  `exit_plan`     text DEFAULT NULL,
  `status`        ENUM('open','closed') NOT NULL DEFAULT 'open',
  `date_close`    date DEFAULT NULL,
  `price_close`   decimal(10,2) DEFAULT NULL,
  `ivp_close`     tinyint(3) DEFAULT NULL,
  `ivr_close`     tinyint(3) DEFAULT NULL,
  `premium_close` decimal(10,2) DEFAULT NULL,
  `fees_close`    decimal(10,2) DEFAULT NULL,
  `realized_pnl`  decimal(10,2) DEFAULT NULL,
  `actual_dte`    smallint(5) DEFAULT NULL,
  `notes`         text DEFAULT NULL,
  `created_at`    timestamp NULL DEFAULT NULL,
  `updated_at`    timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_environment` (`environment`),
  INDEX `idx_status` (`status`),
  INDEX `idx_underlying_date` (`underlying`, `date_open`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
