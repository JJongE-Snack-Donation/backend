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
import traceback
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

import traceback  # 예외 로그 출력

@search_bp.route('/inspection/normal/search', methods=['GET'])
@jwt_required()
def search_normal_inspection():
    """일반 검수 이미지 검색 및 그룹 조회 API"""
    try:
        project_id = request.args.get('project_id')
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        evtnum = request.args.get('evtnum')
        group_by = request.args.get('group_by')

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        query = {'is_classified': True, 'inspection_complete': False}

        if project_id:
            query['ProjectInfo.ID'] = project_id
        if project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': f'^{project_name}$', '$options': 'i'}
        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}
        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}
        if evtnum:
            try:
                query['evtnum'] = int(evtnum)
                if project_id:  # 프로젝트 ID도 함께 필터링해야 함
                    query['ProjectInfo.ID'] = project_id
            except ValueError:
                return jsonify({"status": 400, "message": "evtnum 값이 올바르지 않습니다."}), 400


        if date:
            try:
                start_date = datetime.strptime(date, "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                query['DateTimeOriginal'] = {'$gte': start_date, '$lt': end_date}
            except ValueError:
                return standard_response("날짜 형식이 올바르지 않습니다.", status=400)

        # 그룹 조회 (group_by=evtnum)
        if group_by == "evtnum":
            count_pipeline = [
                {'$match': query},
                {'$group': {'_id': {'evtnum': '$evtnum', 'project_id': '$ProjectInfo.ID'}}},  
                {'$count': 'total'}
            ]
            total_groups = list(db.images.aggregate(count_pipeline))
            total = total_groups[0]['total'] if total_groups and 'total' in total_groups[0] else 0

            pipeline = [
                {'$match': query},
                {'$set': {
                    'DateTimeOriginalStr': {'$ifNull': ['$DateTimeOriginal', '0000-00-00T00:00:00Z']}
                }},
                {'$sort': {'DateTimeOriginal': 1}},
                {'$group': {
                    '_id': {
                        'evtnum': '$evtnum',
                        'project_id': '$ProjectInfo.ID'  
                    },
                    'first_image': {'$first': '$$ROOT'},
                    'image_count': {'$sum': 1}
                }},
                {'$sort': {'_id.evtnum': -1}},
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
                    "evtnum": group['_id']['evtnum'],
                    "projectId": group['_id']['project_id'],
                    "serialNumber": group['first_image'].get('SerialNumber', 'UNKNOWN'),
                    "imageCount": group['image_count'],
                    "ThumnailPath": normalize_path(group['first_image'].get('ThumnailPath', '')),
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['first_image']['DateTimeOriginalStr'],
                    "query_params": {
                        "evtnum": group['_id']['evtnum'],
                        "project_id": group['_id']['project_id']
                    }
                } for group in groups]
            }), 200

        # 일반 검색 (상세 조회)
        if evtnum:
            # project_id와 evtnum 모두로 필터링
            if not project_id:
                return standard_response("evtnum 검색 시 project_id가 필요합니다.", status=400)
            query['ProjectInfo.ID'] = project_id
            query['evtnum'] = int(evtnum)

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
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "project_id": img.get('ProjectInfo', {}).get('ID', ''),
                "evtnum": img.get('evtnum')
            } for img in images]
        }), 200

    except Exception as e:
        print("예외 발생:", str(e))
        traceback.print_exc()
        return handle_exception(e, error_type="db_error")


