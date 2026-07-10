-- 医务室管理系统部署前置数据库脚本
-- 运行方式：
-- 1. 打开 MySQL/MariaDB 控制台 (例如: mysql -u root -p)
-- 2. 复制粘贴并执行以下全部代码，或者执行 `source /path/to/init_database.sql`

-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS `medical_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER DATABASE `medical_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. 使用部署环境自己的高强度密码创建最小权限账号。
-- 不在仓库中保存共享密码。以下语句仅为示例，请先替换 <STRONG_PASSWORD> 后手工执行：
-- CREATE USER 'yiwushi'@'localhost' IDENTIFIED BY '<STRONG_PASSWORD>';
-- GRANT ALL PRIVILEGES ON `medical_db`.* TO 'yiwushi'@'localhost';
-- FLUSH PRIVILEGES;

-- 3. 通过环境变量配置连接串，例如：
-- DATABASE_URL=mysql+pymysql://yiwushi:<URL_ENCODED_PASSWORD>@127.0.0.1:3306/medical_db?charset=utf8mb4
