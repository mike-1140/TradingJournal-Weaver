DROP TABLE IF EXISTS `__PREFIX__trade_planner_legs`;

CREATE TABLE `__PREFIX__trade_planner_legs` (
  `id`           int(11) NOT NULL AUTO_INCREMENT,
  `plan_id`      int(11) NOT NULL,
  `leg_type`     varchar(10) NOT NULL,
  `dte`          smallint(5) DEFAULT NULL,
  `strike`       decimal(10,2) DEFAULT NULL,
  `delta`        decimal(6,2) DEFAULT NULL,
  `premium`      decimal(10,2) DEFAULT NULL,
  `fees`         decimal(10,2) DEFAULT NULL,
  `max_risk`     decimal(10,2) DEFAULT NULL,
  `sort_order`   tinyint(3) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  INDEX `idx_plan_id` (`plan_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
