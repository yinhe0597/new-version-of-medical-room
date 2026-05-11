"""
医务室管理系统 - 生产部署入口
PyInstaller 打包时以此文件为入口点
"""
import os
import sys
import socket
import logging
import threading
import traceback
import time as time_module
from datetime import datetime as dt_now, date as date_type, time as time_type

# ---------------------------------------------------------------------------
# 1. 计算 APP_ROOT（exe 所在目录 or 项目根目录）
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

os.environ['APP_ROOT'] = APP_ROOT

if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# ---------------------------------------------------------------------------
# 2. 自动创建必要的目录
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(APP_ROOT, 'data')
LOGS_DIR = os.path.join(APP_ROOT, 'logs')
BACKUPS_DIR = os.path.join(DATA_DIR, 'backups')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(BACKUPS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 3. 设置数据库路径（相对于 exe 所在目录）
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(DATA_DIR, 'app.db')
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(DB_PATH)

# ---------------------------------------------------------------------------
# 4. 配置日志（需在其他日志输出前完成）
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
# 5. 获取本机局域网 IP
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
# 6. 导入 Flask 工厂（仅导入函数，不创建 app）
# ---------------------------------------------------------------------------
from backend.app import create_app, db


def take_daily_snapshot(flask_app):
    """保存所有活跃药品的当日库存快照"""
    with flask_app.app_context():
        from backend.app.models import DailyStockSnapshot, Drug
        from datetime import date
        today = date.today()

        existing = db.session.query(DailyStockSnapshot).filter_by(date=today).first()
        if existing:
            logging.info(f'Daily snapshot for {today} already exists, skipping.')
            return

        drugs = Drug.query.filter(Drug.status == 1).all()
        count = 0
        for drug in drugs:
            snapshot = DailyStockSnapshot(
                drug_id=drug.id,
                date=today,
                stock=drug.stock
            )
            db.session.add(snapshot)
            count += 1

        db.session.commit()
        logging.info(f'Daily snapshot saved: {count} drugs for {today}')


def snapshot_scheduler(flask_app):
    """后台线程：每天0点执行快照"""
    while True:
        now = dt_now.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now.hour >= 0 and now.minute >= 0:
            from datetime import timedelta
            tomorrow = tomorrow + timedelta(days=1)
        seconds_until_midnight = (tomorrow - now).total_seconds()

        logging.info(f'Snapshot scheduler: next snapshot in {seconds_until_midnight:.0f} seconds')
        time_module.sleep(seconds_until_midnight)

        try:
            take_daily_snapshot(flask_app)
        except Exception as e:
            logging.error(f'Snapshot error: {e}')


if __name__ == '__main__':
    PORT = 5000

    try:
        logging.info(f'APP_ROOT: {APP_ROOT}')
        logging.info(f'Database: {DB_PATH}')

        # 创建 Flask 应用（此时会初始化数据库表、检查并兼容旧表结构）
        logging.info('Creating Flask application...')
        app = create_app()
        logging.info('Flask application created successfully.')

        # 初始化默认用户
        from backend.app.models import User
        from werkzeug.security import generate_password_hash

        with app.app_context():
            logging.info('Ensuring default users exist...')
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
            logging.info('Default user initialization completed.')

        # 启动时补建今天的库存快照（如果不存在）
        take_daily_snapshot(app)

        # 启动后台快照调度线程
        snapshot_thread = threading.Thread(target=snapshot_scheduler, args=(app,), daemon=True)
        snapshot_thread.start()
        logging.info('Daily snapshot scheduler started.')

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
        traceback.print_exc()
        print(f"\n启动失败: {e}", file=sys.stderr)
        input("按 Enter 键退出...")
    finally:
        logging.info('Application stopped.')
