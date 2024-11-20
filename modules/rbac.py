from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from .database import find_user

def role_required(required_role):
    # 특정 역할만 접근 가능하도록 제한
    def decorator(func):
        def wrapper(*args, **kwargs):
            # JWT 인증 확인
            verify_jwt_in_request()
            username = get_jwt_identity()  # JWT에서 username만 가져옴

            # 데이터베이스에서 역할 확인
            user = find_user(username)
            if not user or user['role'] != required_role:
                return jsonify({"message": "Access forbidden: insufficient privileges"}), 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator
