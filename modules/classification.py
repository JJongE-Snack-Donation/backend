from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from bson import ObjectId
from datetime import datetime
from typing import Tuple, Dict, Any, List, Optional
from .database import db
from .database import (
    get_images, 
    get_classified_image_detail, 
    get_unclassified_image_detail,
    delete_classified_image,
    delete_unclassified_image,
    update_classified_image,    
    update_unclassified_image,
    save_image_data
)
from .utils.response import standard_response, handle_exception, pagination_meta
from .utils.constants import PER_PAGE_DEFAULT, VALID_EXCEPTION_STATUSES, MESSAGES, VALID_INSPECTION_STATUSES

classification_bp = Blueprint('classification', __name__)

def update_image(image_id, update_data, is_classified):
    """
    통합된 이미지 업데이트 함수
    Args:
        image_id: 이미지 ID
        update_data: 업데이트할 데이터
        is_classified: 분류된 이미지 여부
    """
    try:
        valid_fields = {
            'classified': {'BestClass', 'Count', 'Infos'},
            'unclassified': {'exception_status', 'Count'}
        }
        
        field_set = valid_fields['classified'] if is_classified else valid_fields['unclassified']
        update_dict = {k: v for k, v in update_data.items() if k in field_set}
        
        if not update_dict:
            return False, "업데이트할 내용이 없습니다"

        result = db.images.update_one(
            {'_id': ObjectId(image_id), 'is_classified': is_classified},
            {'$set': update_dict}
        )
        
        return result.modified_count > 0, None
        
    except Exception as e:
        return False, str(e)

