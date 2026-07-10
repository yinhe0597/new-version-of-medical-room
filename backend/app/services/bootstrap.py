import os
import secrets

from werkzeug.security import generate_password_hash

from backend.app import db
from backend.app.models import User


BOOTSTRAP_USERS = (
    ("admin", "admin", "管理员"),
    ("doctor", "doctor", "张医生"),
    ("nurse", "nurse", "李护士"),
)


def validate_password(password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return password


def add_missing_bootstrap_users():
    """Stage missing built-in accounts and return (usernames, password)."""
    missing = []
    weak_existing = []
    for username, role, real_name in BOOTSTRAP_USERS:
        user = User.query.filter_by(username=username).first()
        if user is None:
            missing.append((username, role, real_name))
        elif user.password_hash and user.check_password("123456"):
            weak_existing.append(user)

    if not missing and not weak_existing:
        return [], None

    configured_password = os.environ.get("BOOTSTRAP_PASSWORD")
    if configured_password is not None:
        try:
            validate_password(configured_password)
        except ValueError as exc:
            raise RuntimeError("BOOTSTRAP_PASSWORD must contain at least 12 characters") from exc
    password = configured_password or secrets.token_urlsafe(12)

    for username, role, real_name in missing:
        db.session.add(User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            real_name=real_name,
        ))
    for user in weak_existing:
        user.set_password(password)

    affected = [username for username, _, _ in missing]
    affected.extend(user.username for user in weak_existing)
    return affected, password
