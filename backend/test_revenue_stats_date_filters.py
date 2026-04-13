from datetime import datetime

from backend.app import create_app, db
from backend.app.models import Patient, Payment, User, Visit


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


def _create_user(username: str, role: str) -> User:
    user = User(username=username, real_name=username, role=role)
    user.set_password("123456")
    db.session.add(user)
    db.session.flush()
    return user


def _create_payment(nurse_id: int, doctor_id: int, paid_at: datetime, amount: float) -> Payment:
    patient = Patient(student_id=f"s{paid_at.timestamp()}-{amount}", name="p")
    db.session.add(patient)
    db.session.flush()

    visit = Visit(
        patient_id=patient.id,
        doctor_id=doctor_id,
        consultation_fee=0.0,
        total_amount=amount,
        status="completed",
    )
    db.session.add(visit)
    db.session.flush()

    payment = Payment(
        visit_id=visit.id,
        nurse_id=nurse_id,
        amount=amount,
        payment_method="cash",
        payment_date=paid_at,
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def run_tests():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()

        admin = _create_user("admin", "admin")
        nurse = _create_user("nurse", "nurse")
        doctor = _create_user("doctor", "doctor")

        seed = [
            (datetime(2026, 1, 14, 23, 59, 59), 1.0),
            (datetime(2026, 1, 15, 0, 0, 0), 2.0),
            (datetime(2026, 1, 15, 23, 59, 59), 3.0),
            (datetime(2026, 1, 16, 0, 0, 0), 5.0),
            (datetime(2026, 2, 1, 0, 0, 0), 7.0),
        ]
        for paid_at, amount in seed:
            _create_payment(nurse.id, doctor.id, paid_at, amount)
        db.session.commit()

        client = app.test_client()
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "123456"})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        token = resp.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "daily", "date": "2026-01-15"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["total_revenue"] == 5.0
        assert data["total_profit"] == 5.0
        assert len(data["details"]) == 2

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "monthly", "date": "2026-01"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["total_revenue"] == 11.0
        assert data["total_profit"] == 11.0
        assert len(data["details"]) == 4

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "monthly", "date": "2026-01-15"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["total_revenue"] == 11.0
        assert len(data["details"]) == 4

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "yearly", "date": "2026"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["total_revenue"] == 18.0
        assert data["total_profit"] == 18.0
        assert len(data["details"]) == 5

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "daily", "date": "2026-01"},
            headers=headers,
        )
        assert resp.status_code == 400

        resp = client.get(
            "/api/admin/statistics/revenue",
            query_string={"type": "monthly", "date": "2026"},
            headers=headers,
        )
        assert resp.status_code == 400

    print("OK")


if __name__ == "__main__":
    run_tests()