@classification_bp.route('/images', methods=['GET'])
@jwt_required()
def list_images() -> Tuple[Dict[str, Any], int]:
    """이미지 목록 조회 API"""
    try:
        is_classified = request.args.get('classified', default=None)
        if is_classified is not None:
            is_classified = is_classified.lower() == 'true'
            
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))
        
        query: Dict[str, Any] = {}
        if is_classified is not None:
            query['is_classified'] = is_classified
            
        total = db.images.count_documents(query)
        images: List[Dict[str, Any]] = list(db.images.find(query)
                     .skip((page - 1) * per_page)
                     .limit(per_page))
                     
        for image in images:
            image['_id'] = str(image['_id'])
            
        return standard_response(
            "이미지 목록 조회 성공",
            data={'images': images},
            meta=pagination_meta(total, page, per_page)
        )
        
    except ValueError:
        return handle_exception(
            Exception("페이지 번호가 유효하지 않습니다"),
            error_type="validation_error"
        )
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@classification_bp.route('/classified-images/<image_id>', methods=['GET'])
@jwt_required()
def get_classified_image_details(image_id):
    """
    일반검수 이미지 상세 정보 조회 API
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
    예외검수 이미지 상세 정보 조회 API
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
    # 위에꺼 다 필요없고 종 이름, 개체수만 들어가면 됨
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

@classification_bp.route('/images/unclassified', methods=['GET'])
@jwt_required()
def get_unclassified_images():
    """미분류 이미지 리스트 조회 API"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        images = list(db.images.find(
            {'is_classified': False},
            {'_id': 1, 'FileName': 1, 'ThumnailPath': 1, 'DateTimeOriginal': 1}
        ).skip((page - 1) * per_page).limit(per_page))
        
        return jsonify({
            "status": 200,
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "uploadDate": img['DateTimeOriginal']
            } for img in images]
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/images/classified', methods=['GET'])
@jwt_required()
def get_classified_images():
    """종분류 이미지 리스트 조회 API"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        sequence = request.args.get('sequenceNumber')
        
        query = {'is_classified': True}
        if sequence:
            query['evtnum'] = int(sequence)
            
        images = list(db.images.find(
            query,
            {'_id': 1, 'FileName': 1, 'ThumnailPath': 1, 'BestClass': 1, 'evtnum': 1}
        ).skip((page - 1) * per_page).limit(per_page))
        
        return jsonify({
            "status": 200,
            "images": [{
                "imageId": str(img['_id']),
                "sequenceNumber": img.get('evtnum'),
                "imageUrl": img['ThumnailPath'],
                "classificationResult": img.get('BestClass', '미확인')
            } for img in images]
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/images/<image_id>', methods=['GET'])
@jwt_required()
def get_image_detail(image_id):
    """이미지 상세 정보 조회 API"""
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if not image:
            return jsonify({
                "status": 404,
                "message": "이미지를 찾을 수 없음"
            }), 404
            
        return jsonify({
            "status": 200,
            "image": {
                "imageId": str(image['_id']),
                "classificationResult": image.get('BestClass', '미확인'),
                "details": {
                    "captureDate": image.get('DateTimeOriginal'),
                    "location": image.get('ProjectInfo', {}).get('location'),
                    "animalType": image.get('BestClass')
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/images/<image_id>', methods=['DELETE'])
@jwt_required()
def delete_image(image_id):
    """이미지 삭제 API"""
    try:
        result = db.images.delete_one({'_id': ObjectId(image_id)})
        if result.deleted_count == 0:
            return jsonify({
                "status": 404,
                "message": "이미지를 찾을 수 없음"
            }), 404
            
        return jsonify({
            "status": 200,
            "message": "이미지 삭제 성공"
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/inspection/normal', methods=['GET'])
@jwt_required()
def get_normal_inspection_images():
    """
    일반검수(종분류) 이미지 조회 API
    query parameters:
    - project_name: 프로젝트 이름
    - start_date: 시작 날짜 (YYYY-MM-DD)
    - end_date: 종료 날짜 (YYYY-MM-DD)
    - serial_number: 카메라 시리얼
    - camera_label: 카메라 라벨
    - species_name: 종 이름
    - page: 페이지 번호 (default: 1)
    - per_page: 페이지당 이미지 수 (default: 20)
    """
    try:
        # 쿼리 파라미터 파싱
        project_name = request.args.get('project_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        serial_number = request.args.get('serial_number')
        camera_label = request.args.get('camera_label')
        species_name = request.args.get('species_name')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # 쿼리 조건 구성
        query = {'is_classified': True}
        if project_name:
            query['ProjectInfo.ProjectName'] = project_name
        if start_date and end_date:
            query['DateTimeOriginal'] = {
                '$gte': datetime.strptime(start_date, '%Y-%m-%d'),
                '$lte': datetime.strptime(end_date, '%Y-%m-%d')
            }
        if serial_number:
            query['SerialNumber'] = serial_number
        if camera_label:
            query['UserLabel'] = camera_label
        if species_name:
            query['BestClass'] = species_name

        # 이미지 조회
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                     .skip((page - 1) * per_page)
                     .limit(per_page))

        return jsonify({
            "status": 200,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "projectName": img.get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": img.get('DateTimeOriginal'),
                "serialNumber": img.get('SerialNumber'),
                "cameraLabel": img.get('UserLabel'),
                "speciesName": img.get('BestClass')
            } for img in images]
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/inspection/exception', methods=['GET'])
@jwt_required()
def get_exception_inspection_images():
    """
    예외검수(미분류) 이미지 조회 API
    query parameters:
    - project_name: 프로젝트 이름
    - start_date: 시작 날짜 (YYYY-MM-DD)
    - end_date: 종료 날짜 (YYYY-MM-DD)
    - serial_number: 카메라 시리얼
    - camera_label: 카메라 라벨
    - exception_status: 예외 처리 상태 (pending/processed)
    - page: 페이지 번호
    - per_page: 페이지당 이미지 수
    """
    try:
        # 쿼리 파라미터 파싱
        project_name = request.args.get('project_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        serial_number = request.args.get('serial_number')
        camera_label = request.args.get('camera_label')
        exception_status = request.args.get('exception_status')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # 쿼리 조건 구성
        query = {'is_classified': False}
        if project_name:
            query['ProjectInfo.ProjectName'] = project_name
        if start_date and end_date:
            query['DateTimeOriginal'] = {
                '$gte': datetime.strptime(start_date, '%Y-%m-%d'),
                '$lte': datetime.strptime(end_date, '%Y-%m-%d')
            }
        if serial_number:
            query['SerialNumber'] = serial_number
        if camera_label:
            query['UserLabel'] = camera_label
        if exception_status:
            query['exception_status'] = exception_status

        # 이미지 조회
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                     .skip((page - 1) * per_page)
                     .limit(per_page))

        return jsonify({
            "status": 200,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "projectName": img.get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": img.get('DateTimeOriginal'),
                "serialNumber": img.get('SerialNumber'),
                "cameraLabel": img.get('UserLabel'),
                "exceptionStatus": img.get('exception_status', 'pending')
            } for img in images]
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/images/bulk-delete', methods=['POST'])
@jwt_required()
def delete_multiple_images():
    """
    다중 이미지 삭제 API
    Request Body:
    {
        "image_ids": ["id1", "id2", ...]
    }
    """
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        
        if not image_ids:
            return jsonify({
                "status": 400,
                "message": "삭제할 이미지 ID가 필요합니다"
            }), 400

        # ObjectId로 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 이미지 삭제
        result = db.images.delete_many({'_id': {'$in': object_ids}})
        
        return jsonify({
            "status": 200,
            "message": f"{result.deleted_count}개의 이미지가 삭제되었습니다"
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/inspection/normal/groups', methods=['GET'])
@jwt_required()
def get_normal_inspection_groups():
    """
    일반검수 - 이미지 그룹 목록 조회 API
    Query Parameters:
    - serial_number: 카메라 시리얼 번호
    - camera_label: 카메라 라벨
    - page: 페이지 번호
    - per_page: 페이지당 항목 수
    """
    try:
        # 쿼리 파라미터 처리
        serial_number = request.args.get('serial_number')
        camera_label = request.args.get('camera_label')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 조건
        query = {'is_classified': True}
        
        # 선택적 필터 적용
        if serial_number:
            query['SerialNumber'] = serial_number
        if camera_label:
            query['UserLabel'] = camera_label

        # 이벤트 번호로 그룹핑하여 조회
        pipeline = [
            {'$match': query},
            {'$sort': {'DateTimeOriginal': 1}},
            {'$group': {
                '_id': {
                    'evtnum': '$evtnum',
                    'SerialNumber': '$SerialNumber'
                },
                'first_image': {'$first': '$$ROOT'},
                'image_count': {'$sum': 1},
                'DateTimeOriginal': {'$first': '$DateTimeOriginal'}
            }},
            {'$sort': {'DateTimeOriginal': -1}},
            {'$skip': (page - 1) * per_page},
            {'$limit': per_page}
        ]

        groups = list(db.images.aggregate(pipeline))
        
        # 전체 그룹 수 계산
        total_groups = len(list(db.images.aggregate([
            {'$match': query},
            {'$group': {
                '_id': {
                    'evtnum': '$evtnum',
                    'SerialNumber': '$SerialNumber'
                }
            }}
        ])))

        response_data = {
            "total": total_groups,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_groups + per_page - 1) // per_page,
            "groups": [{
                "evtnum": group['_id']['evtnum'],
                "serialNumber": group['_id']['SerialNumber'],
                "imageCount": group['image_count'],
                "thumbnail": group['first_image']['ThumnailPath'],
                "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": group['first_image'].get('DateTimeOriginal'),
                "cameraLabel": group['first_image'].get('UserLabel')
            } for group in groups]
        }

        return standard_response("그룹 목록 조회 성공", data=response_data)

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/inspection/exception/groups', methods=['GET'])
@jwt_required()
def get_exception_inspection_groups():
    """
    예외검수 - 이미지 그룹 목록 조회 API
    Query Parameters:
    - serial_number: 카메라 시리얼 번호
    - camera_label: 카메라 라벨
    - exception_status: 예외 상태
    - page: 페이지 번호
    - per_page: 페이지당 항목 수
    """
    try:
        # 쿼리 파라미터 처리
        serial_number = request.args.get('serial_number')
        camera_label = request.args.get('camera_label')
        exception_status = request.args.get('exception_status')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 조건
        query = {'is_classified': False}
        
        # 선택적 필터 적용
        if serial_number:
            query['SerialNumber'] = serial_number
        if camera_label:
            query['UserLabel'] = camera_label
        if exception_status:
            query['exception_status'] = exception_status

        # evtnum 기준으로 그룹핑하여 조회
        pipeline = [
            {'$match': query},
            {'$sort': {'DateTimeOriginal': 1}},
            {'$group': {
                '_id': {
                    'evtnum': '$evtnum',
                    'SerialNumber': '$SerialNumber'
                },
                'first_image': {'$first': '$$ROOT'},
                'image_count': {'$sum': 1},
                'DateTimeOriginal': {'$first': '$DateTimeOriginal'}
            }},
            {'$sort': {'DateTimeOriginal': -1}},
            {'$skip': (page - 1) * per_page},
            {'$limit': per_page}
        ]

        groups = list(db.images.aggregate(pipeline))
        
        # 전체 그룹 수 계산
        total_groups = len(list(db.images.aggregate([
            {'$match': query},
            {'$group': {
                '_id': {
                    'evtnum': '$evtnum',
                    'SerialNumber': '$SerialNumber'
                }
            }}
        ])))

        response_data = {
            "total": total_groups,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_groups + per_page - 1) // per_page,
            "groups": [{
                "evtnum": group['_id']['evtnum'],
                "serialNumber": group['_id']['SerialNumber'],
                "imageCount": group['image_count'],
                "thumbnail": group['first_image']['ThumnailPath'],
                "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": group['first_image'].get('DateTimeOriginal'),
                "cameraLabel": group['first_image'].get('UserLabel'),
                "exceptionStatus": group['first_image'].get('exception_status', 'pending')
            } for group in groups]
        }

        return standard_response("그룹 목록 조회 성공", data=response_data)

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/inspection/normal/group-images/<serial_number>/<int:evtnum>', methods=['GET'])
@jwt_required()
def get_normal_group_images(serial_number, evtnum):
    """
    일반검수 - 특정 evtnum 그룹의 이미지들 조회 API
    Parameters:
    - serial_number: 카메라 시리얼 번호
    - evtnum: 이벤트 번호
    """
    try:
        images = list(db.images.find({
            'SerialNumber': serial_number,
            'evtnum': evtnum,
            'is_classified': True
        }).sort('DateTimeOriginal', 1))

        response_data = {
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "fileName": img['FileName'],
                "projectName": img.get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": img.get('DateTimeOriginal'),
                "serialNumber": img.get('SerialNumber'),
                "cameraLabel": img.get('UserLabel'),
                "bestClass": img.get('BestClass'),
                "count": img.get('Count'),
                "is_favorite": img.get('is_favorite', False)
            } for img in images]
        }

        return standard_response("이미지 목록 조회 성공", data=response_data)

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/inspection/exception/group-images/<serial_number>/<int:evtnum>', methods=['GET'])
@jwt_required()
def get_exception_group_images(serial_number, evtnum):
    """
    예외검수 - 특정 evtnum 그룹의 이미지들 조회 API
    Parameters:
    - serial_number: 카메라 시리얼 번호
    - evtnum: 이벤트 번호
    """
    try:
        images = list(db.images.find({
            'SerialNumber': serial_number,
            'evtnum': evtnum,
            'is_classified': False
        }).sort('DateTimeOriginal', 1))

        response_data = {
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img['ThumnailPath'],
                "fileName": img['FileName'],
                "projectName": img.get('ProjectInfo', {}).get('ProjectName'),
                "dateTime": img.get('DateTimeOriginal'),
                "serialNumber": img.get('SerialNumber'),
                "cameraLabel": img.get('UserLabel'),
                "exceptionStatus": img.get('exception_status', 'pending'),
                "is_favorite": img.get('is_favorite', False),
                "inspection_complete": img.get('inspection_complete', False)
            } for img in images]
        }

        return standard_response("이미지 목록 조회 성공", data=response_data)

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/inspection/normal/bulk-update', methods=['POST'])
@jwt_required()
def update_normal_inspection_bulk():
    """
    일반검수 - 다중 이미지 정보 수정 API
    Request Body:
    {
        "image_ids": ["id1", "id2", ...],
        "updates": {
            "BestClass": "종명",     # 선택적
            "Count": 3              # 선택적
        }
    }
    """
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        updates = data.get('updates', {})
        
        if not image_ids:
            return standard_response("이미지 ID 목록이 필요합니다", status=400)

        # ObjectId로 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 업데이트할 필드 검증
        valid_fields = {'BestClass', 'Count'}
        update_dict = {k: v for k, v in updates.items() if k in valid_fields}
        
        if not update_dict:
            return standard_response("수정할 내용이 없습니다", status=400)

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {
                '_id': {'$in': object_ids},
                'is_classified': True
            },
            {'$set': update_dict}
        )

        return standard_response(f"{result.modified_count}개의 이미지가 수정되었습니다")

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/inspection/exception/bulk-update', methods=['POST'])
@jwt_required()
def update_exception_inspection_bulk():
    """
    예외검수 - 다중 이미지 정보 수정 API
    Request Body:
    {
        "image_ids": ["id1", "id2", ...],
        "updates": {
            "exception_status": "processed",  # 선택적
            "Count": 3                        # 선택적
        }
    }
    """
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        updates = data.get('updates', {})
        
        if not image_ids:
            return standard_response("이미지 ID 목록이 필요합니다", status=400)

        # ObjectId로 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 업데이트할 필드 검증
        valid_fields = {'exception_status', 'Count'}
        update_dict = {k: v for k, v in updates.items() if k in valid_fields}
        
        if not update_dict:
            return standard_response("수정할 내용이 없습니다", status=400)

        # exception_status 값 검증
        if 'exception_status' in update_dict and update_dict['exception_status'] not in VALID_EXCEPTION_STATUSES:
            return standard_response("유효하지 않은 예외 상태입니다", status=400)

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {
                '_id': {'$in': object_ids},
                'is_classified': False
            },
            {'$set': update_dict}
        )

        return standard_response(f"{result.modified_count}개의 이미지가 수정되었습니다")

    except Exception as e:
        return handle_exception(e)

@classification_bp.route('/classification/batch', methods=['POST'])
@jwt_required()
def batch_classify() -> Tuple[Dict[str, Any], int]:
    """이미지 일괄 분류 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        classification = data.get('classification', {})
        
        if not image_ids or not classification:
            return handle_exception(
                Exception(MESSAGES['error']['invalid_request']),
                error_type="validation_error"
            )
            
        # ObjectId 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 업데이트 데이터 준비
        update_dict: Dict[str, Any] = {
            'is_classified': True,
            'classification_date': datetime.utcnow(),
            **classification
        }
        
        # 일괄 업데이트
        result = db.images.update_many(
            {'_id': {'$in': object_ids}},
            {'$set': update_dict}
        )

        return standard_response(
            f"{result.modified_count}개의 이미지가 분류되었습니다",
            data={'modified_count': result.modified_count}
        )

    except Exception as e:
        return handle_exception(e, error_type="db_error")

