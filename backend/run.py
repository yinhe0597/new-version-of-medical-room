import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User, Patient, Drug, Visit, PrescriptionItem, Payment

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Patient': Patient, 'Drug': Drug, 'Visit': Visit, 'PrescriptionItem': PrescriptionItem, 'Payment': Payment}

if __name__ == '__main__':
    import os
    import sys
    import logging
    from werkzeug.security import generate_password_hash
    
    # 强制使用指定的数据库文件
    os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath('E:\\yws2\\medical-room-management-system\\ceshi\\app.db')
    print(f"Using database: {os.environ['SQLALCHEMY_DATABASE_URI']}")
    
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
    
    # 重定向标准输出和标准错误，避免窗口模式下的输出错误
    devnull = open(os.devnull, 'w')
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = devnull
    sys.stderr = devnull
    
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
            
            # 从旧数据库中导入学生信息和药物信息
            old_db_path = r'e:\yws2\medical-room-management-system\ceshi\app.db'
            try:
                import sqlite3
                # 连接到旧数据库
                logging.info(f'Connecting to old database: {old_db_path}')
                conn = sqlite3.connect(old_db_path)
                cursor = conn.cursor()
                
                # 清空现有的患者记录
                logging.info('Clearing existing patient records...')
                db.session.query(Patient).delete()
                db.session.commit()
                
                # 导入学生信息
                logging.info('Importing students from old database...')
                cursor.execute("SELECT student_id, name, gender, grade, college, major, class_name, phone, name_pinyin, name_initials FROM patient")
                patients = cursor.fetchall()
                students = []
                batch_size = 1000
                
                for i, patient in enumerate(patients):
                    student_id, name, gender, grade, college, major, class_name, phone, name_pinyin, name_initials = patient
                    student = Patient(
                        student_id=student_id,
                        name=name,
                        gender=gender,
                        grade=grade,
                        college=college,
                        major=major,
                        class_name=class_name,
                        phone=phone if phone else '',
                        counselor_name='',  # 旧数据库中没有辅导员信息
                        age=0,  # 旧数据库中没有年龄信息
                        name_pinyin=name_pinyin,
                        name_initials=name_initials,
                        is_temporary=False
                    )
                    students.append(student)
                    
                    # 批量提交
                    if len(students) >= batch_size:
                        try:
                            db.session.add_all(students)
                            db.session.commit()
                            students = []
                            logging.info(f"Imported {i+1} students...")
                        except Exception as e:
                            logging.error(f"Error importing students: {e}")
                            db.session.rollback()
                            # 跳过当前批次，继续导入
                            students = []
                
                # 提交剩余的学生信息
                if students:
                    try:
                        db.session.add_all(students)
                        db.session.commit()
                        logging.info(f"Imported {len(students)} more students...")
                    except Exception as e:
                        logging.error(f"Error importing remaining students: {e}")
                        db.session.rollback()
                
                logging.info(f"Successfully imported {len(patients)} students from old database.")
                
                # 清空现有的药物记录
                logging.info('Clearing existing drug records...')
                db.session.query(Drug).delete()
                db.session.commit()
                
                # 导入药物信息
                logging.info("Importing drugs from old database...")
                cursor.execute("SELECT name, specification, unit, price, stock, status, purchase_price, has_scattered, scattered_price, conversion_rate, type, batch_no, inbound_at FROM drug")
                drugs = cursor.fetchall()
                drug_list = []
                
                for i, drug in enumerate(drugs):
                    name, specification, unit, price, stock, status, purchase_price, has_scattered, scattered_price, conversion_rate, type_, batch_no, inbound_at = drug
                    # 只导入Drug模型中存在的字段
                    drug_item = Drug(
                        name=name,
                        specification=specification,
                        unit=unit,
                        price=price,
                        stock=stock,
                        status=status,
                        purchase_price=purchase_price,
                        has_scattered=has_scattered,
                        scattered_price=scattered_price,
                        conversion_rate=conversion_rate,
                        type=type_,
                        batch_no=batch_no,
                        inbound_at=inbound_at
                    )
                    drug_list.append(drug_item)
                    
                    # 批量提交
                    if len(drug_list) >= batch_size:
                        try:
                            db.session.add_all(drug_list)
                            db.session.commit()
                            drug_list = []
                            logging.info(f"Imported {i+1} drugs...")
                        except Exception as e:
                            logging.error(f"Error importing drugs: {e}")
                            db.session.rollback()
                            # 跳过当前批次，继续导入
                            drug_list = []
                
                # 提交剩余的药物信息
                if drug_list:
                    try:
                        db.session.add_all(drug_list)
                        db.session.commit()
                        logging.info(f"Imported {len(drug_list)} more drugs...")
                    except Exception as e:
                        logging.error(f"Error importing remaining drugs: {e}")
                        db.session.rollback()
                
                logging.info(f"Successfully imported {len(drugs)} drugs from old database.")
                
                # 关闭数据库连接
                conn.close()
            except Exception as e:
                logging.error(f"Failed to import data from old database: {e}")
                # 如果旧数据库导入失败，创建示例学生信息
                students = [
                    Patient(student_id='2024001', name='张三', gender='男', grade='2024', college='计算机学院', major='计算机科学与技术', class_name='计算机1班', phone='13800138000', counselor_name='王老师', age=18),
                    Patient(student_id='2024002', name='李四', gender='女', grade='2024', college='英语学院', major='英语', class_name='英语2班', phone='13912345678', counselor_name='刘老师', age=19),
                    Patient(student_id='2024003', name='王五', gender='男', grade='2024', college='数学学院', major='数学', class_name='数学1班', phone='13787654321', counselor_name='张老师', age=18),
                    Patient(student_id='2024004', name='赵六', gender='女', grade='2024', college='物理学院', major='物理学', class_name='物理1班', phone='13654321098', counselor_name='陈老师', age=19),
                    Patient(student_id='2024005', name='孙七', gender='男', grade='2024', college='化学学院', major='化学', class_name='化学1班', phone='13543210987', counselor_name='周老师', age=18),
                    Patient(student_id='2024006', name='周八', gender='女', grade='2024', college='生物学院', major='生物学', class_name='生物1班', phone='13432109876', counselor_name='吴老师', age=19),
                    Patient(student_id='2024007', name='吴九', gender='男', grade='2024', college='历史学院', major='历史学', class_name='历史1班', phone='13321098765', counselor_name='郑老师', age=18),
                    Patient(student_id='2024008', name='郑十', gender='女', grade='2024', college='文学院', major='汉语言文学', class_name='文学1班', phone='13210987654', counselor_name='王老师', age=19),
                    Patient(student_id='2024009', name='王十一', gender='男', grade='2024', college='经济学院', major='经济学', class_name='经济1班', phone='13109876543', counselor_name='李老师', age=18),
                    Patient(student_id='2024010', name='李十二', gender='女', grade='2024', college='管理学院', major='管理学', class_name='管理1班', phone='13098765432', counselor_name='张老师', age=19),
                ]
                db.session.add_all(students)
                logging.info("Created sample students.")
            
            db.session.commit()
            logging.info('Database initialization completed.')
        
        logging.info('Starting Flask application...')
        app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)
    except Exception as e:
        logging.error(f"Error starting application: {e}")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        devnull.close()
        logging.info('Application stopped.')
