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

search_bp = Blueprint('search', __name__)



@search_bp.route('/inspection/normal/search', methods=['GET'])
@jwt_required()
def search_normal_inspection():
    """일반 검수 이미지 검색 및 그룹 조회 API"""
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

        # 기본 쿼리 (일반 검수)
        query = {'is_classified': True}

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
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', False)
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
                "is_classified": img.get('is_classified', False)
            } for img in images]
        }), 200

    except Exception as e:
        return handle_exception(e, error_type="db_error")
