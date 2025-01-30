from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from .database import db
from .database import (
    get_images, 
    get_classified_image_detail, 
    get_unclassified_image_detail,
    delete_classified_image,
    delete_unclassified_image,
    update_classified_image,    
    update_unclassified_image 
)

classification_bp = Blueprint('classification', __name__)

@classification_bp.route('/images', methods=['GET'])
@jwt_required()
def list_images():
    """
    분류/미분류 이미지 조회 API
    query parameters:
    - classified: true/false (optional)
    - page: 페이지 번호 (default: 1)
    - per_page: 페이지당 이미지 수 (default: 12)
    """
    # 쿼리 파라미터 파싱
    is_classified = request.args.get('classified', default=None)
    if is_classified is not None:
        is_classified = is_classified.lower() == 'true'
    
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=12, type=int)
    
    # 이미지 조회
    result = get_images(is_classified, page, per_page)
    
    if 'error' in result:
        return jsonify({'message': 'Failed to fetch images', 'error': result['error']}), 500
        
    return jsonify(result), 200

@classification_bp.route('/classified-images/<image_id>', methods=['GET'])
@jwt_required()
def get_classified_image_details(image_id):
    """
    분류된 이미지 상세 정보 조회 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        result = get_classified_image_detail(object_id)
        
        if not result:
            return jsonify({'message': 'Classified image not found'}), 404
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/unclassified-images/<image_id>', methods=['GET'])
@jwt_required()
def get_unclassified_image_details(image_id):
    """
    미분류 이미지 상세 정보 조회 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        result = get_unclassified_image_detail(object_id)
        
        if not result:
            return jsonify({'message': 'Unclassified image not found'}), 404
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/classified-images/<image_id>', methods=['DELETE'])
@jwt_required()
def delete_classified_image_endpoint(image_id):
    """
    분류된 이미지 삭제 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        result = delete_classified_image(object_id)
        
        if result.get('error'):
            return jsonify({'message': 'Failed to delete image', 'error': result['error']}), 500
            
        if result.get('deleted') == False:
            return jsonify({'message': 'Classified image not found'}), 404
            
        return jsonify({'message': 'Image successfully deleted'}), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/unclassified-images/<image_id>', methods=['DELETE'])
@jwt_required()
def delete_unclassified_image_endpoint(image_id):
    """
    미분류 이미지 삭제 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        result = delete_unclassified_image(object_id)
        
        if result.get('error'):
            return jsonify({'message': 'Failed to delete image', 'error': result['error']}), 500
            
        if result.get('deleted') == False:
            return jsonify({'message': 'Unclassified image not found'}), 404
            
        return jsonify({'message': 'Image successfully deleted'}), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400
    

@classification_bp.route('/classified-images/<image_id>', methods=['PUT'])
@jwt_required()
def update_classified_image_endpoint(image_id):
    """
    분류된 이미지 정보 수정 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    Request Body:
    - species: 종 분류 결과
    - location: 위치 정보
    - capture_date: 촬영 날짜
    - metadata: 기타 메타데이터
    """
    try:
        object_id = ObjectId(image_id)
        update_data = request.get_json()
        
        # 필수 필드 검증
        required_fields = ['Infos', 'Count', 'BestClass']
        if not all(field in update_data for field in required_fields):
            return jsonify({'message': 'Missing required fields'}), 400
            
        # Infos 배열의 각 항목 검증
        for info in update_data.get('Infos', []):
            required_info_fields = ['best_class', 'best_probability', 'name', 'bbox']
            if not all(field in info for field in required_info_fields):
                return jsonify({'message': 'Invalid Infos data structure'}), 400
        
        result = update_classified_image(object_id, update_data)
        
        if result.get('error'):
            return jsonify({'message': 'Failed to update image', 'error': result['error']}), 500
            
        if result.get('updated') == False:
            return jsonify({'message': 'Classified image not found'}), 404
            
        return jsonify({'message': 'Image successfully updated'}), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/unclassified-images/<image_id>', methods=['PUT'])
