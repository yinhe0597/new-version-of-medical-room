-- 医务室管理系统部署前置数据库脚本
-- 运行方式：
-- 1. 打开 MySQL/MariaDB 控制台 (例如: mysql -u root -p)
-- 2. 复制粘贴并执行以下全部代码，或者执行 `source /path/to/init_database.sql`

-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS `medical_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. 创建医务室专用账号
-- 注意：如果是在 MySQL 8.0 及以上，默认密码策略可能要求密码满足复杂性要求
-- 这里的密码 "xibokeladi" 需符合服务器的密码策略
CREATE USER IF NOT EXISTS 'yiwushi'@'localhost' IDENTIFIED BY 'xibokeladi';
CREATE USER IF NOT EXISTS 'yiwushi'@'%' IDENTIFIED BY 'xibokeladi';

-- 修改密码以防用户已存在但密码不对
ALTER USER 'yiwushi'@'localhost' IDENTIFIED BY 'xibokeladi';
ALTER USER 'yiwushi'@'%' IDENTIFIED BY 'xibokeladi';

-- 3. 赋予权限
GRANT ALL PRIVILEGES ON `medical_db`.* TO 'yiwushi'@'localhost';
GRANT ALL PRIVILEGES ON `medical_db`.* TO 'yiwushi'@'%';

-- 4. 刷新权限
FLUSH PRIVILEGES;

-- 提示：执行完成后，后端程序将使用 yiwushi / xibokeladi 连接到 3306 端口上的 medical_db
