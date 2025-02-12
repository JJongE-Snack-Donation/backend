from flask import Blueprint, Response, stream_with_context
from flask_jwt_extended import jwt_required
from typing import Tuple, Dict, Any, List
from datetime import datetime, timedelta

from .database import db
from .utils.response import standard_response, handle_exception
from .utils.constants import MESSAGES
import json
import time

status_bp = Blueprint('status', __name__)

def generate_status_updates():
    """실시간 상태 업데이트 생성기"""
    try:
        while True:
            # 상태 데이터 생성
            total_images = db.images.count_documents({})
            classified_images = db.images.count_documents({'is_classified': True})
            unclassified_images = db.images.count_documents({'is_classified': False})
            progress_percentage = (classified_images / total_images * 100) if total_images > 0 else 0

            status_data = {
                "total_images": total_images,
                "classified_images": classified_images,
                "unclassified_images": unclassified_images,
                "progress_percentage": round(progress_percentage, 2)
            }

            yield f"data: {json.dumps(status_data)}\n\n"
            time.sleep(3)

    except GeneratorExit:
        print("Client disconnected, stopping status updates.")
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        time.sleep(5)


@status_bp.route('/status/summary', methods=['GET'])
@jwt_required()
def get_status_summary() -> Tuple[Dict[str, Any], int]:
    """시스템 상태 요약 API"""
    try:
        # 전체 이미지 수
        total_images = db.images.count_documents({})
        
        # 분류된/미분류 이미지 수
        classified_images = db.images.count_documents({'is_classified': True})
        unclassified_images = db.images.count_documents({'is_classified': False})
        
        # 검토 상태별 이미지 수
        inspection_status_counts: Dict[str, int] = {}
        inspection_pipeline = [
            {
                '$group': {
                    '_id': '$inspection_status',
                    'count': {'$sum': 1}
                }
            }
        ]
        for status in db.images.aggregate(inspection_pipeline):
            inspection_status_counts[status['_id'] or 'pending'] = status['count']
            
        # 최근 24시간 동안의 활동
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_activities = {
            'classifications': db.images.count_documents({
                'classification_date': {'$gte': yesterday}
            }),
            'inspections': db.images.count_documents({
                'inspection_date': {'$gte': yesterday}
            })
        }
        
        # 프로젝트 통계
        project_stats: List[Dict[str, Any]] = []
        projects = db.projects.find()
        
        for project in projects:
            project_id = project['_id']
            stats = {
                'project_name': project['project_name'],
                'total_images': db.images.count_documents({
                    'ProjectInfo.ID': str(project_id)
                }),
                'classified_images': db.images.count_documents({
                    'ProjectInfo.ID': str(project_id),
                    'is_classified': True
                })
            }
            project_stats.append(stats)
            
        return standard_response(
            "시스템 상태 요약 조회 성공",
            data={
                'total_images': total_images,
                'classified_images': classified_images,
                'unclassified_images': unclassified_images,
                'inspection_status': inspection_status_counts,
                'recent_activities': recent_activities,
                'project_stats': project_stats
            }
        )
        
    except Exception as e:
        return handle_exception(e, error_type="db_error")

@status_bp.route('/status/health', methods=['GET'])
@jwt_required()
def health_check() -> Tuple[Dict[str, Any], int]:
    """시스템 헬스 체크 API"""
    try:
        # MongoDB 연결 확인
        db.command('ping')
        
        return standard_response(
            "시스템이 정상 작동 중입니다",
            data={'status': 'healthy'}
        )
        
    except Exception as e:
        return handle_exception(
            Exception("데이터베이스 연결 오류"),
            error_type="db_error"
        ) 