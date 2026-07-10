import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault('APP_ROOT', ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User, Patient, Drug, Visit, PrescriptionItem, Payment
from sqlalchemy.engine import make_url

app = create_app()
print(f"Using database: {make_url(app.config['SQLALCHEMY_DATABASE_URI']).render_as_string(hide_password=True)}")

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Patient': Patient, 'Drug': Drug, 'Visit': Visit, 'PrescriptionItem': PrescriptionItem, 'Payment': Payment}

if __name__ == '__main__':
    import logging
    from backend.app.services.bootstrap import add_missing_bootstrap_users
    
    # 配置日志
    log_file = os.path.join(os.path.dirname(__file__), 'app.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    try:
        logging.info('Starting application...')
        # 初始化数据库，确保默认用户存在
        with app.app_context():
            logging.info('Creating database tables...')
            db.create_all()
            logging.info('Ensuring bootstrap users exist...')
            created_users, bootstrap_password = add_missing_bootstrap_users()
            db.session.commit()
            if created_users:
                logging.warning('Created bootstrap users: %s', ', '.join(created_users))
                print(f'首次启动临时密码: {bootstrap_password}')
            logging.info('Database initialization completed.')
        
        logging.info('Starting Flask application...')
        debug_enabled = os.environ.get('FLASK_DEBUG') == '1'
        bind_host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
        if debug_enabled and bind_host not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('FLASK_DEBUG may only be used with a loopback FLASK_RUN_HOST')
        app.run(debug=debug_enabled, host=bind_host, port=5000, use_reloader=False)
    except Exception as e:
        logging.error(f"Error starting application: {e}")
    finally:
        logging.info('Application stopped.')
