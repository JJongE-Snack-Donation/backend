'''
from flask import Blueprint, request
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator
import cv2
import numpy as np
from bson import ObjectId
from bson.binary import Binary
from datetime import datetime
from typing import Dict, List, Tuple, Any

from ..database import db
from ..utils.response import standard_response, handle_exception
from ..utils.constants import (
    AI_MODEL_PATH,
    CONFIDENCE_THRESHOLD,
    VALID_SPECIES,
    VALID_INSPECTION_STATUSES
)

detection_bp = Blueprint('detection', __name__)

# YOLOv8 모델 로드
model = YOLO(AI_MODEL_PATH)

def add_object_counts(detections, model) -> Dict[str, int]:
    """객체 카운트 집계"""
    object_counts = {species: 0 for species in VALID_SPECIES}
    
    for detection in detections.boxes.data:
        _, _, _, _, confidence, class_id = detection
        if confidence >= CONFIDENCE_THRESHOLD:
            class_name = model.names[int(class_id)]
            if class_name in object_counts:
                object_counts[class_name] += 1
                
    return object_counts

def process_detection(image_data: bytes, image_id: str) -> Dict:
    """이미지 객체 검출 처리"""
    try:
        # 이미지 데이터를 numpy 배열로 변환
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return {
                'status': 'Failed',
                'image_id': image_id,
                'error': '이미지 디코딩 실패'
            }
        
        # 객체 검출 수행
        detections = model(image)[0]
        
        # 결과 이미지 생성
        img = image.copy()
        annotator = Annotator(img)
        
        for box in detections.boxes:
            b = box.xyxy[0]
            annotator.box_label(b.tolist(), color=(255, 0, 0))
            
        # RGB에서 BGR로 변환
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        # 결과 이미지를 바이너리 데이터로 변환
        _, img_encoded = cv2.imencode('.jpg', img_bgr)
        result_image = Binary(img_encoded.tobytes())
        
        # 객체 카운트 및 검출 결과
        object_counts = add_object_counts(detections, model)
        detection_results = []
        
        for detection in detections.boxes.data.tolist():
            x1, y1, x2, y2, confidence, class_id = detection
            if confidence >= CONFIDENCE_THRESHOLD:
                class_name = model.names[int(class_id)]
                detection_results.append({
                    'class': class_name,
                    'confidence': float(confidence * 100),
                    'bbox': [float(x1), float(y1), float(x2), float(y2)]
                })
                
        return {
            'status': 'Success' if detection_results else 'Failed',
            'image_id': image_id,
            'result_image': result_image,
            'detections': detection_results,
            'object_counts': object_counts,
            'reason': 'No valid detections' if not detection_results else None
        }
        
    except Exception as e:
        return {
            'status': 'Failed',
            'image_id': image_id,
            'error': str(e)
        }

@detection_bp.route('/detect', methods=['POST'])
def detect_objects():
    """객체 검출 API"""
    try:
        image_ids = request.json.get('image_ids', [])
        if not image_ids:
            return handle_exception(
                Exception("이미지 ID가 필요합니다"),
                error_type="validation_error"
            )
            
        results = []
        processed_count = 0
        
        for image_id in image_ids:
            # 원본 이미지 조회
            image_doc = db.images.find_one({'_id': ObjectId(image_id)})
            if not image_doc:
                continue
                
            # 객체 검출 수행
            detection_result = process_detection(
                image_doc['data'],
                str(image_id)
            )
            
            # 결과 저장
            if detection_result['status'] == 'Success':
                # 이미지 컬렉션 업데이트
                db.images.update_one(
                    {'_id': ObjectId(image_id)},
                    {
                        '$set': {
                            'Infos': detection_result['detections'],
                            'Count': sum(detection_result['object_counts'].values()),
                            'BestClass': detection_result['detections'][0]['class'] if detection_result['detections'] else None,
                            'Accuracy': detection_result['detections'][0]['confidence'] if detection_result['detections'] else 0,
                            'AI_processed': True,
                            'AI_process_date': datetime.utcnow(),
                            'detection_image': detection_result['result_image']
                        }
                    }
                )
                processed_count += 1
                
            results.append(detection_result)
            
        return standard_response(
            "객체 검출이 완료되었습니다",
            data={
                'processed_count': processed_count,
                'total_count': len(image_ids),
                'results': results
            }
        )
        
    except Exception as e:
        return handle_exception(e, error_type="ai_error")

@detection_bp.route('/image/<image_id>', methods=['GET'])
def get_image_for_inspection(image_id: str) -> Tuple[Dict[str, Any], int]:
    """분류된 이미지 검토를 위한 상세 정보 조회"""
    try:
        # ObjectId 변환
        object_id = ObjectId(image_id)
        
        # 이미지 조회
        image = db.images.find_one({'_id': object_id, 'AI_processed': True})
        if not image:
            return handle_exception(
                Exception("AI 처리된 이미지를 찾을 수 없습니다"),
                error_type="validation_error"
            )
            
        # 검토용 응답 데이터 구성
        response_data = {
            'ImageDatas': {
                '_id': str(image['_id']),
                'FileName': image.get('FileName'),
                'FilePath': image.get('FilePath'),
                'ThumnailPath': image.get('ThumnailPath'),
                'SerialNumber': image.get('SerialNumber'),
                'UserLabel': image.get('UserLabel'),
                'DateTimeOriginal': image.get('DateTimeOriginal'),
                'BestClass': image.get('BestClass'),
                'Count': image.get('Count'),
                'Accuracy': image.get('Accuracy'),
                'inspection_status': image.get('inspection_status', 'pending')
            }
        }
            
        return standard_response(
            "이미지 조회 성공",
            data=response_data
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@detection_bp.route('/image/<image_id>/status', methods=['PUT'])
def update_inspection_status(image_id: str) -> Tuple[Dict[str, Any], int]:
    """검사 상태 업데이트 API"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status or new_status not in VALID_INSPECTION_STATUSES:
            return handle_exception(
                Exception("유효하지 않은 검사 상태입니다"),
                error_type="validation_error"
            )
            
        result = db.images.update_one(
            {'_id': ObjectId(image_id)},
            {
                '$set': {
                    'inspection_status': new_status,
                    'inspection_updated_at': datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            return handle_exception(
                Exception("이미지를 찾을 수 없습니다"),
                error_type="validation_error"
            )
            
        return standard_response("검사 상태가 업데이트되었습니다")
        
    except Exception as e:
        return handle_exception(e, error_type="db_error") '''