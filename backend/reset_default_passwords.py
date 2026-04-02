from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

def reset_passwords(default_password='123456'):
    with app.app_context():
        usernames = ['admin', 'doctor', 'nurse']
        users = User.query.filter(User.username.in_(usernames)).all()
        for user in users:
            user.password_hash = generate_password_hash(default_password)
            db.session.add(user)
        db.session.commit()
        print(f"Reset passwords for: {', '.join([u.username for u in users])}")

if __name__ == '__main__':
    reset_passwords()
