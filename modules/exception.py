from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from bson import ObjectId
from datetime import datetime
from typing import Tuple, Dict, Any, List

from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES, VALID_EXCEPTION_STATUSES

exception_bp = Blueprint('exception', __name__)

@exception_bp.route('/exception/<image_id>/status', methods=['PUT'])
@jwt_required()
def update_exception_status(image_id: str) -> Tuple[Dict[str, Any], int]:
    """예외 상태 업데이트 API"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        comment = data.get('comment', '')
        
        if not new_status or new_status not in VALID_EXCEPTION_STATUSES:
            return handle_exception(
                Exception("유효하지 않은 예외 상태입니다"),
                error_type="validation_error"
            )
            
        result = db.images.update_one(
            {'_id': ObjectId(image_id)},
            {
                '$set': {
                    'exception_status': new_status,
                    'exception_comment': comment,
                    'exception_updated_at': datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            return handle_exception(
                Exception(MESSAGES['error']['not_found']),
                error_type="validation_error"
            )
            
        return standard_response("예외 상태가 업데이트되었습니다")
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@exception_bp.route('/exception/bulk-update', methods=['POST'])
@jwt_required()
def bulk_update_exception() -> Tuple[Dict[str, Any], int]:
    """예외 상태 일괄 업데이트 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        new_status = data.get('status')
        comment = data.get('comment', '')
        
        if not image_ids or not new_status:
            return handle_exception(
                Exception("이미지 ID와 상태값이 필요합니다"),
                error_type="validation_error"
            )
            
        if new_status not in VALID_EXCEPTION_STATUSES:
            return handle_exception(
                Exception("유효하지 않은 예외 상태입니다"),
                error_type="validation_error"
            )
            
        object_ids = [ObjectId(id) for id in image_ids]
        
        result = db.images.update_many(
            {'_id': {'$in': object_ids}},
            {
                '$set': {
                    'exception_status': new_status,
                    'exception_comment': comment,
                    'exception_updated_at': datetime.utcnow()
                }
            }
        )
        
        return standard_response(
            f"{result.modified_count}개의 이미지가 업데이트되었습니다",
            data={'modified_count': result.modified_count}
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error") 