import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 在创建app之前就设置环境变量，指定数据库文件
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath('E:\\yws2\\medical-room-management-system\\ceshi\\app.db')
print(f"Using database: {os.environ['SQLALCHEMY_DATABASE_URI']}")

from backend.app import create_app, db
from backend.app.models import User, Patient, Drug, Visit, PrescriptionItem, Payment

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Patient': Patient, 'Drug': Drug, 'Visit': Visit, 'PrescriptionItem': PrescriptionItem, 'Payment': Payment}

if __name__ == '__main__':
    import logging
    from werkzeug.security import generate_password_hash
    
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
            # 创建默认用户
            logging.info('Creating default users...')
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(username='admin', password_hash=generate_password_hash('123456'), role='admin', real_name='管理员')
                db.session.add(admin)
                logging.info('Created admin user')
            
            doctor = User.query.filter_by(username='doctor').first()
            if not doctor:
                doctor = User(username='doctor', password_hash=generate_password_hash('123456'), role='doctor', real_name='张医生')
                db.session.add(doctor)
                logging.info('Created doctor user')
            
            nurse = User.query.filter_by(username='nurse').first()
            if not nurse:
                nurse = User(username='nurse', password_hash=generate_password_hash('123456'), role='nurse', real_name='李护士')
                db.session.add(nurse)
                logging.info('Created nurse user')
            
            db.session.commit()
            logging.info('Database initialization completed.')
        
        logging.info('Starting Flask application...')
        app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)
    except Exception as e:
        logging.error(f"Error starting application: {e}")
    finally:
        logging.info('Application stopped.')