@jwt_required()
def update_unclassified_image_endpoint(image_id):
    """
    미분류 이미지 정보 수정 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    Request Body:
    - ProjectInfo: 프로젝트 정보
        - ProjectName: 프로젝트명
        - ID: 프로젝트 ID
    - AnalysisFolder: 분석 폴더명
    """
    try:
        object_id = ObjectId(image_id)
        update_data = request.get_json()
        
        # ProjectInfo 구조 검증
        if 'ProjectInfo' in update_data:
            required_project_fields = ['ProjectName', 'ID']
            if not all(field in update_data['ProjectInfo'] for field in required_project_fields):
                return jsonify({'message': 'Invalid ProjectInfo structure'}), 400
        
        result = update_unclassified_image(object_id, update_data)
        
        if result.get('error'):
            return jsonify({'message': 'Failed to update image', 'error': result['error']}), 500
            
        if result.get('updated') == False:
            return jsonify({'message': 'Unclassified image not found'}), 404
            
        return jsonify({'message': 'Image successfully updated'}), 200
    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/images/<image_id>/update', methods=['PUT'])
@jwt_required()
def update_image_classification(image_id):
    """이미지 분류 결과 수정 API"""
    try:
        # ObjectId 변환
        object_id = ObjectId(image_id)
        
        # 요청 데이터 확인
        data = request.get_json()
        is_classified = data.get('is_classified')
        
        if is_classified is None:
            return jsonify({'message': 'Classification status is required'}), 400
            
        # 이미지 존재 확인
        image = db.images.find_one({'_id': object_id})
        if not image:
            return jsonify({'message': 'Image not found'}), 404
            
        # 분류 상태 업데이트
        update_result = db.images.update_one(
            {'_id': object_id},
            {'$set': {'is_classified': is_classified}}
        )
        
        if update_result.modified_count == 0:
            return jsonify({'message': 'No changes made'}), 200
            
        # 업데이트된 이미지 정보 조회
        updated_image = db.images.find_one({'_id': object_id})
        
        # 응답 데이터 구성
        if is_classified:
            response_data = {
                # TODO: 딥러닝 분석 결과 필드 (추후 구현)
                'ImageDatas': {
                    '_id': str(updated_image['_id']),
                    'FileName': updated_image.get('FileName'),
                    'FilePath': updated_image.get('FilePath'),
                    'OriginalFileName': updated_image.get('OriginalFileName'),
                    'ThumnailPath': updated_image.get('ThumnailPath'),
                    'SerialNumber': updated_image.get('SerialNumber'),
                    'UserLabel': updated_image.get('UserLabel'),
                    'DateTimeOriginal': updated_image.get('DateTimeOriginal'),
                    'ProjectInfo': updated_image.get('ProjectInfo'),
                    'AnalysisFolder': updated_image.get('AnalysisFolder'),
                    'sessionid': updated_image.get('sessionid'),
                    'uploadState': updated_image.get('uploadState'),
                    'serial_filename': updated_image.get('serial_filename')
                }
            }
        else:
            response_data = {
                'FileName': updated_image.get('FileName'),
                'FilePath': updated_image.get('FilePath'),
                'OriginalFileName': updated_image.get('OriginalFileName'),
                'ThumnailPath': updated_image.get('ThumnailPath'),
                'SerialNumber': updated_image.get('SerialNumber'),
                'UserLabel': updated_image.get('UserLabel'),
                'DateTimeOriginal': updated_image.get('DateTimeOriginal'),
                'ProjectInfo': updated_image.get('ProjectInfo'),
                'AnalysisFolder': updated_image.get('AnalysisFolder'),
                'sessionid': updated_image.get('sessionid'),
                'uploadState': updated_image.get('uploadState'),
                'serial_filename': updated_image.get('serial_filename')
            }
            
        return jsonify({
            'message': 'Image classification updated successfully',
            'image': response_data
        }), 200
        
    except Exception as e:
        return jsonify({'message': 'Update failed', 'error': str(e)}), 400