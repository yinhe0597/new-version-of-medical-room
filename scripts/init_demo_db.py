"""
初始化空白演示数据库 — 创建 data/app.db 并填充演示数据
用法: python scripts/init_demo_db.py
输出: data/app.db（包含表结构和演示数据）
"""
import os
import sys

# 将项目根目录加入 sys.path
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

os.environ['APP_ROOT'] = APP_ROOT
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(APP_ROOT, 'data', 'app.db')

from backend.app import create_app, db
from backend.app.models import User, Drug, DiagnosisDict, Patient
from backend.app.services.bootstrap import add_missing_bootstrap_users

app = create_app()

DEMO_DRUGS = [
    # 常用药品
    {'name': '布洛芬缓释胶囊', 'type': 1, 'specification': '0.3g*20粒', 'unit': '盒', 'price': 15.0, 'stock': 50, 'purchase_price': 8.0},
    {'name': '阿莫西林胶囊', 'type': 1, 'specification': '0.25g*24粒', 'unit': '盒', 'price': 8.5, 'stock': 40, 'purchase_price': 4.0},
    {'name': '头孢克肟分散片', 'type': 1, 'specification': '50mg*6片', 'unit': '盒', 'price': 18.0, 'stock': 30, 'purchase_price': 10.0},
    {'name': '感冒灵颗粒', 'type': 1, 'specification': '10g*9袋', 'unit': '盒', 'price': 12.0, 'stock': 60, 'purchase_price': 6.5},
    {'name': '板蓝根颗粒', 'type': 1, 'specification': '10g*20袋', 'unit': '袋', 'price': 3.5, 'stock': 100, 'purchase_price': 1.5},
    {'name': '氯雷他定片', 'type': 1, 'specification': '10mg*6片', 'unit': '盒', 'price': 12.0, 'stock': 25, 'purchase_price': 6.0},
    {'name': '蒙脱石散', 'type': 1, 'specification': '3g*10袋', 'unit': '盒', 'price': 15.0, 'stock': 20, 'purchase_price': 8.0},
    {'name': '创可贴', 'type': 1, 'specification': '100片/盒', 'unit': '片', 'price': 0.5, 'stock': 500, 'purchase_price': 0.2},
    {'name': '碘伏消毒液', 'type': 1, 'specification': '100ml', 'unit': '瓶', 'price': 8.0, 'stock': 15, 'purchase_price': 4.0},
    {'name': '医用纱布卷', 'type': 1, 'specification': '8*600cm', 'unit': '卷', 'price': 5.0, 'stock': 20, 'purchase_price': 2.5},
    {'name': '云南白药气雾剂', 'type': 1, 'specification': '85g', 'unit': '瓶', 'price': 35.0, 'stock': 10, 'purchase_price': 22.0},
    {'name': '维生素C片', 'type': 1, 'specification': '100mg*100片', 'unit': '瓶', 'price': 6.0, 'stock': 30, 'purchase_price': 3.0},
    {'name': '电子体温计', 'type': 2, 'specification': '医用级', 'unit': '支', 'price': 25.0, 'stock': 5, 'purchase_price': 15.0},
    # 诊疗服务项目
    {'name': '普通诊疗费', 'type': 2, 'specification': '次', 'unit': '次', 'price': 10.0, 'stock': 99999, 'purchase_price': 0.0},
    {'name': '肌肉注射费', 'type': 2, 'specification': '次', 'unit': '次', 'price': 5.0, 'stock': 99999, 'purchase_price': 0.0},
    {'name': '静脉输液费', 'type': 2, 'specification': '次', 'unit': '次', 'price': 15.0, 'stock': 99999, 'purchase_price': 0.0},
    {'name': '伤口清创缝合', 'type': 2, 'specification': '次', 'unit': '次', 'price': 30.0, 'stock': 99999, 'purchase_price': 0.0},
    {'name': '换药费', 'type': 2, 'specification': '次', 'unit': '次', 'price': 8.0, 'stock': 99999, 'purchase_price': 0.0},
    {'name': '雾化吸入治疗', 'type': 2, 'specification': '次', 'unit': '次', 'price': 12.0, 'stock': 99999, 'purchase_price': 0.0},
    # 耗材
    {'name': '一次性手套', 'type': 3, 'specification': '100只/盒', 'unit': '只', 'price': 0.5, 'stock': 200, 'purchase_price': 0.2, 'variant_type': 'consumable'},
    {'name': '医用棉签', 'type': 3, 'specification': '50支/包', 'unit': '支', 'price': 0.1, 'stock': 500, 'purchase_price': 0.03, 'variant_type': 'consumable'},
    {'name': '输液贴', 'type': 3, 'specification': '100片/盒', 'unit': '片', 'price': 0.3, 'stock': 300, 'purchase_price': 0.1, 'variant_type': 'consumable'},
    {'name': '一次性注射器(5ml)', 'type': 3, 'specification': '5ml', 'unit': '支', 'price': 1.5, 'stock': 100, 'purchase_price': 0.8, 'variant_type': 'consumable'},
]

