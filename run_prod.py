"""
医务室管理系统 - 生产部署入口
PyInstaller 打包时以此文件为入口点
"""
import os
import sys
import socket
import logging

# ---------------------------------------------------------------------------
# 1. 计算 APP_ROOT（exe 所在目录 or 项目根目录）
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后: exe 所在目录
    APP_ROOT = os.path.dirname(sys.executable)
else:
    # 开发环境: 本文件所在目录（项目根）
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# 将 APP_ROOT 写入环境变量，供 config.py 等模块读取
os.environ['APP_ROOT'] = APP_ROOT

# ---------------------------------------------------------------------------
# 2. 确保 sys.path 包含项目根目录（开发环境 & 打包环境）
# ---------------------------------------------------------------------------
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# ---------------------------------------------------------------------------
# 3. 自动创建必要的目录
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(APP_ROOT, 'data')
LOGS_DIR = os.path.join(APP_ROOT, 'logs')
BACKUPS_DIR = os.path.join(DATA_DIR, 'backups')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(BACKUPS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 4. 设置数据库路径（相对于 exe 所在目录）
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(DATA_DIR, 'app.db')
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(DB_PATH)

# ---------------------------------------------------------------------------
# 5. 配置日志
# ---------------------------------------------------------------------------
log_file = os.path.join(LOGS_DIR, 'app.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ---------------------------------------------------------------------------
# 6. 获取本机局域网 IP
# ---------------------------------------------------------------------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

# ---------------------------------------------------------------------------
# 7. 导入并启动 Flask 应用
# ---------------------------------------------------------------------------
from backend.app import create_app, db
from backend.app.models import User

app = create_app()

PORT = 5000

if __name__ == '__main__':
    from werkzeug.security import generate_password_hash

    try:
        logging.info(f'APP_ROOT: {APP_ROOT}')
        logging.info(f'Database: {DB_PATH}')

        # 初始化数据库
        with app.app_context():
            logging.info('Creating database tables...')
            db.create_all()

            # 创建默认用户（仅在不存在时）
            if not User.query.filter_by(username='admin').first():
                db.session.add(User(username='admin', password_hash=generate_password_hash('123456'), role='admin', real_name='管理员'))
                logging.info('Created admin user')
            if not User.query.filter_by(username='doctor').first():
                db.session.add(User(username='doctor', password_hash=generate_password_hash('123456'), role='doctor', real_name='张医生'))
                logging.info('Created doctor user')
            if not User.query.filter_by(username='nurse').first():
                db.session.add(User(username='nurse', password_hash=generate_password_hash('123456'), role='nurse', real_name='李护士'))
                logging.info('Created nurse user')
            db.session.commit()
            logging.info('Database initialization completed.')

        local_ip = get_local_ip()

        print('')
        print('=' * 60)
        print('    医务室诊疗管理系统 v26.04.29.10.25')
        print('=' * 60)
        print(f'  本机访问:   http://127.0.0.1:{PORT}')
        print(f'  局域网访问: http://{local_ip}:{PORT}')
        print(f'  数据库位置: {os.path.abspath(DB_PATH)}')
        print('=' * 60)
        print('  提示: 关闭此窗口将停止系统运行')
        print('=' * 60)
        print('')

        logging.info(f'Starting server on 0.0.0.0:{PORT}')
        app.run(debug=False, host='0.0.0.0', port=PORT, use_reloader=False)

    except Exception as e:
        logging.error(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
    finally:
        logging.info('Application stopped.')
