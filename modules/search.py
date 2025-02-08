from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from datetime import datetime, timedelta
from bson import json_util
from .database import db
from .utils.response import standard_response, handle_exception, pagination_meta
from .utils.constants import (
    PER_PAGE_DEFAULT, 
    MESSAGES,
    VALID_EXCEPTION_STATUSES
)

search_bp = Blueprint('search', __name__)



@search_bp.route('/inspection/normal/search', methods=['GET'])
@jwt_required()
def search_normal_inspection():
    """일반 검수 이미지 검색 API"""
    try:
        # 검색 파라미터 로깅
        print("검색 파라미터:", {
            'project_name': request.args.get('project_name'),
            'date': request.args.get('date'),
            'serial_number': request.args.get('serial_number'),
            'species': request.args.get('species'),
            'page': request.args.get('page'),
            'per_page': request.args.get('per_page')
        })

        # 검색 파라미터
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 (분류된 이미지를 false로 변경)
        query = {'is_classified': False}

        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': f'^{project_name}$', '$options': 'i'}

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}

        if date:
            try:
                search_date = datetime.strptime(date, '%Y-%m-%d')
                # 해당 날짜의 시작과 끝을 계산
                start_date = f"{date}T00:00:00.000Z"
                end_date = f"{date}T23:59:59.999Z"
                query['DateTimeOriginal'] = {
                    '$gte': start_date,
                    '$lte': end_date
                }
            except ValueError:
                return standard_response("날짜 형식이 잘못되었습니다.", status=400)

        # 검색 실행
        total = db.images.count_documents(query)
        images = list(db.images.find(
            query,
            {
                '_id': 1,
                'FileName': 1,
                'ThumnailPath': 1,
                'DateTimeOriginal': 1,
                'SerialNumber': 1,
                'BestClass': 1,
                'ProjectInfo': 1,
                'Count': 1,
                'evtnum': 1,
                'is_classified': 1
            }
        ).skip((page - 1) * per_page).limit(per_page))

        # 쿼리 로깅
        print("MongoDB 쿼리:", query)
        
        # 검색 결과 수 로깅
        print("검색된 총 문서 수:", total)
        print("필터링된 이미지 수:", len(images))

        # 응답 데이터 변환
        response_data = {
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": img['ThumnailPath'],
                "date": img['DateTimeOriginal'],  # 그대로 반환
                "serial_number": img.get('SerialNumber', ''),
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', False)
            } for img in images]
        }

        return standard_response(
            "검색 성공",
            data=response_data,
            meta=pagination_meta(len(images), page, per_page)
        )

    except Exception as e:
        print("에러 발생:", str(e))  # 에러 로깅
        return handle_exception(e, error_type="db_error")


@search_bp.route('/inspection/exception/search', methods=['GET'])
@jwt_required()
def search_exception_inspection():
    """예외 검수 이미지 검색 API"""
    try:
        # 검색 파라미터
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        exception_status = request.args.get('exception_status')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))
        
        # 기본 쿼리 (미분류 이미지)
        query = {'is_classified': False}
        
        # 조건 추가
        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': project_name, '$options': 'i'}
            
        if date:
            try:
                search_date = datetime.strptime(date, '%Y-%m-%d')
                query['DateTimeOriginal.$date'] = {
                    '$gte': search_date.isoformat() + 'Z',
                    '$lt': datetime(search_date.year, search_date.month, search_date.day + 1).isoformat() + 'Z'
                }
            except ValueError:
                return standard_response(MESSAGES['error']['invalid_request'], status=400)
                
        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}
            
        if exception_status and exception_status in VALID_EXCEPTION_STATUSES:
            query['exception_status'] = exception_status
            
        # 검색 실행
        total = db.images.count_documents(query)
        images = list(db.images.find(
            query,
            {
                '_id': 1, 
                'FileName': 1, 
                'ThumnailPath': 1, 
                'DateTimeOriginal': 1,
                'SerialNumber': 1,
                'ProjectInfo': 1,
                'exception_status': 1,
                'evtnum': 1,
                'is_classified': 1
            }
        ).skip((page - 1) * per_page).limit(per_page))
        
        response_data = {
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": img['ThumnailPath'],
                "date": datetime.fromisoformat(img['DateTimeOriginal']['$date'].replace('Z', '')).strftime('%Y-%m-%d'),
                "serial_number": img.get('SerialNumber', ''),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "exception_status": img.get('exception_status', 'pending'),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', False)
            } for img in images]
        }
        
        return standard_response(
            MESSAGES['success']['search'],
            data=response_data,
            meta=pagination_meta(total, page, per_page)
        )
        
    except Exception as e:
        return handle_exception(e) 