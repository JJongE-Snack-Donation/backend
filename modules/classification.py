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
import traceback
classification_bp = Blueprint('classification', __name__)

def generate_image_url(thumbnail_path):  # 매개변수명 수정
    """
    Generate a URL for the given thumbnail path.
    """
    if not thumbnail_path:
        # thumbnail_path가 None 또는 빈 문자열인 경우 기본값 반환
        return None

    # 경로 정규화
    thumbnail_path = os.path.normpath(thumbnail_path)
    base_path = os.path.normpath(r"C:\Users\User\Documents\backend\mnt")

    if thumbnail_path.startswith(base_path):
        relative_path = thumbnail_path[len(base_path):].lstrip(os.sep)
    else:
        logging.error(f"Unexpected thumbnail path format: {thumbnail_path}")
        return None

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

        # 이미지 데이터 처리
        processed_images = []
        for image in images:
            # ObjectId를 문자열로 변환
            image['_id'] = str(image['_id'])
            
            # 썸네일 경로를 URL로 변환
            if 'ThumnailPath' in image:
                image['ThumnailPath'] = generate_image_url(image['ThumnailPath'])
            
            # 원본 이미지 경로를 URL로 변환
            if 'FilePath' in image:
                image['FilePath'] = generate_image_url(image['FilePath'])
                
            processed_images.append(image)

        return standard_response(
            "검수 완료된 이미지 목록 조회 성공",
            data={'images': processed_images},
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
    try:
        logger.info(f"\n=== 이미지 상세 정보 조회 시작: {image_id} ===")

        # 1️⃣ 현재 요청된 이미지 정보를 가져옴
        try:
            object_id = ObjectId(image_id)
        except Exception as e:
            logger.error(f"ObjectId 변환 실패: {str(e)}")
            return jsonify({'message': 'Invalid image ID'}), 400

        image_doc = db.images.find_one({"_id": object_id})

        if not image_doc:
            logger.warning(f"이미지를 찾을 수 없음: {image_id}")
            return jsonify({'message': 'Classified image not found'}), 404

        # 2️⃣ 프로젝트 ID 및 evtnum 정보 가져오기
        project_id = image_doc.get("ProjectInfo", {}).get("ID")
        evtnum = image_doc.get("evtnum")

        if not project_id:
            logger.warning(f"이미지 {image_id}에 프로젝트 정보가 없습니다.")
            return jsonify({'message': 'Project ID is missing'}), 400

        try:
            evtnum = int(evtnum)
        except ValueError:
            logger.error(f"evtnum 값 변환 오류: {evtnum}")
            return jsonify({'message': 'Invalid evtnum format'}), 400

        logger.info(f"요청된 이미지 프로젝트 ID: {project_id}, evtnum: {evtnum}")

        # 3️⃣ 같은 프로젝트 내에서 같은 evtnum을 가진 이미지 가져오기
        query_filter = {
            "evtnum": evtnum,
            "ProjectInfo.ID": project_id
        }

        related_images = list(db.images.find(query_filter))

        # 4️⃣ detect_images에서 종명, 개체수, 정확도 가져오기
        detect_query = {"Image_id": image_doc["_id"]}
        logger.info(f"\n=== detect_images 검색 시작 ===")
        logger.info(f"검색 조건: {detect_query}")

        detection_data = db.detect_images.find_one(
            detect_query,
            sort=[("UpdatedAt", -1)]
        )

        # 5️⃣ 기존 응답 구조 유지 + 개선된 필드 적용
        response_data = {
            "_id": str(image_doc["_id"]),
            "FileName": image_doc.get("FileName", ""),
            "FilePath": image_doc.get("FilePath", ""),
            "ThumnailPath": image_doc.get("ThumnailPath", ""),
            "ProjectInfo": image_doc.get("ProjectInfo", {}),
            "DateTimeOriginal": image_doc.get("DateTimeOriginal", {}),
            "UploadDate": image_doc.get("UploadDate", ""),
            "Latitude": image_doc.get("Latitude", "No Data"),
            "Longitude": image_doc.get("Longitude", "No Data"),
            "SerialNumber": image_doc.get("SerialNumber", "UNKNOWN"),
            "evtnum": image_doc.get("evtnum", ""),
            "AI_processed": image_doc.get("AI_processed", False),
            "is_classified": image_doc.get("is_classified", False),
            "inspection_status": image_doc.get("inspection_status", ""),
            "inspection_complete": image_doc.get("inspection_complete", False),
            "exception_status": image_doc.get("exception_status", ""),
            "exception_comment": image_doc.get("exception_comment", ""),
            "is_favorite": image_doc.get("is_favorite", False),

            # 🔹 `bbox` & `new_bbox`를 `detect_images`에서 가져옴
            "bbox": detection_data.get("bbox", []) if detection_data else [],
            "new_bbox": detection_data.get("new_bbox", []) if detection_data else [],

            # 🔹 `speciesName`을 `BestClass`와 동일하게 설정
            "speciesName": detection_data.get("BestClass", "미확인") if detection_data else "미확인",

            # 🔹 종명, 개체수, 정확도 추가
            "BestClass": detection_data.get("BestClass", "No Data") if detection_data else "No Data",
            "Count": detection_data.get("Count", "No Data") if detection_data else "No Data",
            "Accuracy": detection_data.get("Accuracy", "No Data") if detection_data else "No Data",

            # 🔹 같은 프로젝트 내 evtnum이 동일한 이미지 리스트 반환
            "related_images": [
                {
                    "id": str(img["_id"]),
                    "FileName": img.get("FileName", ""),
                    "ThumnailPath": img.get("ThumnailPath", ""),
                    "ProjectInfo": img.get("ProjectInfo", {}),
                    "evtnum": img.get("evtnum", "")
                }
                for img in related_images
            ]
        }

        logger.info("\n=== 이미지 상세 정보 조회 완료 ===")
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"\n=== 오류 발생 ===")
        logger.error(f"이미지 상세 정보 조회 중 오류: {str(e)}", exc_info=True)
        return jsonify({'message': 'Error fetching image details', 'error': str(e)}), 500

