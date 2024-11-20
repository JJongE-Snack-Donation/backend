from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

def role_required(required_role):
    # 특정 역할만 접근 가능하도록 제한
    # 추후 어드민 관리페이지 추가 시 사용
    def decorator(func):
        def wrapper(*args, **kwargs):
            # JWT 인증 확인
            verify_jwt_in_request()
            claims = get_jwt()
            # 역할(role) 확인
            if claims.get('role') != required_role:
                return jsonify({"message": "Access forbidden: insufficient privileges"}), 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator
