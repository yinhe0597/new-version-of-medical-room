-- MySQL/MariaDB 数据库字符集修复脚本（可重复执行）
-- 目的：把数据库默认字符集、所有表（以及其字符列）统一到 utf8mb4，避免写入中文变成 ????
--
-- 使用方式：
-- 1) 打开 MySQL/MariaDB 控制台 (例如: mysql -u root -p)
-- 2) 执行：USE `medical_db`; 然后复制粘贴执行本文件全部内容
--    或：source /path/to/repair_mysql_charset.sql
--
-- 注意：
-- - 会对表做 CONVERT，执行时会锁表；建议在业务低峰执行
-- - 已经写入成 ???? 的历史数据无法从数据库侧自动恢复

SET NAMES utf8mb4;
SET @db := DATABASE();

SET FOREIGN_KEY_CHECKS = 0;

SET @sql_db := CONCAT('ALTER DATABASE `', @db, '` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
PREPARE stmt_db FROM @sql_db;
EXECUTE stmt_db;
DEALLOCATE PREPARE stmt_db;

SET SESSION group_concat_max_len = 1024 * 1024;
SELECT
  IFNULL(
    GROUP_CONCAT(
      CONCAT('ALTER TABLE `', table_schema, '`.`', table_name, '` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
      SEPARATOR '; '
    ),
    'SELECT 1'
  )
INTO @sql_tables
FROM information_schema.tables
WHERE table_schema = @db
  AND table_type = 'BASE TABLE';

PREPARE stmt_tables FROM @sql_tables;
EXECUTE stmt_tables;
DEALLOCATE PREPARE stmt_tables;

SET FOREIGN_KEY_CHECKS = 1;
