from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from datetime import datetime
from bson import ObjectId
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
        # 검색 파라미터
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))
        
        # 기본 쿼리 (분류된 이미지)
        query = {'is_classified': True}
        
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
            
        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}
            
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
                'evtnum': 1
            }
        ).skip((page - 1) * per_page).limit(per_page))
        
        response_data = {
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": img['ThumnailPath'],
                "date": datetime.fromisoformat(img['DateTimeOriginal']['$date'].replace('Z', '')).strftime('%Y-%m-%d'),
                "serial_number": img.get('SerialNumber', ''),
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0)
            } for img in images]
        }
        
        return standard_response(
            MESSAGES['success']['search'],
            data=response_data,
            meta=pagination_meta(total, page, per_page)
        )
        
    except Exception as e:
        return handle_exception(e)

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
                'evtnum': 1
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
                "event_number": img.get('evtnum', 0)
            } for img in images]
        }
        
        return standard_response(
            MESSAGES['success']['search'],
            data=response_data,
            meta=pagination_meta(total, page, per_page)
        )
        
    except Exception as e:
        return handle_exception(e) 