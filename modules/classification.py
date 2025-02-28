from flask import Blueprint, request, jsonify, current_app
import logging
from urllib.parse import quote
from flask_jwt_extended import jwt_required
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from typing import Tuple, Dict, Any, List, Optional
from .database import db
from .database import (
    get_classified_image_detail, 
    get_unclassified_image_detail,
    delete_classified_image,
    delete_unclassified_image,
    update_classified_image,    
    update_unclassified_image
)
import os
from .utils.response import standard_response, handle_exception, pagination_meta
from .utils.constants import PER_PAGE_DEFAULT, VALID_EXCEPTION_STATUSES, MESSAGES, VALID_INSPECTION_STATUSES
import logging as logger
classification_bp = Blueprint('classification', __name__)
def generate_image_url(thumbnail_path):
    """
    Generate a URL for the given thumbnail path.
    """
    if not thumbnail_path:
        # thumbnail_path가 None 또는 빈 문자열인 경우 기본값 반환
        return None

    # 경로 정규화
    thumbnail_path = os.path.normpath(thumbnail_path)
    base_path = os.path.normpath(r"C:\Users\User\Documents\backend\mnt") # << 여기 본인 경로 추가

    if thumbnail_path.startswith(base_path):
        relative_path = thumbnail_path[len(base_path):].lstrip(os.sep)
    else:
        # 예상과 다른 경로 형식인 경우 로그 출력
        logging.error(f"Unexpected thumbnail path format: {thumbnail_path}")
        return None

    # URL 인코딩 및 URL 생성
    encoded_path = quote(relative_path.replace("\\", "/"))
    return f"http://localhost:5000/images/{encoded_path}"

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
    """검수 완료된 이미지 목록 조회 API"""
    try:
        is_classified = request.args.get('classified', default=None)
        if is_classified is not None:
            is_classified = is_classified.lower() == 'true'

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리: 검수 완료된 이미지만 조회
        query: Dict[str, Any] = {'inspection_complete': True}

        if is_classified is not None:
            query['is_classified'] = is_classified

        total = db.images.count_documents(query)
        images: List[Dict[str, Any]] = list(db.images.find(query)
                     .skip((page - 1) * per_page)
                     .limit(per_page))

        for image in images:
            image['_id'] = str(image['_id'])

        return standard_response(
            "검수 완료된 이미지 목록 조회 성공",
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


from bson import ObjectId

@classification_bp.route('/classified-images/<image_id>', methods=['GET'])
@jwt_required()
def get_classified_image_details(image_id):
    """일반검수 이미지 상세 정보 조회 API"""
    try:
        # ObjectId 변환을 시도하고, 실패하면 문자열 처리
        try:
            object_id = ObjectId(image_id)
        except Exception:
            object_id = None  # 변환 실패 시 None 할당

        # images 컬렉션에서 해당 이미지 찾기 + detect_images 조인
        query_filter = {"_id": object_id} if object_id else {"Image_id": image_id}

        result = db.images.aggregate([
            {"$match": query_filter},  # ObjectId 조회 또는 Image_id 조회
            {
                "$lookup": {
                    "from": "detect_images",
                    "let": { "imageId": { "$toString": "$_id" } },  # _id를 문자열로 변환
                    "pipeline": [
                        { "$match": { "$expr": { "$eq": ["$Image_id", "$$imageId"] } } }
                    ],
                    "as": "detection_data"
                }
            },
            {"$unwind": {"path": "$detection_data", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "_id": 1,
                    "FileName": 1,
                    "FilePath": 1,
                    "ThumnailPath": 1,
                    "DateTimeOriginal": 1,
                    "SerialNumber": 1,
                    "ProjectInfo": 1,
                    "Latitude": {"$ifNull": ["$detection_data.Latitude", "$Latitude"]}, 
                    "Longitude": {"$ifNull": ["$detection_data.Longitude", "$Longitude"]},
                    "BestClass": {"$ifNull": ["$detection_data.BestClass", "미확인"]},
                    "Accuracy": {"$ifNull": ["$detection_data.Accuracy", 0]},
                    "species": {"$ifNull": ["$detection_data.BestClass", "미확인"]},
                    "Count": {"$ifNull": ["$detection_data.Count", 0]},
                    "is_classified": 1,
                    "classification_date": 1,
                    "inspection_status": 1,
                    "inspection_date": 1,
                    "inspection_complete": 1,
                    "exception_status": 1,
                    "exception_comment": 1,
                    "is_favorite": 1
                }
            }
        ])

        image_data = list(result)
        if not image_data:
            return jsonify({'message': 'Classified image not found'}), 404

        return jsonify(image_data[0]), 200

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
        result = db.images.aggregate([
            {"$match": {"_id": object_id}},  # images 컬렉션에서 이미지 찾기
            {
                "$lookup": {
                    "from": "detect_images",
                    "let": { "imageId": "$_id" },  # ObjectId 변환
                    "pipeline": [
                        { "$match": { "$expr": { "$eq": ["$Image_id", "$$imageId"] } } }
                    ],
                    "as": "detection_data"
                }
            },
            {"$unwind": {"path": "$detection_data", "preserveNullAndEmptyArrays": True}},  # 데이터가 없을 경우 허용
            {
                "$project": {
                    "_id": 1,
                    "FileName": 1,
                    "FilePath": {"$ifNull": ["$FilePath", ""]},  # 일반검수 API와 동일한 구조 유지
                    "ThumnailPath": {"$ifNull": ["$ThumnailPath", ""]},  # 일반검수 API에 맞춰 추가
                    "DateTimeOriginal": 1,
                    "SerialNumber": 1,
                    "ProjectInfo": 1,
                    "Latitude": {"$ifNull": ["$detection_data.Latitude", "$Latitude"]},  # detect_images 없으면 images 값 사용
                    "Longitude": {"$ifNull": ["$detection_data.Longitude", "$Longitude"]},
                    "BestClass": {"$ifNull": ["$detection_data.BestClass", "$BestClass"]}, # detect_images 없으면 images 값 사용
                    "Accuracy": {"$ifNull": ["$detection_data.Accuracy", "$Accuracy"]},  # detect_images 없으면 images 값 사용
                    "species": {"$ifNull": ["$detection_data.BestClass", "$BestClass"]},  # 종명 추가
                    "Count": {"$ifNull": ["$detection_data.Count", "$Count"]},
                    "is_classified": 1,
                    "classification_date": 1,
                    "inspection_status": 1,
                    "inspection_date": 1,
                    "inspection_complete": 1,
                    "exception_status": 1,
                    "exception_comment": 1,
                    "is_favorite": 1
                }
            }
        ])

        image_data = list(result)
        if not image_data:
            return jsonify({
                "status": 404,
                "message": "Unclassified image not found"
            }), 404

        return jsonify({
            "status": 200,
            "data": image_data[0]
        }), 200

    except Exception as e:
        return jsonify({
            "status": 400,
            "message": "Invalid image ID format or other error",
            "error": str(e)
        }), 400


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
    - count: 개체 수 (필수)
    - best_class: 가장 확신 있는 분류 (필수)
    """
    try:
        object_id = ObjectId(image_id)
        update_data = request.get_json()

        # 필수 필드 검증
        if 'count' not in update_data or 'best_class' not in update_data:
            return jsonify({'message': 'Missing required fields'}), 400

        # MongoDB 업데이트 실행
        result = db.images.update_one(
            {'_id': object_id},
            {'$set': {
                'count': update_data['count'],
                'best_class': update_data['best_class']
            }}
        )

        # 업데이트 결과 확인
        if result.matched_count == 0:
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
    - best_class: AI가 예측한 최상의 클래스 (필수)
    - status: 탐지 상태 (필수)
    - object_counts: 객체 카운트 정보 (필수)
    """
    try:
        object_id = ObjectId(image_id)
        update_data = request.get_json()

        # 필수 필드 검증
        if 'best_class' not in update_data or 'status' not in update_data or 'object_counts' not in update_data:
            return jsonify({'message': 'Missing required fields'}), 400

        # MongoDB 업데이트 실행
        result = db.images.update_one(
            {'_id': object_id},
            {'$set': {
                'best_class': update_data['best_class'],
                'status': update_data['status'],
                'object_counts': update_data['object_counts']
            }}
        )

        # 업데이트 결과 확인
        if result.matched_count == 0:
            return jsonify({'message': 'Unclassified image not found'}), 404

        return jsonify({'message': 'Unclassified image successfully updated'}), 200

    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400

@classification_bp.route('/images/<image_id>', methods=['GET'])
@jwt_required()
def get_image_detail(image_id):
    """검수 완료된 이미지 상세 정보 조회 API"""
    try:
        object_id = ObjectId(image_id)

        # images와 detect_images를 조인하여 데이터 조회
        result = db.images.aggregate([
            {"$match": {"_id": object_id, "inspection_complete": True}},  # 검수 완료된 이미지만 조회
            {
                "$lookup": {
                    "from": "detect_images",  # detect_images 컬렉션과 조인
                    "let": { "imageId": "$_id" },
                    "pipeline": [
                        { "$match": { "$expr": { "$eq": ["$Image_id", "$$imageId"] } } }
                    ],
                    "as": "detection_data"
                }
            },
            {"$unwind": {"path": "$detection_data", "preserveNullAndEmptyArrays": True}},  # detect_images 데이터가 없을 경우 허용
            {
                "$project": {
                    "_id": 1,
                    "FileName": 1,
                    "FilePath": {"$ifNull": ["$FilePath", ""]},
                    "ThumnailPath": {"$ifNull": ["$ThumnailPath", ""]},
                    "DateTimeOriginal": 1,
                    "SerialNumber": 1,
                    "ProjectInfo": 1,
                    "Latitude": {"$ifNull": ["$detection_data.Latitude", "$Latitude"]},
                    "Longitude": {"$ifNull": ["$detection_data.Longitude", "$Longitude"]},
                    "BestClass": {"$ifNull": ["$detection_data.BestClass", "$BestClass"]},
                    "Accuracy": {"$ifNull": ["$detection_data.Accuracy", "$Accuracy"]},
                    "species": {"$ifNull": ["$detection_data.BestClass", "$BestClass"]},
                    "Count": {"$ifNull": ["$detection_data.Count", "$Count"]},  # 개체 수 추가
                    "is_classified": 1,
                    "classification_date": 1,
                    "inspection_status": 1,
                    "inspection_date": 1,
                    "inspection_complete": 1,
                    "exception_status": 1,
                    "exception_comment": 1,
                    "is_favorite": 1
                }
            }
        ])

        image_data = list(result)
        if not image_data:
            return jsonify({"status": 404, "message": "검수 완료된 이미지를 찾을 수 없음"}), 404

        image = image_data[0]

        # 촬영 날짜를 ISO 8601 형식으로 변환
        capture_date = image.get("DateTimeOriginal")
        if capture_date:
            capture_date = capture_date.isoformat()

        return jsonify({
            "status": 200,
            "image": {
                "imageId": str(image["_id"]),
                "classificationResult": image.get("BestClass", "미확인"),
                "details": {
                    "captureDate": capture_date,
                    "location": image.get("ProjectInfo", {}).get("ProjectName", "위치 정보 없음"),
                    "animalType": image.get("BestClass"),
                    "latitude": image.get("Latitude"),
                    "longitude": image.get("Longitude"),
                    "accuracy": image.get("Accuracy"),
                    "count": image.get("Count"),  
                    "thumbnailUrl": image.get("ThumnailPath"),  
                    "originalFilePath": image.get("FilePath"),  
                    "inspectionStatus": image.get("inspection_status"),  
                    "inspectionDate": image.get("inspection_date"),  
                    "classificationDate": image.get("classification_date"),  
                    "exceptionStatus": image.get("exception_status"),  
                    "exceptionComment": image.get("exception_comment"),  
                    "isFavorite": image.get("is_favorite")  
                }
            }
        }), 200

    except Exception as e:
        return jsonify({
            "status": 500,
            "message": f"서버 오류: {str(e)}"
        }), 500

@classification_bp.route('/images/classified', methods=['GET'])
@jwt_required()
def get_classified_images():
    """분류된 이미지 리스트 조회 API"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        sequence = request.args.get('sequenceNumber')

        query = {'is_classified': True}
        if sequence:
            query['evtnum'] = int(sequence)

        images = list(db.images.find(
            query,
            {
                '_id': 1, 
                'FileName': 1, 
                'ThumnailPath': 1, 
                'BestClass': 1, 
                'evtnum': 1, 
                'DateTimeOriginal': 1, 
                'ProjectInfo.ID': 1, 
                'ProjectInfo.ProjectName': 1
            }
        ).skip((page - 1) * per_page).limit(per_page))

        return jsonify({
            "status": 200,
            "images": [{
                "imageId": str(img['_id']),
                "imageUrl": img.get('ThumnailPath', ''),
                "uploadDate": img.get('DateTimeOriginal', ''),  # 통일된 필드
                "classificationResult": img.get('BestClass', '미확인'),  # 통일된 필드
                "sequenceNumber": img.get('evtnum'),
                "projectId": img.get('ProjectInfo', {}).get('ID', ''),  # 프로젝트 ID
                "projectName": img.get('ProjectInfo', {}).get('ProjectName', '')  # 프로젝트 이름
            } for img in images]
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
        # 이미지 조회
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if not image:
            return jsonify({
                "status": 404,
                "message": "이미지를 찾을 수 없음"
            }), 404

        # 물리적 파일 삭제
        for file_path in [image.get('FilePath'), image.get('ThumnailPath')]:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

        # DB에서 삭제
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
    """일반검수(종분류) 이미지 조회 API"""
    try:
        # 쿼리 파라미터 파싱
        project_id = request.args.get('project_id')  # 프로젝트 ID 추가
        project_name = request.args.get('project_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        serial_number = request.args.get('serial_number')
        species_name = request.args.get('species_name')
        evtnum = request.args.get('evtnum')  # 이벤트 번호
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # 기본 쿼리 조건 (분류된 이미지만 조회)
        query = {'is_classified': True}

        # 프로젝트 ID 필터 추가
        if project_id:
            query['ProjectInfo.ID'] = project_id

        if project_name:
            query['ProjectInfo.ProjectName'] = project_name

        if start_date and end_date:
            try:
                query['DateTimeOriginal'] = {
                    '$gte': datetime.strptime(start_date, '%Y-%m-%d').isoformat() + 'Z',
                    '$lte': datetime.strptime(end_date, '%Y-%m-%d').isoformat() + 'Z'
                }
            except ValueError:
                return jsonify({"status": 400, "message": "날짜 형식이 올바르지 않습니다."}), 400

        if serial_number:
            query['SerialNumber'] = serial_number

        if species_name:
            query['BestClass'] = species_name  # 종 필터 적용

        # 이벤트 번호 필터 추가 (int 변환 포함)
        if evtnum:
            try:
                query['evtnum'] = int(evtnum)
            except ValueError:
                return jsonify({"status": 400, "message": "evtnum 값이 올바르지 않습니다."}), 400

        # 이미지 조회
        total = db.images.count_documents(query)
        images = list(db.images.find(query, {
            '_id': 1,
            'FileName': 1,
            'ThumnailPath': 1,
            'DateTimeOriginal': 1,
            'ProjectInfo.ProjectName': 1,
            'ProjectInfo.ID': 1,  # 프로젝트 ID 포함
            'SerialNumber': 1,
            'BestClass': 1,
            'evtnum': 1
        }).skip((page - 1) * per_page).limit(per_page))

        return jsonify({
            "status": 200,
            "message": "일반 검수 이미지 조회 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "images": [{

                "imageId": str(img['_id']),
                "fileName": img['FileName'],
                "imageUrl": generate_image_url(img.get('ThumnailPath')),
                "uploadDate": img.get('DateTimeOriginal', {}).get('$date', ''),
                "projectId": img.get('ProjectInfo', {}).get('ID', ''),  # 프로젝트 ID 추가
                "projectName": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "serialNumber": img.get('SerialNumber', ''),
                "speciesName": img.get('BestClass', '미확인'),
                "evtnum": img.get('evtnum', ''),
                "exception_status": img.get('exception_status', ''),
            } for img in images]
        }), 200

    except Exception as e:
        logger.error(f"🚨 서버 오류 발생: {str(e)}", exc_info=True)  # ✅ 로그 남기기
        return jsonify({
            "status": 500,
            "message": f"서버 오류 발생: {str(e)}"
        }), 500




@classification_bp.route('/inspection/exception', methods=['GET'])
@jwt_required()
def get_exception_inspection_images():
    """
    예외검수(미분류) 이미지 조회 API
    query parameters:
    - project_id: 프로젝트 ID
    - project_name: 프로젝트 이름
    - start_date: 시작 날짜 (YYYY-MM-DD)
    - end_date: 종료 날짜 (YYYY-MM-DD)
    - serial_number: 카메라 시리얼
    - exception_status: 예외 처리 상태 (pending/processed)
    - evtnum: 이벤트 번호 (그룹 조회용)
    - page: 페이지 번호 (default: 1)
    - per_page: 페이지당 이미지 수 (default: 20)
    """
    try:
        # 쿼리 파라미터 파싱
        project_id = request.args.get('project_id')
        project_name = request.args.get('project_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        serial_number = request.args.get('serial_number')
        exception_status = request.args.get('exception_status')
        evtnum = request.args.get('evtnum')

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))

        # 기본 쿼리 조건 (미분류된 이미지만 조회)
        query = {'is_classified': False}

        # 프로젝트 ID 필터 추가 
        if project_id:
            query['ProjectInfo.ID'] = project_id
        elif project_name:
            query['ProjectInfo.ProjectName'] = project_name

        # 날짜 필터 추가 
        if start_date and end_date:
            query['DateTimeOriginal'] = {
                '$gte': datetime.strptime(start_date, '%Y-%m-%d'),
                '$lte': datetime.strptime(end_date, '%Y-%m-%d')
            }

        # 기타 필터 적용
        if serial_number:
            query['SerialNumber'] = serial_number
        if exception_status:
            query['exception_status'] = exception_status  # 예외 상태 필터 적용
        if evtnum:
            query['evtnum'] = int(evtnum)

        # 이미지 조회
        total = db.images.count_documents(query)
        images = list(db.images.find(query, {
            '_id': 1,
            'FileName': 1,
            'ThumnailPath': 1,
            'DateTimeOriginal': 1,
            'ProjectInfo.ID': 1,  # 프로젝트 ID 추가
            'ProjectInfo.ProjectName': 1,
            'SerialNumber': 1,
            'exception_status': 1,
            'evtnum': 1
        }).skip((page - 1) * per_page).limit(per_page))

        return jsonify({
            "status": 200,
            "message": "예외 검수 이미지 조회 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "images": [{
                "imageId": str(img['_id']),
                "fileName": img['FileName'],
                "imageUrl": generate_image_url(img.get('ThumnailPath')),
                "uploadDate": img['DateTimeOriginal'],
                "projectId": img.get('ProjectInfo', {}).get('ID', ''),  # 프로젝트 ID 포함
                "projectName": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "serialNumber": img.get('SerialNumber', ''),
                "exceptionStatus": img.get('exception_status', 'pending'),
                "evtnum": img.get('evtnum', '')
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



from bson.errors import InvalidId

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

        if not isinstance(updates, dict):
            return standard_response("업데이트 데이터 형식이 잘못되었습니다", status=400)

        # ObjectId 변환 (유효성 검사)
        object_ids = []
        invalid_ids = []
        for img_id in image_ids:
            try:
                object_ids.append(ObjectId(img_id))
            except InvalidId:
                invalid_ids.append(img_id)

        if invalid_ids:
            return standard_response(f"유효하지 않은 이미지 ID: {invalid_ids}", status=400)

        # 업데이트할 필드 검증 (타입 체크 추가)
        valid_fields = {'BestClass': str, 'Count': int}
        update_dict = {}
        for field, value in updates.items():
            if field in valid_fields:
                expected_type = valid_fields[field]
                if isinstance(value, expected_type):
                    update_dict[field] = value
                else:
                    return standard_response(f"'{field}' 필드는 {expected_type.__name__} 타입이어야 합니다", status=400)

        if not update_dict:
            return standard_response("수정할 내용이 없습니다", status=400)

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {'_id': {'$in': object_ids}, 'is_classified': True},
            {'$set': update_dict}
        )

        if result.matched_count == 0:
            return standard_response("해당 조건에 맞는 이미지가 없습니다", status=404)

        return standard_response(f"{result.modified_count}개의 이미지가 수정되었습니다", data={"modified_count": result.modified_count})

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

        # ObjectId 변환 (유효성 검사)
        object_ids = []
        invalid_ids = []
        for img_id in image_ids:
            try:
                object_ids.append(ObjectId(img_id))
            except Exception:  # bson.errors.InvalidId 사용 가능
                invalid_ids.append(img_id)

        if invalid_ids:
            return standard_response(f"유효하지 않은 이미지 ID: {invalid_ids}", status=400)

        # 업데이트할 필드 검증 (타입 체크 추가)
        valid_fields = {'exception_status': str, 'Count': int}
        update_dict = {}
        for field, value in updates.items():
            if field in valid_fields and isinstance(value, valid_fields[field]):
                update_dict[field] = value
            else:
                return standard_response(f"'{field}' 필드는 {valid_fields[field].__name__} 타입이어야 합니다", status=400)

        if not update_dict:
            return standard_response("수정할 내용이 없습니다", status=400)

        # exception_status 값 검증 (get() 활용)
        if update_dict.get("exception_status") and update_dict["exception_status"] not in VALID_EXCEPTION_STATUSES:
            return standard_response("유효하지 않은 예외 상태입니다", status=400)

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {'_id': {'$in': object_ids}, 'is_classified': False},
            {'$set': update_dict}
        )

        if result.matched_count == 0:
            return standard_response("수정할 이미지가 없습니다", status=404)

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
            'inspection_complete': True,  
            'inspection_date': datetime.utcnow(),  
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

@classification_bp.route('/images/batch-update', methods=['POST'])
@jwt_required()
def batch_update() -> Tuple[Dict[str, Any], int]:
    """분류된 이미지 포함 해서 속성 일괄 업데이트 API"""
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

@classification_bp.route('/image/<image_id>/inspection-status', methods=['PUT'])
@jwt_required()
def update_inspection_status(image_id: str) -> Tuple[Dict[str, Any], int]:
    """검사 상태 업데이트 API"""
    try:
        data = request.get_json()
        new_status = data.get('status')

        # 유효한 검사 상태인지 확인
        valid_statuses = set(VALID_INSPECTION_STATUSES) if isinstance(VALID_INSPECTION_STATUSES, (list, set)) else set()
        if not new_status or new_status not in valid_statuses:
            return handle_exception(
                Exception("유효하지 않은 검사 상태입니다"),
                error_type="validation_error"
            )

        # ObjectId 변환 예외 처리
        try:
            object_id = ObjectId(image_id)
        except InvalidId:
            return handle_exception(
                Exception("유효하지 않은 이미지 ID 형식입니다"),
                error_type="validation_error"
            )

        # DB 업데이트
        result = db.images.update_one(
            {'_id': object_id},
            {
                '$set': {
                    'inspection_status': new_status,
                    'inspection_updated_at': datetime.utcnow()
                }
            }
        )

        # 업데이트 결과 확인
        if result.matched_count == 0:
            return handle_exception(
                Exception("이미지를 찾을 수 없습니다"),
                error_type="not_found"
            )

        # 수정된 이미지 정보 조회
        updated_image = db.images.find_one({'_id': object_id}, {'inspection_status': 1, '_id': 1})

        return standard_response(
            "검사 상태가 업데이트되었습니다",
            data={"image_id": str(updated_image['_id']), "inspection_status": updated_image['inspection_status']}
        )

    except Exception as e:
        return handle_exception(e, error_type="db_error")