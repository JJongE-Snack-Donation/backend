from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from bson import ObjectId
from typing import Tuple, Dict, Any, List

from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES

favorite_bp = Blueprint('favorite', __name__)

@favorite_bp.route('/favorite/<image_id>', methods=['POST'])
@jwt_required()
def toggle_favorite(image_id: str) -> Tuple[Dict[str, Any], int]:
    """즐겨찾기 토글 API"""
    try:
        # ObjectId 변환 및 이미지 존재 확인
        object_id = ObjectId(image_id)
        image = db.images.find_one({'_id': object_id})
        
        if not image:
            return handle_exception(
                Exception(MESSAGES['error']['not_found']),
                error_type="validation_error"
            )
            
        # 현재 상태의 반대로 토글
        new_status = not image.get('is_favorite', False)
        
        # 업데이트
        result = db.images.update_one(
            {'_id': object_id},
            {'$set': {'is_favorite': new_status}}
        )
        
        if result.modified_count == 0:
            return handle_exception(
                Exception(MESSAGES['error']['update_failed']),
                error_type="db_error"
            )
            
        return standard_response(
            "즐겨찾기 상태가 변경되었습니다",
            data={'is_favorite': new_status}
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@favorite_bp.route('/favorite/bulk', methods=['POST'])
@jwt_required()
def bulk_update_favorites() -> Tuple[Dict[str, Any], int]:
    """즐겨찾기 일괄 업데이트 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        is_favorite = data.get('is_favorite', False)
        
        if not image_ids:
            return handle_exception(
                Exception(MESSAGES['error']['invalid_request']),
                error_type="validation_error"
            )
            
        # ObjectId 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 일괄 업데이트
        result = db.images.update_many(
            {'_id': {'$in': object_ids}},
            {'$set': {'is_favorite': is_favorite}}
        )
        
        return standard_response(
            f"{result.modified_count}개의 이미지가 업데이트되었습니다",
            data={
                'modified_count': result.modified_count,
                'is_favorite': is_favorite
            }
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error") 