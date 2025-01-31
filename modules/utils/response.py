from typing import Dict, Any, Optional, Union
from flask import jsonify

def standard_response(
    message: str, 
    data: Optional[Dict[str, Any]] = None, 
    meta: Optional[Dict[str, Any]] = None,
    status: int = 200
) -> tuple[Dict[str, Any], int]:
    """표준 응답 형식"""
    response = {
        "message": message,
        "status": status
    }
    if data is not None:
        response["data"] = data
    if meta is not None:
        response["meta"] = meta
    return jsonify(response), status

def handle_exception(
    e: Exception, 
    error_type: str = "general_error"
) -> tuple[Dict[str, Any], int]:
    """예외 처리 함수
    
    error_types:
    - auth_error: 인증/인가 관련 오류
    - validation_error: 데이터 유효성 검사 오류
    - db_error: 데이터베이스 관련 오류
    - file_error: 파일 처리 관련 오류
    - general_error: 기타 일반 오류
    """
    error_status = {
        "auth_error": 401,
        "validation_error": 400,
        "db_error": 500,
        "file_error": 500,
        "general_error": 500
    }
    
    return standard_response(
        str(e),
        status=error_status.get(error_type, 500)
    )

def pagination_meta(
    total: int, 
    page: int, 
    per_page: int
) -> Dict[str, Any]:
    """페이지네이션 메타데이터"""
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    } 