from flask import Blueprint, request, jsonify
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
import os
import logging as logger
search_bp = Blueprint('search', __name__)

def normalize_path(path):
    """MongoDB에서 가져온 Windows 경로를 Flask에서 정상적으로 제공할 수 있는 경로로 변환"""
    if not path:
        return ""

    # Windows 경로 정리
    path = path.replace("\\", "/")  # 역슬래시를 슬래시로 변환
    path = path.replace("C:/Users/User/Documents/backend/mnt", "/mnt")  # 경로 변환
    path = path.replace("C:\\Users\\User\\Documents\\backend\\mnt", "/mnt")  # 경로 변환
    path = path.replace("backend/modules/mnt", "/mnt")  # modules/mnt 잘못된 경로 제거

    return path


from datetime import datetime, timedelta

@search_bp.route('/inspection/normal/search', methods=['GET'])
@jwt_required()
def search_normal_inspection():
    """일반 검수 이미지 검색 및 그룹 조회 API"""
    try:
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        evtnum = request.args.get('evtnum')
        group_by = request.args.get('group_by')

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 🔹 `inspection_complete: False` 필터 추가
        query = {
            'is_classified': True,
            'inspection_complete': False  # ✅ 검수 완료되지 않은 데이터만 조회
        }

        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': f'^{project_name}$', '$options': 'i'}

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}

        if evtnum:
            try:
                query['evtnum'] = int(evtnum)
            except ValueError:
                return standard_response("evtnum 값이 올바르지 않습니다.", status=400)

        if date:
            try:
                start_date = datetime.strptime(date, "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                query['DateTimeOriginal.$date'] = {'$gte': start_date.isoformat() + "Z", '$lt': end_date.isoformat() + "Z"}
            except ValueError:
                return standard_response("날짜 형식이 올바르지 않습니다.", status=400)

        # 그룹 조회 (group_by=evtnum)
        if group_by == "evtnum":
            count_pipeline = [
                {'$match': query},
                {'$group': {'_id': '$evtnum'}},
                {'$count': 'total'}
            ]
            total_groups = list(db.images.aggregate(count_pipeline))
            total = total_groups[0]['total'] if total_groups else 0

            pipeline = [
                {'$match': query},
                {'$set': {
                    'DateTimeOriginalStr': {
                        '$ifNull': [{'$getField': {'field': 'DateTimeOriginal', 'input': '$$ROOT'}}, '0000-00-00T00:00:00Z']
                    }
                }},
                {'$sort': {'DateTimeOriginal': 1}},
                {'$group': {
                    '_id': '$evtnum',
                    'first_image': {'$first': '$$ROOT'},
                    'image_count': {'$sum': 1}
                }},
                {'$project': {
                    '_id': 1,
                    'first_image': {
                        '$ifNull': ['$first_image', {
                            'SerialNumber': 'UNKNOWN',
                            'ThumnailPath': '',
                            'ProjectInfo': {'ProjectName': 'Unknown'},
                            'DateTimeOriginalStr': '0000-00-00T00:00:00Z'
                        }]
                    },
                    'image_count': 1
                }},
                {'$sort': {'_id': -1}},
                {'$skip': (page - 1) * per_page},
                {'$limit': per_page}
            ]

            groups = list(db.images.aggregate(pipeline))

            return jsonify({
                "status": 200,
                "message": "그룹 목록 조회 성공",
                "total": total,
                "page": page,
                "per_page": per_page,
                "groups": [{
                    "evtnum": group['_id'],
                    "serialNumber": group['first_image']['SerialNumber'],
                    "imageCount": group['image_count'],
                    "ThumnailPath": normalize_path(group['first_image'].get('ThumnailPath', '')),  
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['first_image']['DateTimeOriginalStr']
                } for group in groups]
            }), 200

        # 일반 검색
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                      .skip((page - 1) * per_page)
                      .limit(per_page))

        return jsonify({
            "status": 200,
            "message": "검색 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": normalize_path(img.get('ThumnailPath', '')),  
                "date": img.get('DateTimeOriginal', {}).get('$date', '0000-00-00T00:00:00Z'),
                "serial_number": img.get('SerialNumber', ''),
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', True),
                "latitude": img.get('Latitude', None),
                "longitude": img.get('Longitude', None),
                "accuracy": img.get('Accuracy', 0)
            } for img in images]
        }), 200

    except Exception as e:
        return handle_exception(e, error_type="db_error")



