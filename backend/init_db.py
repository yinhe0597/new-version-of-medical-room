import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User, Drug, Patient
from werkzeug.security import generate_password_hash
import sqlalchemy

def _mysql_no_db_uri(uri: str) -> str:
    base, sep, query = uri.partition("?")
    prefix = base.rsplit("/", 1)[0] + "/"
    if sep and query:
        return prefix + "?" + query
    return prefix

def create_database_if_not_exists(app):
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('mysql'):
        base = uri.split("?", 1)[0]
        db_name = base.rsplit("/", 1)[1]
        engine = sqlalchemy.create_engine(_mysql_no_db_uri(uri))
        try:
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                conn.execute(sqlalchemy.text(f"ALTER DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                print(f"Ensured database '{db_name}' exists.")
        except Exception as e:
            print(f"Failed to create database '{db_name}': {e}")

def init_db(app):
    create_database_if_not_exists(app)
    with app.app_context():
        db.create_all()
        # Create Users
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', password_hash=generate_password_hash('123456'), role='admin', real_name='管理员')
            db.session.add(admin)
            print("Created admin user.")

        doctor = User.query.filter_by(username='doctor').first()
        if not doctor:
            doctor = User(username='doctor', password_hash=generate_password_hash('123456'), role='doctor', real_name='张医生')
            db.session.add(doctor)
            print("Created doctor user.")

        nurse = User.query.filter_by(username='nurse').first()
        if not nurse:
            nurse = User(username='nurse', password_hash=generate_password_hash('123456'), role='nurse', real_name='李护士')
            db.session.add(nurse)
            print("Created nurse user.")

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

if __name__ == '__main__':
    app = create_app()
    init_db(app)
