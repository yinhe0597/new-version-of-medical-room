from flask import request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from backend.app.api import bp
from backend.app import db
from backend.app.models import User
from backend.app.services.bootstrap import validate_password

@bp.route('/auth/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"}), 400

    username = request.json.get('username', None)
    password = request.json.get('password', None)

    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    user = User.query.filter_by(username=username).first()

    if user is None or user.is_active is False or not user.check_password(password):
        return jsonify({"msg": "Bad username or password"}), 401

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"ver": int(user.token_version or 0)},
    )
    return jsonify({
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "role": user.role,
            "is_active": user.is_active is not False,
        }
    }), 200


@bp.route('/auth/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """修改当前登录用户的密码"""
    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({"msg": "请提供原密码和新密码"}), 400

    try:
        validate_password(new_password)
    except ValueError:
        return jsonify({"msg": "新密码长度不能少于12位"}), 400

    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id))
    if not user:
        return jsonify({"msg": "用户不存在"}), 404

    if not user.check_password(old_password):
        return jsonify({"msg": "原密码错误"}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"msg": "密码修改成功"}), 200
