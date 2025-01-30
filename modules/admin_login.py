from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from flasgger.utils import swag_from
from .database import find_user
from werkzeug.security import check_password_hash

admin_login_bp = Blueprint('admin_login', __name__)

@admin_login_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """관리자 로그인 API"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        user = find_user(username)
        if user and check_password_hash(user['password'], password) and user['role'] == 'admin':
            token = create_access_token(
                identity=username,
                expires_delta=timedelta(minutes=60)
            )
            return jsonify({
                "status": 200,
                "result": {
                    "token": token
                }
            }), 200
        else:
            return jsonify({
                "status": 401,
                "message": "로그인 실패"
            }), 401
            
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@admin_login_bp.route('/admin/logout', methods=['POST'])
@jwt_required()
def admin_logout():
    """관리자 로그아웃 API"""
    try:
        return jsonify({
            "status": 200,
            "message": "로그아웃 성공"
        }), 200
    except Exception as e:
        return jsonify({
            "status": 401,
            "message": "인증 실패"
        }), 401

@admin_login_bp.route('/admin/check-auth', methods=['GET'])
@jwt_required()
def check_auth():
    """
    현재 로그인 상태 확인용 엔드포인트
    """
    current_user = get_jwt_identity()
    return jsonify({
        "message": "Token is valid",
        "user": current_user,
        "authenticated": True
    }), 200