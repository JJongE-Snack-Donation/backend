from flask import Blueprint, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from werkzeug.security import check_password_hash
from typing import Tuple, Dict, Any
import time
from flask_jwt_extended import decode_token
from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES, JWT_ACCESS_TOKEN_EXPIRES

admin_login_bp = Blueprint('admin_login', __name__)

@admin_login_bp.route('/login', methods=['POST'])
def admin_login() -> Tuple[Dict[str, Any], int]:
    """관리자 로그인 API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return handle_exception(
                Exception(MESSAGES['error']['invalid_credentials']),
                error_type="validation_error"
            )
            
        admin = db.users.find_one({'username': username})
        if not admin or not check_password_hash(admin['password'], password):
            return handle_exception(
                Exception(MESSAGES['error']['invalid_credentials']),
                error_type="auth_error"
            )
            
        access_token = create_access_token(
            identity=username,
            expires_delta=timedelta(seconds=JWT_ACCESS_TOKEN_EXPIRES)
        )
        
        return standard_response(
            MESSAGES['success']['login'],
            data={
                'access_token': access_token,
                'admin': {
                    'username': admin['username'],
                    'email': admin['email'],
                    'role': 'admin'
                }
            }
        )
        
    except Exception as e:
        return handle_exception(e, error_type="auth_error")

@admin_login_bp.route('/logout', methods=['POST'])
@jwt_required()
def admin_logout():
    try:

        # 로그아웃 성공 시 응답
        return standard_response(
            message="로그아웃 성공",  # 직접 메시지 지정
            status=200
        )
        
    except Exception as e:
        print(f"로그아웃 에러: {str(e)}")
        return handle_exception(e, error_type="auth_error")

@admin_login_bp.route('/check-auth', methods=['GET'])
@jwt_required()
def check_auth():
    """현재 로그인 상태 확인용 엔드포인트"""
    try:
        current_user = get_jwt_identity()

        if not current_user:
            return handle_exception(
                Exception("유효하지 않은 토큰입니다."),
                error_type="auth_error"
            )

        return standard_response(
            "인증 확인 성공",
            data={
                "user": current_user,
                "authenticated": True
            }
        )

    except Exception as e:
        # 명시적으로 예외를 처리하고 적절한 에러 메시지를 반환
        return handle_exception(
            e if str(e) else Exception("인증 확인 중 알 수 없는 오류가 발생했습니다."),
            error_type="auth_error"
        )
