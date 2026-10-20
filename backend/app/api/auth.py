from flask import current_app, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from backend.app.api import bp
from backend.app import db
from backend.app.models import User
from backend.app.services.bootstrap import validate_password
from backend.app.services.login_throttle import (
    clear_login_failures,
    login_retry_after,
    record_login_failure,
)


def _too_many_attempts(retry_after):
    response = jsonify({"msg": "登录失败次数过多，请稍后再试"})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


@bp.route('/auth/login', methods=['POST'])
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"msg": "Missing JSON in request"}), 400

    username = payload.get('username')
    password = payload.get('password')

    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not username.strip()
        or not password
    ):
        return jsonify({"msg": "Missing username or password"}), 400

    username = username.strip()
    remote_addr = request.remote_addr or "unknown"
    max_attempts = current_app.config.get("LOGIN_MAX_ATTEMPTS", 5)
    window_seconds = current_app.config.get("LOGIN_ATTEMPT_WINDOW_SECONDS", 900)
    lockout_seconds = current_app.config.get("LOGIN_LOCKOUT_SECONDS", 900)

    retry_after = login_retry_after(
        remote_addr,
        username,
        window_seconds=window_seconds,
        lockout_seconds=lockout_seconds,
    )
    if retry_after:
        return _too_many_attempts(retry_after)

    user = User.query.filter_by(username=username).first()

    if user is None or user.is_active is False or not user.check_password(password):
        retry_after = record_login_failure(
            remote_addr,
            username,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            lockout_seconds=lockout_seconds,
        )
        if retry_after:
            return _too_many_attempts(retry_after)
        return jsonify({"msg": "Bad username or password"}), 401

    clear_login_failures(remote_addr, username)

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
