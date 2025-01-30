from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from .database import db

status_bp = Blueprint('status', __name__)

@status_bp.route('/images/status', methods=['GET'])
@jwt_required()
def get_image_status():
    """이미지 현황 조회 API"""
    try:
        total_images = db.images.count_documents({})
        unclassified_images = db.images.count_documents({'is_classified': False})
        classified_images = db.images.count_documents({'is_classified': True})

        return jsonify({
            "status": 200,
            "summary": {
                "totalImages": total_images,
                "unclassifiedImages": unclassified_images,
                "classifiedImages": classified_images
            }
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500 