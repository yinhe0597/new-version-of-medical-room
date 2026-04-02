import sys
from datetime import datetime

sys.path.append(r"e:\yws")

from flask_jwt_extended import create_access_token
from backend.app import create_app, db
from backend.app.models import User, Drug


def get_token(app, role):
    with app.app_context():
        user = User.query.filter_by(role=role).first()
        if not user:
            user = User(username=f"test_{role}", role=role)
            user.set_password("123456")
            db.session.add(user)
            db.session.commit()
        return create_access_token(identity=str(user.id))


def main():
    app = create_app()
    app.testing = True
    client = app.test_client()

    with app.app_context():
        d = Drug.query.filter_by(name="测试药品A", specification="10mg*10片").first()
        if not d:
            d = Drug(
                name="测试药品A",
                type=1,
                specification="10mg*10片",
                unit="盒",
                price=10.0,
                stock=0,
                status=1,
                purchase_price=8.0,
                has_scattered=True,
                scattered_price=1.0,
                conversion_rate=10,
                batch_no="BATCH-TEST",
                inbound_at=datetime(2026, 3, 1, 10, 30),
            )
            db.session.add(d)
            db.session.commit()

    nurse_token = get_token(app, "nurse")
    doctor_token = get_token(app, "doctor")

    res = client.get(
        "/api/nurse/drugs",
        headers={"Authorization": f"Bearer {nurse_token}"},
        query_string={"name": "测试药品A", "pack": "scattered"},
    )
    assert res.status_code == 200, res.data
    payload = res.get_json()
    assert payload["data"], payload
    assert payload["data"][0]["has_scattered"] is True

    res = client.get(
        "/api/doctor/drugs/search",
        headers={"Authorization": f"Bearer {doctor_token}"},
        query_string={"keyword": "测试药品A"},
    )
    assert res.status_code == 200, res.data
    payload = res.get_json()
    assert payload["data"], payload
    assert payload["data"][0]["name"] == "测试药品A"

    print("OK")


if __name__ == "__main__":
    main()