DEMO_DIAGNOSES = [
    {'code': 'J00', 'name': '急性鼻咽炎[普通感冒]', 'pinyin': 'jixingbiyan'},
    {'code': 'J02', 'name': '急性咽炎', 'pinyin': 'jixingyanyan'},
    {'code': 'J06', 'name': '急性上呼吸道感染', 'pinyin': 'jixingshanghuxidaoganran'},
    {'code': 'J20', 'name': '急性支气管炎', 'pinyin': 'jixingzhiqiguanyan'},
    {'code': 'K29', 'name': '胃炎', 'pinyin': 'weiyan'},
    {'code': 'K52', 'name': '急性胃肠炎', 'pinyin': 'jixingweichangyan'},
    {'code': 'R50', 'name': '发热', 'pinyin': 'fare'},
    {'code': 'R51', 'name': '头痛', 'pinyin': 'toutong'},
    {'code': 'R52', 'name': '腹痛', 'pinyin': 'futong'},
    {'code': 'T14', 'name': '软组织损伤', 'pinyin': 'ruanzuzhisunshang'},
    {'code': 'L01', 'name': '皮肤感染', 'pinyin': 'pifuganran'},
    {'code': 'H10', 'name': '结膜炎', 'pinyin': 'jiemoyan'},
    {'code': 'S60', 'name': '手指挫伤', 'pinyin': 'shouzhichuoshang'},
    {'code': 'M54', 'name': '腰痛', 'pinyin': 'yaotong'},
    {'code': 'T78', 'name': '过敏性反应', 'pinyin': 'guominxingfanying'},
]

DEMO_PATIENTS = [
    {'student_id': '2024001', 'name': '张三', 'gender': '男', 'class_name': '计算机科学1班', 'grade': '2024级', 'college': '信息学院', 'major': '计算机科学与技术'},
    {'student_id': '2024002', 'name': '李四', 'gender': '女', 'class_name': '软件工程2班', 'grade': '2024级', 'college': '信息学院', 'major': '软件工程'},
    {'student_id': '2024003', 'name': '王五', 'gender': '男', 'class_name': '数学与应用数学1班', 'grade': '2023级', 'college': '理学院', 'major': '数学与应用数学'},
    {'student_id': '2024004', 'name': '赵六', 'gender': '女', 'class_name': '英语1班', 'grade': '2023级', 'college': '外国语学院', 'major': '英语'},
    {'student_id': '2024005', 'name': '陈七', 'gender': '男', 'class_name': '体育教育1班', 'grade': '2022级', 'college': '体育学院', 'major': '体育教育'},
]


def init_demo_db():
    with app.app_context():
        print('Creating database tables...')
        db.create_all()

        created_users, bootstrap_password = add_missing_bootstrap_users()
        db.session.commit()

        # 添加演示药品
        drug_count = Drug.query.count()
        if drug_count == 0:
            for d in DEMO_DRUGS:
                drug = Drug(**d)
                db.session.add(drug)
            db.session.commit()
            print(f'  Added {len(DEMO_DRUGS)} demo drugs/service items.')
        else:
            print(f'  Drugs already exist ({drug_count}), skipping.')

        # 添加诊断词库
        diag_count = DiagnosisDict.query.count()
        if diag_count == 0:
            for d in DEMO_DIAGNOSES:
                diag = DiagnosisDict(**d)
                db.session.add(diag)
            db.session.commit()
            print(f'  Added {len(DEMO_DIAGNOSES)} diagnosis dictionary entries.')
        else:
            print(f'  Diagnoses already exist ({diag_count}), skipping.')

        # 添加演示患者
        patient_count = Patient.query.count()
        if patient_count == 0:
            for p in DEMO_PATIENTS:
                patient = Patient(**p)
                # 自动生成拼音
                try:
                    from pypinyin import lazy_pinyin, Style
                    py = ''.join(lazy_pinyin(p['name'], style=Style.TONE3))
                    initials = ''.join(lazy_pinyin(p['name'], style=Style.FIRST_LETTER))
                    patient.name_pinyin = py
                    patient.name_initials = initials
                except ImportError:
                    pass
                db.session.add(patient)
            db.session.commit()
            print(f'  Added {len(DEMO_PATIENTS)} demo patients.')
        else:
            print(f'  Patients already exist ({patient_count}), skipping.')

        print()
        print('=' * 50)
        print('  Demo database initialized successfully!')
        print(f'  Database: {os.path.join(APP_ROOT, "data", "app.db")}')
        print('=' * 50)
        print()
        print('  Bootstrap accounts: admin, doctor, nurse')
        if created_users:
            print(f'  First-run temporary password: {bootstrap_password}')
        else:
            print('  Existing account passwords were not changed.')
        print()
        print('  提示: 将这个 data/app.db 复制到部署目录即可使用')


if __name__ == '__main__':
    init_demo_db()
