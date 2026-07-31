"""手工验收：患者多路检索（学号/拼音首字母/姓名，本地 app，无需启动服务）。

临时测试用户口令来自 MEDICAL_CHECK_PASSWORD，未设置时随机生成。
"""

from _common import check_password, ensure_repo_root_on_path

ensure_repo_root_on_path()

from flask_jwt_extended import create_access_token
from backend.app import create_app, db
from backend.app.models import User, Patient


def get_doctor_token(app):
    with app.app_context():
        user = User.query.filter_by(role="doctor").first()
        if not user:
            user = User(username="test_doctor2", role="doctor")
            user.set_password(check_password())
            db.session.add(user)
            db.session.commit()
        return create_access_token(identity=str(user.id))


def main():
    app = create_app()
    app.testing = True
    client = app.test_client()

    with app.app_context():
        p = Patient.query.filter_by(student_id="2023123456").first()
        if not p:
            p = Patient(
                student_id="2023123456",
                name="张三",
                name_pinyin="zhangsan",
                name_initials="zs",
                gender="男",
                grade="2023",
                college="测试学院",
                major="测试专业",
                class_name="测试班级",
                phone="13800000000",
            )
            db.session.add(p)
            db.session.commit()

    token = get_doctor_token(app)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/doctor/patient/search", headers=headers, query_string={"student_id": "234"})
    assert res.status_code == 200, res.data
    data = res.get_json()["data"]
    assert any(x["student_id"] == "2023123456" for x in data)

    res = client.get("/api/doctor/patient/search", headers=headers, query_string={"student_id": "zs"})
    assert res.status_code == 200, res.data
    data = res.get_json()["data"]
    assert any(x["student_id"] == "2023123456" for x in data)

    res = client.get("/api/doctor/patient/search", headers=headers, query_string={"student_id": "张三"})
    assert res.status_code == 200, res.data
    data = res.get_json()["data"]
    assert any(x["student_id"] == "2023123456" for x in data)

    print("OK")


if __name__ == "__main__":
    main()
