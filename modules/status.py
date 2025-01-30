from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from .database import db

status_bp = Blueprint('status', __name__)

@status_bp.route('/status/summary', methods=['GET'])
@jwt_required()
def get_image_status():
    """
    이미지 현황 조회 API
    Returns:
        - totalImages: 전체 이미지 수
        - unclassifiedImages: 미분류 이미지 수
        - classifiedImages: 분류된 이미지 수
    """
    try:
        # 전체 이미지 수
        total_images = db.images.count_documents({})
        
        # 미분류 이미지 수
        unclassified_images = db.images.count_documents({'is_classified': False})
        
        # 분류된 이미지 수
        classified_images = db.images.count_documents({'is_classified': True})
        
        return jsonify({
            'status': 200,
            'summary': {
                'totalImages': total_images,
                'unclassifiedImages': unclassified_images,
                'classifiedImages': classified_images
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 500,
            'error': f'Failed to fetch image status: {str(e)}'
        }), 500 