@classification_bp.route('/unclassified-images/<image_id>', methods=['GET'])
@jwt_required()
def get_unclassified_image_details(image_id):
    """
    예외검수 이미지 상세 정보 조회 API
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        # ObjectId 변환 시도
        try:
            print(f"Received image_id: {image_id}")
            object_id = ObjectId(image_id)
            print(f"Converted to ObjectId: {object_id}")
        except Exception as e:
            print(f"ObjectId conversion failed: {e}")
            return jsonify({"status": 400, "message": "Invalid image ID format"}), 400

        # ✅ 일반검수 API와 동일한 query_filter 적용
        query_filter = {"_id": object_id} if object_id else {"Image_id": image_id}

        # images 컬렉션에서 해당 이미지 찾기 + detect_images 조인
        result = db.images.aggregate([
            {"$match": query_filter},  # ObjectId 조회 또는 Image_id 조회
            {
                "$lookup": {
                    "from": "detect_images",
                    "let": { "imageId": "$_id" },
                    "pipeline": [
                        { "$match": { "$expr": { "$eq": ["$Image_id", "$$imageId"] } } } 
                    ],
                    "as": "detection_data"
                }
            },
            {"$unwind": {"path": "$detection_data", "preserveNullAndEmptyArrays": True}},
            {
                "$addFields": {
                    "BestClass": { "$ifNull": ["$detection_data.BestClass", "미확인"] },  # ✅ 일반검수 API와 동일한 기본값 적용
                    "species": { "$ifNull": ["$detection_data.BestClass", "미확인"] },
                    "AI_processed": { "$ifNull": ["$detection_data.AI_processed", False] }
                }
            },
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
                    "BestClass": 1,
                    "Accuracy": {"$ifNull": ["$detection_data.Accuracy", 0]},
                    "Count": {"$ifNull": ["$detection_data.Count", 0]},
                    "AI_processed": 1,
                    "species": 1,
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
        print(f"Query result: {image_data}")

        if not image_data:
            return jsonify({
                "status": 404,
                "message": "Unclassified image not found"
            }), 404

        return jsonify(image_data[0]), 200

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
    분류된 이미지 삭제 API - images와 detect_images 컬렉션에서 모두 삭제
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        
        # 1. images 컬렉션에서 이미지 정보 조회
        image = db.images.find_one({"_id": object_id})
        if not image:
            return jsonify({'message': 'Image not found'}), 404

        # 2. 실제 파일 삭제
        file_deleted = True
        for path in [image.get('FilePath'), image.get('ThumnailPath')]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete file {path}: {str(e)}")
                    file_deleted = False

        # 3. detect_images 컬렉션에서 삭제
        detect_result = db.detect_images.delete_many({
            "Image_id": object_id,
            "ProjectInfo.ID": image["ProjectInfo"]["ID"]
        })
        
        # 4. images 컬렉션에서 삭제
        image_result = db.images.delete_one({"_id": object_id})

        # 결과 반환
        if image_result.deleted_count > 0:
            response_message = "이미지가 성공적으로 삭제되었습니다."
            if not file_deleted:
                response_message += " (실제 파일 삭제 실패)"
            
            return jsonify({
                'message': response_message,
                'details': {
                    'images_deleted': image_result.deleted_count,
                    'detect_images_deleted': detect_result.deleted_count,
                    'files_deleted': file_deleted
                }
            }), 200
        else:
            return jsonify({'message': '이미지 삭제 실패'}), 500

    except Exception as e:
        logger.error(f"Image deletion error: {str(e)}")
        return jsonify({
            'message': 'Invalid image ID format or other error', 
            'error': str(e)
        }), 400

@classification_bp.route('/unclassified-images/<image_id>', methods=['DELETE'])
@jwt_required()
def delete_unclassified_image_endpoint(image_id):
    """
    미분류 이미지 삭제 API - images와 detect_images 컬렉션에서 모두 삭제
    Parameters:
    - image_id: MongoDB _id (ObjectId)
    """
    try:
        object_id = ObjectId(image_id)
        
        # 1. images 컬렉션에서 미분류 이미지 정보 조회
        image = db.images.find_one({
            "_id": object_id,
            "is_classified": False  # 미분류 이미지 확인
        })
        
        if not image:
            return jsonify({'message': '미분류 이미지를 찾을 수 없습니다'}), 404

        # 2. 실제 파일 삭제
        file_deleted = True
        for path in [image.get('FilePath'), image.get('ThumnailPath')]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete file {path}: {str(e)}")
                    file_deleted = False

        # 3. detect_images 컬렉션에서 삭제
        detect_result = db.detect_images.delete_many({
            "Image_id": object_id,
            "ProjectInfo.ID": image["ProjectInfo"]["ID"]
        })
        
        # 4. images 컬렉션에서 삭제
        image_result = db.images.delete_one({"_id": object_id})

        # 결과 반환
        if image_result.deleted_count > 0:
            response_message = "미분류 이미지가 성공적으로 삭제되었습니다."
            if not file_deleted:
                response_message += " (실제 파일 삭제 실패)"
            
            return jsonify({
                'message': response_message,
                'details': {
                    'images_deleted': image_result.deleted_count,
                    'detect_images_deleted': detect_result.deleted_count,
                    'files_deleted': file_deleted
                }
            }), 200
        else:
            return jsonify({'message': '이미지 삭제 실패'}), 500

    except Exception as e:
        logger.error(f"Unclassified image deletion error: {str(e)}")
        return jsonify({
            'message': 'Invalid image ID format or other error', 
            'error': str(e)
        }), 400
    

@classification_bp.route('/classified-images/<image_id>', methods=['PUT'])
@jwt_required()
def update_classified_image_endpoint(image_id):
    """
    분류된 이미지 정보 수정 API - images와 detect_images 컬렉션 모두 업데이트
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
            return jsonify({'message': '필수 필드가 누락되었습니다 (count, best_class)'}), 400

        # 1. 먼저 이미지 정보 조회 (ProjectInfo.ID 필요)
        image = db.images.find_one({'_id': object_id})
        if not image:
            return jsonify({'message': '이미지를 찾을 수 없습니다'}), 404

        update_fields = {
            'Count': update_data['count'],
            'BestClass': update_data['best_class']
        }

        # 2. images 컬렉션 업데이트
        images_result = db.images.update_one(
            {'_id': object_id},
            {'$set': update_fields}
        )

        # 3. detect_images 컬렉션 업데이트
        detect_result = db.detect_images.update_one(
            {
                'Image_id': object_id,
                'ProjectInfo.ID': image['ProjectInfo']['ID']
            },
            {'$set': update_fields}
        )

        # 업데이트 결과 확인
        if images_result.matched_count == 0:
            return jsonify({'message': '이미지를 찾을 수 없습니다'}), 404

        return jsonify({
            'message': '이미지 정보가 성공적으로 업데이트되었습니다',
            'details': {
                'images_updated': images_result.modified_count > 0,
                'detect_images_updated': detect_result.modified_count > 0
            }
        }), 200

    except Exception as e:
        logger.error(f"Image update error: {str(e)}")
        return jsonify({
            'message': 'Invalid image ID format or other error', 
            'error': str(e)
        }), 400