@search_bp.route('/inspection/exception/search', methods=['GET'])
@jwt_required()
def search_exception_inspection():
    """예외 검수 이미지 검색 및 그룹 조회 API"""
    try:
        # 검색 파라미터
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        exception_status = request.args.get('exception_status')
        evtnum = request.args.get('evtnum')  # 특정 그룹 조회
        group_by = request.args.get('group_by')  # 그룹 조회 모드

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 (예외 검수)
        query = {'is_classified': False}

        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': project_name, '$options': 'i'}

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if exception_status:
            query['exception_status'] = exception_status

        if evtnum:
            query['evtnum'] = int(evtnum)

        if date:
            try:
                start_date = f"{date}T00:00:00.000Z"
                end_date = f"{date}T23:59:59.999Z"
                query['DateTimeOriginal'] = {'$gte': start_date, '$lte': end_date}
            except ValueError:
                return standard_response("날짜 형식이 잘못되었습니다.", status=400)

        # 그룹 조회 모드 (group_by=evtnum)
        if group_by == "evtnum":
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

            return jsonify({
                "status": 200,
                "message": "그룹 목록 조회 성공",
                "total": len(groups),
                "page": page,
                "per_page": per_page,
                "groups": [{
                    "evtnum": group['_id']['evtnum'],
                    "serialNumber": group['_id']['SerialNumber'],
                    "imageCount": group['image_count'],
                    "ThumnailPath": group['first_image']['ThumnailPath'],
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['first_image']['DateTimeOriginal'],
                    "exceptionStatus": group['first_image'].get('exception_status', 'pending')
                } for group in groups]
            }), 200

        # 일반 검색 모드
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                      .skip((page - 1) * per_page)
                      .limit(per_page))

        return jsonify({
            "status": 200,
            "message": "검색 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": img['ThumnailPath'],
                "date": img['DateTimeOriginal'],
                "serial_number": img.get('SerialNumber', ''),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "exception_status": img.get('exception_status', 'pending'),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', False),
                "latitude": img.get('Latitude', None),  
                "longitude": img.get('Longitude', None),  
                "accuracy": img.get('Accuracy', 0)  
            } for img in images]
        }), 200

    except Exception as e:
        return handle_exception(e, error_type="db_error")

@search_bp.route('/images/search', methods=['GET'])
@jwt_required()
def search_inspection_images():
    """검수 완료한 이미지 검색 및 그룹 조회 API"""
    try:
        # 검색 파라미터
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        evtnum = request.args.get('evtnum')  # 특정 그룹 필터링
        group_by = request.args.get('group_by')  # 그룹 조회 모드

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 (검수 완료된 이미지만 조회)
        query = {'inspection_complete': True}

        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': f'^{project_name}$', '$options': 'i'}

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}

        if evtnum:
            query['evtnum'] = int(evtnum)

        if date:
            try:
                start_date = f"{date}T00:00:00.000Z"
                end_date = f"{date}T23:59:59.999Z"
                query['DateTimeOriginal'] = {'$gte': start_date, '$lte': end_date}
            except ValueError:
                return standard_response("날짜 형식이 잘못되었습니다.", status=400)

        # 그룹 조회 모드 (group_by=evtnum)
        if group_by == "evtnum":
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

            return jsonify({
                "status": 200,
                "message": "검수 완료된 그룹 목록 조회 성공",
                "total": len(groups),
                "page": page,
                "per_page": per_page,
                "groups": [{
                    "evtnum": group['_id']['evtnum'],
                    "serialNumber": group['_id']['SerialNumber'],
                    "imageCount": group['image_count'],
                    "ThumnailPath": group['first_image']['ThumnailPath'],
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['first_image']['DateTimeOriginal']
                } for group in groups]
            }), 200

        # 일반 검색 모드
        total = db.images.count_documents(query)
        images = list(db.images.find(query)
                      .skip((page - 1) * per_page)
                      .limit(per_page))

        return jsonify({
            "status": 200,
            "message": "검수 완료된 이미지 검색 성공",
            "total": total,
            "page": page,
            "per_page": per_page,
            "images": [{
                "id": str(img['_id']),
                "filename": img['FileName'],
                "thumbnail": img['ThumnailPath'],
                "date": img['DateTimeOriginal'],
                "serial_number": img.get('SerialNumber', ''),
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0),
                "inspection_complete": img.get('inspection_complete', False),  # 검수 완료 여부 포함
                "latitude": img.get('Latitude', None),
                "longitude": img.get('Longitude', None),
                "accuracy": img.get('Accuracy', 0)
            } for img in images]
        }), 200

    except Exception as e:
        return handle_exception(e, error_type="db_error")