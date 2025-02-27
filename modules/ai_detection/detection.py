from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from threading import Thread
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator
import cv2
import numpy as np
import os
from bson import ObjectId
from bson.binary import Binary
from datetime import datetime
from typing import Dict, List, Any

from ..database import db
from ..utils.response import standard_response, handle_exception
from ..utils.constants import AI_MODEL_PATH, CONFIDENCE_THRESHOLD

detection_bp = Blueprint('detection', __name__)

# YOLOv8 모델 로드
model = YOLO(AI_MODEL_PATH)

def add_object_counts(detections, model) -> Dict[str, int]:
    """객체 카운트 집계"""
    object_counts = {'deer': 0, 'pig': 0, 'racoon': 0}

    for detection in detections.boxes.data:
        _, _, _, _, confidence, class_id = detection
        if confidence >= CONFIDENCE_THRESHOLD:  # 80% 이상의 확률만 처리
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

        detection_results = []
        object_counts = add_object_counts(detections, model)
        valid_detections = 0

        for detection in detections.boxes.data.tolist():
            x1, y1, x2, y2, confidence, class_id = detection
            if confidence >= CONFIDENCE_THRESHOLD:  # 80% 이상의 확률만 처리
                valid_detections += 1
                class_name = model.names[int(class_id)]
                detection_results.append({
                    'best_class': class_name,  # 추가
                    'best_probability': float(confidence * 100),  # << 여기에 정확도 저장
                    'name': class_name,
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'new_bbox': [float(x1), float(y1), float(x2), float(y2)]  # 임시로 원본 bbox 유지
                })
                annotator.box_label([x1, y1, x2, y2], label=class_name, color=(255, 0, 0))

        # RGB에서 BGR로 변환
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        # 결과 이미지를 바이너리 데이터로 변환
        _, img_encoded = cv2.imencode('.jpg', img_bgr)
        result_image = Binary(img_encoded.tobytes())

        return {
            'status': 'Success' if valid_detections > 0 else 'Failed',
            'image_id': image_id,
            'result_image': result_image,
            'detections': detection_results,
            'object_counts': object_counts,
            'reason': 'No objects detected' if valid_detections == 0 else None
        }
        
    except Exception as e:
        return {
            'status': 'Failed',
            'image_id': image_id,
            'error': str(e)
        }

@detection_bp.route('/detect', methods=['POST'])
@jwt_required()
def detect_objects():
    """객체 검출 API"""
    try:
        image_ids = request.json.get('image_ids', [])
        if not image_ids:
            return handle_exception(Exception("이미지 ID가 필요합니다"), error_type="validation_error")

        total_images = len(image_ids)

        # AI 분석 시작 (50%)
        db.progress.update_one(
            {'_id': 'ai_progress'},
            {'$set': {'progress': 50, 'total_images': total_images, 'processed_images': 0}},
            upsert=True
        )

        results = []

        def background_process(image_ids):
            processed_count = 0

            for image_id in image_ids:
                image_doc = db.images.find_one({'_id': ObjectId(image_id)})
                if not image_doc:
                    continue

                # MongoDB에서 이미지 파일 경로 조회
                file_path = image_doc.get('FilePath')
                if not file_path or not os.path.exists(file_path):
                    db.failed_results.insert_one({
                        'Image_id': image_id,
                        'Status': 'Failed',
                        'Reason': 'File not found',
                        'Timestamp': datetime.utcnow()
                    })
                    continue

                with open(file_path, 'rb') as f:
                    image_data = f.read()

                detection_result = process_detection(image_data, str(image_id))
                results.append(detection_result)

                update_data = {
                    'Infos': detection_result['detections'],  # << best_probability 포함됨
                    'Count': sum(detection_result['object_counts'].values()),
                    'Accuracy': max((d['best_probability'] for d in detection_result['detections']), default=0),  # 최고 정확도
                    'AI_processed': True,
                    'AI_process_date': datetime.utcnow(),
                    'detection_image': detection_result['result_image'],
                    'is_classified': bool(detection_result['detections'])
                }

                if detection_result['detections']:
                    update_data['BestClass'] = detection_result['detections'][0]['best_class']  # << 최고 확률 객체 저장
                    db.detect_images.update_one({'Image_id': ObjectId(image_id)}, {'$set': update_data}, upsert=True)


                    # images 컬렉션에도 is_classified 업데이트 추가
                    db.images.update_one({'_id': ObjectId(image_id)}, {'$set': {'is_classified': True}})
                else:
                    db.failed_results.insert_one({
                        'Image_id': image_id,
                        'Status': 'Failed',
                        'Reason': 'No objects detected',
                        'Timestamp': datetime.utcnow()
                    })

                    # 객체 검출 실패 시 images 컬렉션에도 is_classified를 False로 설정
                    db.images.update_one({'_id': ObjectId(image_id)}, {'$set': {'is_classified': False}})

                processed_count += 1

                # 진행률 업데이트
                progress_percentage = 50 + (processed_count / total_images * 50)
                db.progress.update_one(
                    {'_id': 'ai_progress'},
                    {'$set': {'progress': round(progress_percentage, 2), 'processed_images': processed_count}}
                )

            # AI 분석 완료 (100%)
            db.progress.update_one(
                {'_id': 'ai_progress'},
                {'$set': {'progress': 100, 'processed_images': processed_count}}
            )

        # 백그라운드 스레드 실행
        Thread(target=background_process, args=(image_ids,)).start()

        return jsonify({
            "message": "객체 검출이 진행 중입니다",
            "progress": 50,
            "total_images": total_images,
            "detections": [
                {
                    "image_id": result["image_id"],
                    "detections": result["detections"],
                    "object_counts": result["object_counts"]
                }
                for result in results
            ] if results else []
        }), 202  

    except Exception as e:
        return handle_exception(e, error_type="ai_error")

@detection_bp.route('/status/ai-progress', methods=['GET'])
@jwt_required()
def get_ai_progress():
    """AI 분석 진행 상태 조회 API"""
    try:
        progress = db.progress.find_one({'_id': 'ai_progress'}, {'_id': 0})
        return jsonify(progress if progress else {"progress": 0, "total_images": 0, "processed_images": 0})

    except Exception as e:
        return handle_exception(e, error_type="db_error")
