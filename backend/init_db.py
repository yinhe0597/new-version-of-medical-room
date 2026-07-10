import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import Drug, Patient
from backend.app.services.bootstrap import add_missing_bootstrap_users
import sqlalchemy
import re

def create_database_if_not_exists(app_or_uri):
    uri = (
        app_or_uri.config['SQLALCHEMY_DATABASE_URI']
        if hasattr(app_or_uri, 'config')
        else str(app_or_uri)
    )
    if uri.startswith('mysql'):
        url = sqlalchemy.engine.make_url(uri)
        db_name = url.database
        if not db_name or not re.fullmatch(r'[A-Za-z0-9_]+', db_name):
            raise RuntimeError('MySQL database name may only contain letters, numbers, and underscores')
        engine = sqlalchemy.create_engine(url.set(database=None))
        try:
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                conn.execute(sqlalchemy.text(f"ALTER DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                print(f"Ensured database '{db_name}' exists.")
        except Exception as e:
            print(f"Failed to create database '{db_name}': {e}")
            raise
        finally:
            engine.dispose()

def init_db(app):
    create_database_if_not_exists(app)
    with app.app_context():
        db.create_all()
        created_users, bootstrap_password = add_missing_bootstrap_users()

        # Create Drugs
        if Drug.query.count() == 0:
            drugs = [
                Drug(name='感冒灵颗粒', specification='10g×9袋', unit='盒', price=12.50, stock=100, status=1),
                Drug(name='布洛芬片', specification='0.2g×20片', unit='盒', price=15.00, stock=50, status=1),
                Drug(name='阿莫西林胶囊', specification='0.25g×20粒', unit='盒', price=18.00, stock=80, status=1),
                Drug(name='板蓝根颗粒', specification='10g×20袋', unit='包', price=22.50, stock=200, status=1),
                Drug(name='碘伏消毒液', specification='100ml', unit='瓶', price=5.00, stock=30, status=1),
            ]
            db.session.add_all(drugs)
            print("Created sample drugs.")

        # Create Patients
        if Patient.query.count() == 0:
            patients = [
                Patient(student_id='2024001', name='张三', gender='男', class_name='计算机1班', phone='13800138000'),
                Patient(student_id='2024002', name='李四', gender='女', class_name='英语2班', phone='13912345678'),
            ]
            db.session.add_all(patients)
            print("Created sample patients.")

        db.session.commit()
        print("Database initialized successfully.")
        if created_users:
            print(f"Created bootstrap users: {', '.join(created_users)}")
            print(f"First-run temporary password: {bootstrap_password}")

if __name__ == '__main__':
    from backend.config import Config

    create_database_if_not_exists(Config.SQLALCHEMY_DATABASE_URI)
    app = create_app()
    init_db(app)
