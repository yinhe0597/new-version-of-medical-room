"""
医务室管理系统 - 生产部署入口
PyInstaller 打包时以此文件为入口点

稳定性增强 (open0.0.7):
  1. 使用 waitress 替代 Flask 开发服务器（生产级 WSGI）
  2. 禁用 Windows Console QuickEdit 模式防止进程冻结
  3. 全局异常兜底 + 崩溃自动重启
  4. 结构化日志增强（带日志轮转）
"""
import os
import sys
import socket
import logging
import logging.handlers
import threading
import traceback
import time as time_module
import ctypes
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
# 2.1 禁用 Windows Console QuickEdit 模式
#     QuickEdit 模式下用户点击控制台窗口会冻结进程，是生产环境
#     "系统自动退出" 最常见的原因
# ---------------------------------------------------------------------------
def disable_quickedit():
    """禁用 Windows 控制台的 QuickEdit 模式，防止点击冻结进程"""
    if sys.platform != 'win32':
        return
    try:
        kernel32 = ctypes.windll.kernel32
        # STD_INPUT_HANDLE = -10
        handle = kernel32.GetStdHandle(ctypes.c_ulong(-10 & 0xFFFFFFFF))
        if handle == -1:
            return
        # 获取当前控制台模式
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        # ENABLE_QUICK_EDIT_MODE = 0x0040, ENABLE_INSERT_MODE = 0x0020
        # 关闭 QuickEdit 和 Insert 模式
        new_mode = mode.value & ~0x0040 & ~0x0020
        # ENABLE_EXTENDED_FLAGS = 0x0080 (必须设置才能修改 QuickEdit)
        new_mode |= 0x0080
        kernel32.SetConsoleMode(handle, ctypes.c_ulong(new_mode))
    except Exception:
        pass  # 非 Windows 或权限不足时静默跳过

disable_quickedit()

# ---------------------------------------------------------------------------
# 3. 设置数据库路径（相对于 exe 所在目录）
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(DATA_DIR, 'app.db')
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(DB_PATH)

# ---------------------------------------------------------------------------
# 4. 配置日志（带日志轮转，防止日志文件无限增长）
# ---------------------------------------------------------------------------
log_file = os.path.join(LOGS_DIR, 'app.log')

# 日志轮转：单文件最大 5MB，保留最近 5 个备份
file_handler = logging.handlers.RotatingFileHandler(
    log_file, encoding='utf-8', maxBytes=5*1024*1024, backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
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


def start_server():
    """启动服务器（可被外层重启循环调用）"""
    PORT = 5000

    logging.info(f'APP_ROOT: {APP_ROOT}')
    logging.info(f'Database: {DB_PATH}')

    # 创建 Flask 应用（此时会初始化数据库表、检查并兼容旧表结构）
    logging.info('Creating Flask application...')
    app = create_app()
    logging.info('Flask application created successfully.')

    # 注册全局异常处理器，防止未捕获异常导致 500 空响应
    @app.errorhandler(Exception)
    def handle_all_exceptions(e):
        logging.error(f'Unhandled exception: {type(e).__name__}: {e}', exc_info=True)
        return {'msg': '服务器内部错误，请稍后重试', 'error': str(e)}, 500

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
    print('    医务室诊疗管理系统 open0.0.7')
    print('=' * 60)
    print(f'  本机访问:   http://127.0.0.1:{PORT}')
    print(f'  局域网访问: http://{local_ip}:{PORT}')
    print(f'  数据库位置: {os.path.abspath(DB_PATH)}')
    print('=' * 60)
    print('  ⚠ 请勿点击本窗口内部（会导致系统暂停）')
    print('  ⚠ 关闭本窗口将停止系统运行')
    print('=' * 60)
    print('')

    # 使用 waitress 生产级 WSGI 服务器替代 Flask 开发服务器
    # waitress 特性：多线程、稳定、不会因单个请求异常而崩溃
    try:
        from waitress import serve
        logging.info(f'Starting waitress server on 0.0.0.0:{PORT}')
        serve(app, host='0.0.0.0', port=PORT, threads=4,
              channel_timeout=120, recv_bytes=65536,
              url_scheme='http')
    except ImportError:
        # waitress 未安装时回退到 Flask 开发服务器
        logging.warning('waitress not installed, falling back to Flask dev server (NOT recommended for production)')
        logging.info(f'Starting Flask dev server on 0.0.0.0:{PORT}')
        app.run(debug=False, host='0.0.0.0', port=PORT, use_reloader=False)


if __name__ == '__main__':
    MAX_RESTART_ATTEMPTS = 5
    RESTART_COOLDOWN = 3  # 重启间隔（秒）
    restart_count = 0

    while restart_count < MAX_RESTART_ATTEMPTS:
        try:
            start_server()
            # 正常退出（如 Ctrl+C）
            logging.info('Server stopped normally.')
            break
        except KeyboardInterrupt:
            logging.info('Server stopped by user (Ctrl+C).')
            break
        except SystemExit:
            logging.info('Server received SystemExit.')
            break
        except Exception as e:
            restart_count += 1
            logging.error(f'Server crashed (attempt {restart_count}/{MAX_RESTART_ATTEMPTS}): {e}')
            logging.error(traceback.format_exc())
            if restart_count < MAX_RESTART_ATTEMPTS:
                logging.info(f'Auto-restarting in {RESTART_COOLDOWN} seconds...')
                time_module.sleep(RESTART_COOLDOWN)
            else:
                logging.error('Max restart attempts reached. Server will not restart.')
                print(f"\n服务器多次崩溃，已停止自动重启。请检查 logs/app.log 获取详情。", file=sys.stderr)
                input("按 Enter 键退出...")

    logging.info('Application exited.')
