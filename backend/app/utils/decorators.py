from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.app import db
from backend.app.models import User

def role_required(roles):
    if not isinstance(roles, list):
        roles = [roles]

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            try:
                user = db.session.get(User, int(user_id))
            except (ValueError, TypeError):
                return jsonify(msg="Invalid user identity"), 401

            if not user or user.is_active is False:
                return jsonify(msg="Account is disabled"), 403

            if user.role not in roles:
                return jsonify(msg="Access denied: insufficient permissions"), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
