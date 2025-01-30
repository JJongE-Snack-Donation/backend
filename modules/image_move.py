from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from .database import db

image_move_bp = Blueprint('image_move', __name__)

@image_move_bp.route('/images/<image_id>/move', methods=['POST'])
@jwt_required()
def move_image(image_id):
    """이미지 이동 API"""
    try:
        data = request.get_json()
        target_category = data.get('targetCategory')
        
        if target_category not in ['classified', 'unclassified']:
            return jsonify({
                "status": 400,
                "message": "유효하지 않은 카테고리"
            }), 400

        is_classified = target_category == 'classified'
        
        result = db.images.update_one(
            {'_id': ObjectId(image_id)},
            {'$set': {'is_classified': is_classified}}
        )

        if result.modified_count == 0:
            return jsonify({
                "status": 404,
                "message": "이미지를 찾을 수 없음"
            }), 404

        return jsonify({
            "status": 200,
            "message": "이미지 이동 성공",
            "newCategory": target_category
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500 