@classification_bp.route('/unclassified-images/<image_id>', methods=['PUT'])
@jwt_required()
def update_unclassified_image_endpoint(image_id):
    """
    미분류 이미지 정보 수정 API - images와 detect_images 컬렉션 모두 업데이트
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
        required_fields = ['best_class', 'status', 'object_counts']
        if not all(field in update_data for field in required_fields):
            return jsonify({'message': '필수 필드가 누락되었습니다 (best_class, status, object_counts)'}), 400

        # 1. 먼저 이미지 정보 조회 (ProjectInfo.ID 필요)
        image = db.images.find_one({
            '_id': object_id,
            'is_classified': False  # 미분류 이미지 확인
        })
        
        if not image:
            return jsonify({'message': '미분류 이미지를 찾을 수 없습니다'}), 404

        update_fields = {
            'BestClass': update_data['best_class'],
            'Status': update_data['status'],
            'ObjectCounts': update_data['object_counts'],
            'UpdatedAt': datetime.utcnow()
        }

        # 2. images 컬렉션 업데이트
        images_result = db.images.update_one(
            {'_id': object_id},
            {'$set': update_fields}
        )

        # 3. detect_images 컬렉션 업데이트
        detect_result = db.detect_images.update_one(
            {
                'Image_id': object_id,
                'ProjectInfo.ID': image['ProjectInfo']['ID']
            },
            {'$set': update_fields}
        )

        # 업데이트 결과 반환
        if images_result.matched_count == 0:
            return jsonify({'message': '이미지를 찾을 수 없습니다'}), 404

        return jsonify({
            'message': '미분류 이미지 정보가 성공적으로 업데이트되었습니다',
            'details': {
                'images_updated': images_result.modified_count > 0,
                'detect_images_updated': detect_result.modified_count > 0,
                'updated_fields': update_fields
            }
        }), 200

    except Exception as e:
        logger.error(f"Unclassified image update error: {str(e)}")
        return jsonify({
            'message': 'Invalid image ID format or other error', 
            'error': str(e)
        }), 400

@classification_bp.route('/images/<image_id>', methods=['GET'])
@jwt_required()
def get_image_detail(image_id):
    """검수 완료된 이미지 상세 정보 조회 API"""
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
                    "let": { "imageId": "$_id" },  # 변환 없이 ObjectId 그대로 사용
                    "pipeline": [
                        { "$match": { "$expr": { "$eq": ["$Image_id", "$$imageId"] } } } 
                    ],
                    "as": "detection_data"
                }
            },
            {"$unwind": {"path": "$detection_data", "preserveNullAndEmptyArrays": True}},  # preserveNullAndEmptyArrays=True 유지
            {
                "$addFields": {
                    "BestClass": { "$ifNull": ["$detection_data.BestClass", "미확인"] },  # BestClass 기본값 설정
                    "species": { "$ifNull": ["$detection_data.BestClass", "미확인"] },  # species를 detection_data.BestClass 기반으로 설정
                    "AI_processed": { "$ifNull": ["$detection_data.AI_processed", "$AI_processed"] }  # AI 처리 여부 추가
                }
            },
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
                    "BestClass": 1,  # addFields에서 설정한 값
                    "Accuracy": {"$ifNull": ["$detection_data.Accuracy", 0]},
                    "Count": {"$ifNull": ["$detection_data.Count", 0]},
                    "species": 1,  # addFields에서 설정한 값 사용
                    "AI_processed": 1,  # AI 처리 여부 포함
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
        print(image_data)  # aggregate 결과 확인

        if not image_data:
            return jsonify({'message': '검수 완료된 이미지를 찾을 수 없음'}), 404

        return jsonify(image_data[0]), 200

    except Exception as e:
        return jsonify({'message': 'Invalid image ID format or other error', 'error': str(e)}), 400


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
    try:
        logger.info("=== 일반검수 이미지 목록 조회 시작 ===")
        
        project_id = request.args.get('project_id')
        evtnum = request.args.get('evtnum')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 1000))

        logger.info(f"요청 파라미터: project_id={project_id}, evtnum={evtnum}")

        # 기본 쿼리 조건
        query = {
            'is_classified': True, 
            'inspection_complete': False
        }

        # ✅ evtnum이 있는 경우, project_id가 없어도 전체에서 검색 가능하도록 허용
        if evtnum:
            try:
                evtnum_int = int(evtnum)
                query['evtnum'] = evtnum_int

                if project_id:  # 특정 프로젝트 내 evtnum 검색
                    query['ProjectInfo.ID'] = project_id
                    logger.info(f"프로젝트 {project_id}의 이벤트 {evtnum} 조회")
                else:
                    logger.info(f"⚠️ 전체 프로젝트에서 이벤트 {evtnum} 조회")
                    
            except ValueError:
                return jsonify({"status": 400, "message": "evtnum 값이 올바르지 않습니다."}), 400

        elif project_id:  # 프로젝트 ID만 있을 때
            query['ProjectInfo.ID'] = project_id
            logger.info(f"프로젝트 {project_id}의 모든 이미지 조회")

        logger.info(f"최종 검색 조건: {query}")

        # ✅ evtnum과 project_id를 함께 그룹핑하여, 프로젝트가 다른 경우 evtnum이 같아도 다른 그룹이 되도록 함
        pipeline = [
            {"$match": query},
            {"$sort": {"evtnum": 1, "FileName": 1}},  # evtnum으로 먼저 정렬하고, 같은 evtnum 내에서는 파일명으로 정렬
            {"$group": {
                "_id": {"evtnum": "$evtnum", "project_id": "$ProjectInfo.ID"},  # ✅ 프로젝트 ID도 포함하여 그룹화
                "images": {"$push": "$$ROOT"},  # 각 그룹의 모든 문서 저장
                "count": {"$sum": 1}  # 각 그룹의 이미지 수 계산
            }},
            {"$sort": {"_id.evtnum": 1}},  # 그룹(evtnum)을 오름차순으로 정렬
            {"$skip": (page - 1) * per_page},
            {"$limit": per_page}
        ]

        # Aggregation 실행
        grouped_results = list(db.images.aggregate(pipeline))
        
        # 전체 문서 수 계산
        total = db.images.count_documents(query)
        
        # 결과 포맷팅
        result_images = []
        for group in grouped_results:
            for img in group['images']:
                # ✅ detect_images에서 해당 이미지의 종 정보를 가져옴
                detect_query = {"Image_id": img["_id"]}
                detection_data = db.detect_images.find_one(
                    detect_query,
                    sort=[("UpdatedAt", -1)]  # 최신 데이터 가져오기
                )

                species_name = "미확인"
                bbox_data = []
                new_bbox_data = []

                if detection_data:
                    species_name = detection_data.get("BestClass", "미확인")

                    # ✅ Infos 배열이 있고, 최소 한 개의 요소가 있을 경우 bbox 값 가져오기
                    infos = detection_data.get("Infos", [])
                    if infos and isinstance(infos, list) and len(infos) > 0:
                        bbox_data = infos[0].get("bbox", [])  # ✅ Infos[0] 내부의 bbox 추출
                        new_bbox_data = infos[0].get("new_bbox", [])

                result_images.append({
                    "imageId": str(img['_id']),
                    "fileName": img.get('FileName', ''),
                    "imageUrl": generate_image_url(img.get('ThumnailPath')),
                    "uploadDate": img.get('DateTimeOriginal', {}).get('$date', ''),
                    "projectId": img.get('ProjectInfo', {}).get('ID', ''),
                    "projectName": img.get('ProjectInfo', {}).get('ProjectName', ''),
                    "serialNumber": img.get('SerialNumber', ''),
                    "speciesName": species_name,  # ✅ AI 분석된 종 정보 반영
                    "evtnum": img.get('evtnum', ''),
                    "exception_status": img.get('exception_status', ''),
                    "bbox": bbox_data,  # ✅ Infos[0]에서 가져온 bbox
                    "new_bbox": new_bbox_data,  # ✅ Infos[0]에서 가져온 new_bbox
                })


        logger.info(f"\n=== 조회 결과 요약 ===")
        logger.info(f"총 이미지 수: {total}")
        logger.info(f"현재 페이지: {page}")
        logger.info(f"페이지당 이미지 수: {per_page}")
        logger.info(f"처리된 이미지 수: {len(result_images)}")

        return jsonify({
            "status": 200,
            "message": "일반 검수 이미지 조회 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "images": result_images
        }), 200

    except Exception as e:
        logger.error(f"🚨 서버 오류 발생: {str(e)}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": f"서버 오류 발생: {str(e)}"
        }), 500

@classification_bp.route('/inspection/exception', methods=['GET'])
@jwt_required()
def get_exception_inspection_images():
    """
    예외검수(미분류) 이미지 조회 API
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
        per_page = int(request.args.get('per_page', 1000))

        # 기본 쿼리 조건 (미분류된 이미지만 조회)
        query = {'is_classified': False, 'inspection_complete': False}

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
        
        # 이벤트 번호 필터 (프로젝트 ID와 함께 조회)
        if evtnum:
            query['evtnum'] = int(evtnum)
            if project_id:
                query['ProjectInfo.ID'] = project_id

        # 이미지 조회
        total = db.images.count_documents(query)
        images = list(db.images.find(query, {
            '_id': 1,
            'FileName': 1,
            'ThumnailPath': 1,
            'DateTimeOriginal': 1,
            'ProjectInfo.ID': 1,
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
                "fileName": img.get('FileName', 'No Data'),
                "imageUrl": generate_image_url(img.get('ThumnailPath')),
                "uploadDate": img.get('DateTimeOriginal', '0000-00-00T00:00:00Z'),
                "projectId": img.get('ProjectInfo', {}).get('ID', ''),
                "projectName": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "serialNumber": img.get('SerialNumber', ''),
                "exceptionStatus": img.get('exception_status', 'pending'),
                "evtnum": img.get('evtnum', '')
            } for img in images]
        }), 200

    except Exception as e:
        print("예외 발생:", str(e))
        traceback.print_exc()
        return handle_exception(e, error_type="db_error")

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

        # 수정 시 자동으로 is_classified=True 설정
        update_dict['is_classified'] = True

        # 디버깅용 출력
        print(f"수정할 이미지 ID 목록: {image_ids}")
        print(f"변환된 ObjectId 목록: {object_ids}")
        print(f"적용할 업데이트 값: {update_dict}")

        # 다중 이미지 업데이트
        result = db.images.update_many(
            {'_id': {'$in': object_ids}},  #is_classified 조건 없이 업데이트 실행
            {'$set': update_dict}
        )

        print(f"수정된 문서 개수: {result.modified_count}")

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
        print(f"Received image_ids: {image_ids}")

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