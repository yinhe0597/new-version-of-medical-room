from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.app.api import bp
from backend.app.models import User
from backend.app.utils.decorators import role_required

@bp.route('/')
def index():
    return "Hello, World!"

@bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    return jsonify(logged_in_as=user.username), 200

@bp.route('/admin-only', methods=['GET'])
@jwt_required()
@role_required(['admin'])
def admin_only():
    return jsonify(msg="Welcome admin!"), 200

@bp.route('/doctor-only', methods=['GET'])
@jwt_required()
@role_required(['doctor', 'admin'])
def doctor_only():
    return jsonify(msg="Welcome doctor!"), 200
