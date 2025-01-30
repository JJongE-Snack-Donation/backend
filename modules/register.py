from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from .database import create_user, find_user

register_bp = Blueprint('register', __name__)

@register_bp.route('/register', methods=['POST'])
def register():
    # 회원가입
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if find_user(username):
        return jsonify({"message": "User already exists"}), 400

    hashed_password = generate_password_hash(password)
    create_user(username, hashed_password, role='user')
    return jsonify({"message": "회원가입 완료"}), 201
