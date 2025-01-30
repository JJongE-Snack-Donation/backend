from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from .database import db
from datetime import datetime

inspection_bp = Blueprint('inspection', __name__)

@inspection_bp.route('/inspection/<image_id>', methods=['GET'])
@jwt_required()
def get_image_for_inspection(image_id):
    """분류된 이미지 검토를 위한 상세 정보 조회"""
    try:
        # ObjectId 변환
        object_id = ObjectId(image_id)
        
        # 이미지 조회
        image = db.images.find_one({'_id': object_id, 'is_classified': True})
        if not image:
            return jsonify({'message': 'Classified image not found'}), 404
            
        # 검토용 응답 데이터
        response_data = {
            'ImageDatas': {
                '_id': str(image['_id']),
                'FileName': image.get('FileName'),
                'FilePath': image.get('FilePath'),
                'ThumnailPath': image.get('ThumnailPath'),
                'SerialNumber': image.get('SerialNumber'),
                'UserLabel': image.get('UserLabel'),
                'DateTimeOriginal': image.get('DateTimeOriginal'),
                'ProjectInfo': image.get('ProjectInfo'),
                'AnalysisFolder': image.get('AnalysisFolder')
            },
            # TODO: 딥러닝 분석 결과 (추후 구현)
            # 'Infos': image.get('Infos', []),
            # 'Count': image.get('Count'),
            # 'BestClass': image.get('BestClass')
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({'message': 'Failed to get image', 'error': str(e)}), 400

@inspection_bp.route('/inspection/<image_id>/confirm', methods=['POST'])
@jwt_required()
def confirm_classification(image_id):
    """이미지 분류 결과 확정"""
    try:
        # ObjectId 변환
        object_id = ObjectId(image_id)
        
        # 요청 데이터 확인
        data = request.get_json()
        is_approved = data.get('is_approved')
        
        if is_approved is None:
            return jsonify({'message': 'Approval status is required'}), 400
            
        # 이미지 존재 확인
        image = db.images.find_one({'_id': object_id, 'is_classified': True})
        if not image:
            return jsonify({'message': 'Classified image not found'}), 404
            
        # 승인 상태 업데이트
        update_data = {
            'inspection_status': 'approved' if is_approved else 'rejected',
            'inspection_date': datetime.utcnow()
        }
        
        update_result = db.images.update_one(
            {'_id': object_id},
            {'$set': update_data}
        )
        
        if update_result.modified_count == 0:
            return jsonify({'message': 'No changes made'}), 200
            
        return jsonify({
            'message': 'Classification inspection completed',
            'status': 'approved' if is_approved else 'rejected'
        }), 200
        
    except Exception as e:
        return jsonify({'message': 'Confirmation failed', 'error': str(e)}), 400

@inspection_bp.route('/images/<image_id>/inspect', methods=['POST'])
@jwt_required()
def inspect_image(image_id):
    """이미지 검사 API"""
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if not image:
            return jsonify({
                "status": 404,
                "message": "이미지를 찾을 수 없음"
            }), 404

        # AI 분석 결과 (임시 데이터)
        analysis_result = {
            "animalType": "고라니",
            "accuracy": 97
        }
        
        # 분석 결과 저장
        db.images.update_one(
            {'_id': ObjectId(image_id)},
            {
                '$set': {
                    'BestClass': analysis_result['animalType'],
                    'inspection_status': 'pending',
                    'inspection_date': datetime.utcnow()
                }
            }
        )

        return jsonify({
            "status": 200,
            "message": "이미지 검사 완료",
            "result": analysis_result
        }), 200

    except Exception as e:
        return jsonify({
            "status": 400,
            "message": f"검사 실패: {str(e)}"
        }), 400 