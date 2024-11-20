from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from .database import find_user
from werkzeug.security import check_password_hash

admin_login_bp = Blueprint('admin_login', __name__)

@admin_login_bp.route('/admin/login', methods=['POST'])
def admin_login():
    # 관리자 로그인
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = find_user(username)
    if user and check_password_hash(user['password'], password) and user['role'] == 'admin':
        token = create_access_token(identity={"username": username, "role": "admin"})
        return jsonify({"message": "Login successful", "token": token}), 200
    else:
        return jsonify({"message": "Invalid credentials or not an admin"}), 401