@classification_bp.route('/classification/batch-update', methods=['POST'])
@jwt_required()
def batch_update() -> Tuple[Dict[str, Any], int]:
    """이미지 일괄 업데이트 API"""
    try:
        data = request.get_json()
        image_ids = data.get('image_ids', [])
        updates = data.get('updates', {})
        
        if not image_ids:
            return handle_exception(
                Exception("이미지 ID 목록이 필요합니다"),
                error_type="validation_error"
            )

        # ObjectId 변환
        object_ids = [ObjectId(id) for id in image_ids]
        
        # 업데이트할 필드 검증
        valid_fields = {'exception_status', 'Count'}
        update_dict = {k: v for k, v in updates.items() if k in valid_fields}
        
        if not update_dict:
            return handle_exception(
                Exception("수정할 내용이 없습니다"),
                error_type="validation_error"
            )

        # exception_status 값 검증
        if ('exception_status' in update_dict and 
            update_dict['exception_status'] not in VALID_EXCEPTION_STATUSES):
            return handle_exception(
                Exception("유효하지 않은 예외 상태입니다"),
                error_type="validation_error"
            )

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {
                '_id': {'$in': object_ids},
                'is_classified': False
            },
            {'$set': update_dict}
        )

        return standard_response(f"{result.modified_count}개의 이미지가 수정되었습니다")

    except Exception as e:
        return handle_exception(e, error_type="db_error")