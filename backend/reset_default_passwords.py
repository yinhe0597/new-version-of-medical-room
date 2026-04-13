import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User
from werkzeug.security import generate_password_hash

def reset_passwords(app, default_password='123456'):
    with app.app_context():
        usernames = ['admin', 'doctor', 'nurse']
        users = User.query.filter(User.username.in_(usernames)).all()
        for user in users:
            user.password_hash = generate_password_hash(default_password)
            db.session.add(user)
        db.session.commit()
        print(f"Reset passwords for: {', '.join([u.username for u in users])}")

if __name__ == '__main__':
    app = create_app()
    reset_passwords(app)
