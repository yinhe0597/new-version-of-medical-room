import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app, db
from backend.app.models import User
from backend.app.services.bootstrap import validate_password

def reset_passwords(app, new_password=None):
    new_password = new_password or os.environ.get('RESET_PASSWORD')
    try:
        validate_password(new_password)
    except ValueError:
        raise RuntimeError('Set RESET_PASSWORD to a password containing at least 12 characters')
    with app.app_context():
        usernames = ['admin', 'doctor', 'nurse']
        users = User.query.filter(User.username.in_(usernames)).all()
        for user in users:
            user.set_password(new_password)
            db.session.add(user)
        db.session.commit()
        print(f"Reset passwords for: {', '.join([u.username for u in users])}")

if __name__ == '__main__':
    app = create_app()
    reset_passwords(app)