@search_bp.route('/inspection/exception/search', methods=['GET'])
@jwt_required()
def search_exception_inspection():
    """예외 검수 이미지 검색 및 그룹 조회 API"""
    try:
        project_id = request.args.get('project_id')
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        exception_status = request.args.get('exception_status')
        evtnum = request.args.get('evtnum')
        group_by = request.args.get('group_by')

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 검색 조건 (미분류된 이미지만 조회)
        query = {'is_classified': False, 'inspection_complete': False}

        if project_id:
            query['ProjectInfo.ID'] = project_id
        elif project_name:
            query['ProjectInfo.ProjectName'] = {'$regex': project_name, '$options': 'i'}

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if exception_status:
            query['exception_status'] = exception_status

        if evtnum:
            try:
                query['evtnum'] = int(evtnum)
                if project_id:  # 프로젝트 ID도 함께 필터링 (중복 방지)
                    query['ProjectInfo.ID'] = project_id
            except ValueError:
                return jsonify({"status": 400, "message": "evtnum 값이 올바르지 않습니다."}), 400

        if date:
            try:
                start_date = datetime.strptime(date, "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                query['DateTimeOriginal'] = {'$gte': start_date, '$lt': end_date}
            except ValueError:
                return standard_response("날짜 형식이 잘못되었습니다.", status=400)

        # ✅ 그룹 조회: 같은 프로젝트 내에서 같은 evtnum을 가진 이미지만 그룹화
        if group_by == "evtnum":
            pipeline = [
                {'$match': query},
                {'$set': {
                    'DateTimeOriginalStr': {'$ifNull': ['$DateTimeOriginal', '0000-00-00T00:00:00Z']}
                }},
                {'$sort': {'DateTimeOriginal': 1}},
                {'$group': {
                    '_id': {
                        'evtnum': '$evtnum',
                        'project_id': '$ProjectInfo.ID'  # ✅ 프로젝트 ID 기준으로 그룹화
                    },
                    'first_image': {'$first': '$$ROOT'},
                    'image_count': {'$sum': 1}
                }},
                {'$sort': {'_id.evtnum': -1}},
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
                    "projectId": group['_id']['project_id'],  
                    "serialNumber": group['first_image'].get('SerialNumber', 'UNKNOWN'),
                    "imageCount": group['image_count'],
                    "ThumnailPath": normalize_path(group['first_image'].get('ThumnailPath', '')),
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['first_image'].get('DateTimeOriginalStr', '0000-00-00T00:00:00Z'),
                    "exceptionStatus": group['first_image'].get('exception_status', 'pending')
                } for group in groups]
            }), 200

        # ✅ 일반 검색 모드 (단일 이미지 리스트 조회)
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
                "thumbnail": normalize_path(img['ThumnailPath']),
                "date": img.get('DateTimeOriginal', {}).get('$date', '0000-00-00T00:00:00Z'),
                "serial_number": img.get('SerialNumber', ''),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "project_id": img.get('ProjectInfo', {}).get('ID', ''),
                "exception_status": img.get('exception_status', 'pending'),
                "event_number": img.get('evtnum', 0),
                "is_classified": img.get('is_classified', False),
                "latitude": img.get('Latitude', None),  
                "longitude": img.get('Longitude', None),  
                "accuracy": img.get('Accuracy', 0)  
            } for img in images]
        }), 200

    except Exception as e:
        print("예외 발생:", str(e))
        traceback.print_exc()
        return handle_exception(e, error_type="db_error")


@search_bp.route('/images/search', methods=['GET'])
@jwt_required()
def search_inspection_images():
    """검수 완료한 이미지 검색 및 그룹 조회 API"""
    try:
        # 검색 파라미터
        project_id = request.args.get('project_id')
        project_name = request.args.get('project_name')
        date = request.args.get('date')
        serial_number = request.args.get('serial_number')
        species = request.args.get('species')
        evtnum = request.args.get('evtnum')
        group_by = request.args.get('group_by')

        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', PER_PAGE_DEFAULT))

        # 기본 쿼리 (검수 완료된 이미지만 조회)
        query = {'inspection_complete': True}

        if project_id:
            query['ProjectInfo.ID'] = project_id
        elif project_name:
            query['ProjectInfo.ProjectName'] = project_name 

        if serial_number:
            query['SerialNumber'] = {'$regex': serial_number, '$options': 'i'}

        if species:
            query['BestClass'] = {'$regex': species, '$options': 'i'}

        if evtnum:
            query['evtnum'] = int(evtnum)

        if date:
            try:
                start_date = datetime.strptime(date, "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                query['DateTimeOriginal'] = {'$gte': start_date, '$lt': end_date}
            except ValueError:
                return standard_response("날짜 형식이 잘못되었습니다.", status=400)

        # 그룹 조회 모드 (group_by=evtnum)
        if group_by == "evtnum":
            pipeline = [
                {'$match': query},
                {'$group': {
                    '_id': {'evtnum': '$evtnum', 'project_id': '$ProjectInfo.ID'}, 
                    'first_image': {'$first': '$$ROOT'},
                    'image_count': {'$sum': 1},
                    'DateTimeOriginal': {'$first': '$DateTimeOriginal'}
                }},
                {'$project': {
                    '_id': 1,
                    'first_image': 1,
                    'image_count': 1,
                    'DateTimeOriginalStr': {
                        '$ifNull': ['$DateTimeOriginal', '0000-00-00T00:00:00Z']
                    }
                }},
                {'$sort': {'DateTimeOriginalStr': -1}},
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
                    "projectId": group['_id']['project_id'], 
                    "serialNumber": group['first_image'].get('SerialNumber', 'UNKNOWN'),
                    "imageCount": group['image_count'],
                    "ThumnailPath": normalize_path(group['first_image'].get('ThumnailPath', '')),
                    "projectName": group['first_image'].get('ProjectInfo', {}).get('ProjectName', ''),
                    "DateTimeOriginal": group['DateTimeOriginalStr']
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
                "ThumnailPath": normalize_path(img.get('ThumnailPath', '')),
                "date": img['DateTimeOriginal'],
                "serial_number": img.get('SerialNumber', ''),
                "species": img.get('BestClass', '미확인'),
                "project_name": img.get('ProjectInfo', {}).get('ProjectName', ''),
                "project_id": img.get('ProjectInfo', {}).get('ID', ''),
                "count": img.get('Count', 0),
                "event_number": img.get('evtnum', 0),
                "inspection_complete": img.get('inspection_complete', False),
                "latitude": img.get('Latitude', None),
                "longitude": img.get('Longitude', None),
                "accuracy": img.get('Accuracy', 0)
            } for img in images]
        }), 200

    except Exception as e:
        print("예외 발생:", str(e))
        traceback.print_exc()
        return handle_exception(e, error_type="db_error")